from databricks.sdk import WorkspaceClient
from dotenv import load_dotenv
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

load_dotenv()

mcp = FastMCP("Databricks Lakehouse MCP Server")


@mcp.custom_route("/health", methods=["GET"])
def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


@mcp.tool()
def list_catalogs() -> list[str]:
    """List all Unity Catalog catalogs in the Databricks workspace."""
    w = WorkspaceClient()
    return [c.name for c in w.catalogs.list()]


app = mcp.http_app(path="/mcp")