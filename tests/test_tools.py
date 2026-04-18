import os
import pytest
from unittest.mock import MagicMock, patch

from databricks.sdk.service.sql import StatementState


@pytest.fixture
def mock_workspace():
    with patch("src.mcp_server.server._w") as mock_w:
        yield mock_w.return_value


def _catalog(name):
    c = MagicMock()
    c.name = name
    return c


def _table(name, columns=None, comment=None):
    t = MagicMock()
    t.name = name
    t.full_name = f"samples.tpcds_sf1.{name}"
    t.comment = comment
    t.columns = columns or []
    return t


def _column(name, type_text="bigint", comment=None):
    c = MagicMock()
    c.name = name
    c.type_text = type_text
    c.comment = comment
    return c


def _stmt_result(columns, rows):
    r = MagicMock()
    r.status.state = StatementState.SUCCEEDED
    r.manifest.schema.columns = [_column(c) for c in columns]
    r.result.data_array = rows
    return r


def _failed_stmt(message):
    r = MagicMock()
    r.status.state = StatementState.FAILED
    r.status.error.message = message
    return r


# --- list_catalogs ---

def test_list_catalogs(mock_workspace):
    from src.mcp_server.server import list_catalogs

    mock_workspace.catalogs.list.return_value = [_catalog("main"), _catalog("samples")]
    assert list_catalogs() == ["main", "samples"]


# --- list_tables ---

def test_list_tables(mock_workspace):
    from src.mcp_server.server import list_tables

    mock_workspace.tables.list.return_value = [_table("store_sales"), _table("customer")]
    result = list_tables()
    assert result == ["store_sales", "customer"]
    mock_workspace.tables.list.assert_called_once_with(
        catalog_name="samples", schema_name="tpcds_sf1"
    )


# --- search_tables ---

def test_search_tables_match(mock_workspace):
    from src.mcp_server.server import search_tables

    t = _table("store_sales", columns=[_column("ss_sales_price")])
    mock_workspace.tables.list.return_value = [t]

    result = search_tables("sales")
    assert len(result) == 1
    assert result[0]["full_name"] == "samples.tpcds_sf1.store_sales"


def test_search_tables_no_match(mock_workspace):
    from src.mcp_server.server import search_tables

    mock_workspace.tables.list.return_value = [_table("date_dim")]
    assert search_tables("sales") == []


# --- explain_table ---

def test_explain_table(mock_workspace):
    from src.mcp_server.server import explain_table

    col = _column("ss_item_sk", type_text="bigint", comment="item key")
    table = MagicMock()
    table.full_name = "samples.tpcds_sf1.store_sales"
    table.comment = "Store sales fact"
    table.columns = [col]
    mock_workspace.tables.get.return_value = table

    result = explain_table("store_sales")
    assert result["full_name"] == "samples.tpcds_sf1.store_sales"
    assert result["columns"][0] == {"name": "ss_item_sk", "type": "bigint", "comment": "item key"}
    mock_workspace.tables.get.assert_called_once_with(
        full_name="samples.tpcds_sf1.store_sales"
    )


# --- run_query ---

def test_run_query_success(mock_workspace):
    from src.mcp_server.server import run_query

    mock_workspace.statement_execution.execute_statement.return_value = _stmt_result(
        ["total_sales"], [["1000.00"]]
    )

    with patch.dict(os.environ, {"DATABRICKS_SQL_WAREHOUSE_ID": "test-wh"}):
        result = run_query("SELECT SUM(ss_sales_price) AS total_sales FROM samples.tpcds_sf1.store_sales")

    assert result["columns"] == ["total_sales"]
    assert result["rows"] == [["1000.00"]]
    assert result["row_count"] == 1


def test_run_query_failure(mock_workspace):
    from src.mcp_server.server import run_query

    mock_workspace.statement_execution.execute_statement.return_value = _failed_stmt("Table not found")

    with patch.dict(os.environ, {"DATABRICKS_SQL_WAREHOUSE_ID": "test-wh"}):
        with pytest.raises(RuntimeError, match="Table not found"):
            run_query("SELECT * FROM nonexistent")


# --- get_job_status ---

def test_get_job_status(mock_workspace):
    from src.mcp_server.server import get_job_status

    run = MagicMock()
    run.run_id = 123
    run.job_id = 456
    run.run_name = "daily_pipeline"
    run.state.life_cycle_state = "TERMINATED"
    run.state.result_state = "SUCCESS"
    run.start_time = 1_000_000
    run.end_time = 1_060_000
    mock_workspace.jobs.list_runs.return_value = [run]

    result = get_job_status(limit=1)
    assert len(result) == 1
    assert result[0]["run_id"] == 123
    assert result[0]["duration_seconds"] == 60


def test_get_job_status_filters_by_job_id(mock_workspace):
    from src.mcp_server.server import get_job_status

    mock_workspace.jobs.list_runs.return_value = []
    get_job_status(job_id=42, limit=5)
    mock_workspace.jobs.list_runs.assert_called_once_with(
        limit=5, expand_tasks=False, job_id=42
    )
