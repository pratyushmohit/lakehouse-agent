import logging

from databricks.sdk import WorkspaceClient
from dotenv import load_dotenv
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.logging_config import configure_logging

load_dotenv()
configure_logging()

logger = logging.getLogger(__name__)

mcp = FastMCP("Databricks Lakehouse MCP Server")


@mcp.custom_route("/health", methods=["GET"])
def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


@mcp.tool()
def list_catalogs() -> list[str]:
    """List all Unity Catalog catalogs in the Databricks workspace."""
    logger.info("Tool call: list_catalogs")
    w = WorkspaceClient()
    catalogs = [c.name for c in w.catalogs.list()]
    logger.info("list_catalogs returned %d catalogs", len(catalogs))
    return catalogs


app = mcp.http_app(path="/mcp", stateless_http=True)
