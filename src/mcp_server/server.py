import itertools
import logging
import os

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import Disposition, Format, StatementState
from dotenv import load_dotenv
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.logging_config import configure_logging

load_dotenv()
configure_logging()

logger = logging.getLogger(__name__)

mcp = FastMCP("Databricks Lakehouse MCP Server")

CATALOG = "samples"
SCHEMA = "tpcds_sf1"


def _w() -> WorkspaceClient:
    return WorkspaceClient()


def _exec_sql(sql: str) -> dict:
    wh_id = os.environ["DATABRICKS_SQL_WAREHOUSE_ID"]
    result = _w().statement_execution.execute_statement(
        warehouse_id=wh_id,
        statement=sql,
        wait_timeout="50s",
        disposition=Disposition.INLINE,
        format=Format.JSON_ARRAY,
    )
    if result.status.state != StatementState.SUCCEEDED:
        msg = result.status.error.message if result.status.error else "unknown"
        raise RuntimeError(f"Query failed ({result.status.state}): {msg}")
    columns = [col.name for col in result.manifest.schema.columns]
    rows = result.result.data_array or []
    return {"columns": columns, "rows": rows[:1000], "row_count": len(rows)}


@mcp.custom_route("/health", methods=["GET"])
def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


@mcp.tool()
def list_catalogs() -> list[str]:
    """List all Unity Catalog catalogs in the Databricks workspace."""
    logger.info("Tool call: list_catalogs")
    catalogs = [c.name for c in _w().catalogs.list()]
    logger.info("list_catalogs returned %d catalogs", len(catalogs))
    return catalogs


@mcp.tool()
def search_tables(query: str) -> list[dict]:
    """
    Search for tables in the samples.tpcds_sf1 schema by keyword.
    Matches against table name and column names.
    Returns table name, comment, and column count.
    """
    logger.info("Tool call: search_tables query=%s", query)
    w = _w()
    query_lower = query.lower()
    results = []
    for table in itertools.islice(w.tables.list(catalog_name=CATALOG, schema_name=SCHEMA), 200):
        searchable = f"{table.name} {' '.join(c.name for c in (table.columns or []))}".lower()
        if query_lower in searchable:
            results.append({
                "full_name": table.full_name,
                "comment": table.comment,
                "column_count": len(table.columns) if table.columns else 0,
            })
    logger.info("search_tables found %d tables", len(results))
    return results


@mcp.tool()
def explain_table(table_name: str) -> dict:
    """
    Get schema and metadata for a table in samples.tpcds_sf1.
    Returns column names, types, and comments.
    table_name: just the table name, e.g. 'store_sales'
    """
    logger.info("Tool call: explain_table table=%s", table_name)
    table = _w().tables.get(full_name=f"{CATALOG}.{SCHEMA}.{table_name}")
    return {
        "full_name": table.full_name,
        "comment": table.comment,
        "columns": [
            {"name": col.name, "type": str(col.type_text), "comment": col.comment}
            for col in (table.columns or [])
        ],
    }


@mcp.tool()
def run_query(sql: str) -> dict:
    """
    Execute a SQL query against the Databricks SQL warehouse.
    Returns columns, rows (up to 1000), and row count.
    All queries run against the samples catalog by default.
    """
    logger.info("Tool call: run_query sql=%.200s", sql)
    result = _exec_sql(sql)
    logger.info("run_query returned %d rows", result["row_count"])
    return result


@mcp.tool()
def get_job_status(job_id: int | None = None, limit: int = 10) -> list[dict]:
    """
    Get recent Databricks job run statuses to check pipeline health.
    If job_id provided, returns runs for that job only.
    Otherwise returns the most recent runs across all jobs.
    """
    logger.info("Tool call: get_job_status job_id=%s limit=%d", job_id, limit)
    kwargs: dict = {"limit": limit, "expand_tasks": False}
    if job_id is not None:
        kwargs["job_id"] = job_id
    runs = list(itertools.islice(_w().jobs.list_runs(**kwargs), limit))
    logger.info("get_job_status returned %d runs", len(runs))
    return [
        {
            "run_id": run.run_id,
            "job_id": run.job_id,
            "run_name": run.run_name,
            "state": str(run.state.life_cycle_state) if run.state else None,
            "result_state": str(run.state.result_state) if run.state and run.state.result_state else None,
            "duration_seconds": (
                round((run.end_time - run.start_time) / 1000)
                if run.end_time and run.start_time else None
            ),
        }
        for run in runs
    ]


@mcp.tool()
def get_query_history(hours: int = 24, limit: int = 20) -> dict:
    """
    Retrieve recent SQL query history from system.query.history.
    Shows query text, executor, duration, and status.
    Useful for cost analysis and identifying slow queries.
    """
    logger.info("Tool call: get_query_history hours=%d limit=%d", hours, limit)
    return _exec_sql(f"""
        SELECT
            query_id,
            executed_by,
            SUBSTRING(statement_text, 1, 300) AS query_preview,
            ROUND(total_duration_ms / 1000.0, 2) AS duration_seconds,
            status,
            warehouse_id,
            DATE_FORMAT(start_time, 'yyyy-MM-dd HH:mm:ss') AS started_at
        FROM system.query.history
        WHERE start_time >= DATEADD(HOUR, -{hours}, NOW())
        ORDER BY total_duration_ms DESC NULLS LAST
        LIMIT {limit}
    """)


app = mcp.http_app(path="/mcp", stateless_http=True)
