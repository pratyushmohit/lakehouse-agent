# lakehouse-agent

An autonomous Databricks Lakehouse Operations Agent. Ask business questions in plain English — the agent discovers the right tables in Unity Catalog, runs SQL against a Databricks SQL warehouse, checks pipeline health, and interprets results in business terms.

## How it works

Two services communicate over the [Model Context Protocol (MCP)](https://modelcontextprotocol.io):

```
User → POST /chat
         └─ Agent (LangGraph + Ollama)
               └─ MCP Client → MCP Server (FastMCP)
                                     └─ Databricks SDK
                                           ├─ Unity Catalog
                                           ├─ SQL Warehouse
                                           └─ Jobs API
```

**Agent tools:**

| Tool | What it does |
|---|---|
| `list_catalogs` | List all Unity Catalog catalogs |
| `search_tables` | Find tables in `samples.tpcds_sf1` by keyword |
| `explain_table` | Get column schema and metadata for a table |
| `run_query` | Execute SQL on a Databricks SQL warehouse |
| `get_job_status` | Check recent job/pipeline run statuses |
| `get_query_history` | Analyse query history for cost and performance |

## Stack

- **FastAPI** — HTTP API
- **LangGraph** — cyclic agent graph (ReAct loop)
- **Ollama** — local LLM (`gemma4:e4b` recommended)
- **FastMCP** — MCP server
- **langchain-mcp-adapters** — MCP client
- **Databricks SDK** — Unity Catalog, SQL warehouse, Jobs
- **Langfuse** — agent tracing and observability (optional)
- **Docker Compose** — runs both services together
- **uv** — dependency management

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop)
- [Ollama](https://ollama.com) running locally
- A Databricks workspace with Unity Catalog enabled and a SQL warehouse

## 1. Pull the model

```bash
ollama pull gemma4:e4b
```

Any Ollama model with tool calling support works. `gemma4:e4b` (9.6 GB) is recommended.

## 2. Set up Databricks credentials

This project authenticates via a **service principal** — no personal access tokens.

**Create a service principal**

Databricks UI → **Settings** → **Identity & Access** → **Service Principals** → **Add service principal**.

**Generate a client secret**

Open the service principal → **Secrets** tab → **Generate secret**. Copy the **Client ID** (on the SP overview page) and the **Client Secret** (shown only once).

**Grant workspace access**

Settings → **Identity & Access** → **Service Principals** → select yours → **Roles** → assign **Workspace access**.

**Grant Unity Catalog permissions**

Run in a Databricks notebook or SQL editor:

```sql
GRANT USE CATALOG ON CATALOG samples TO `<your-client-id>`;
GRANT USE SCHEMA ON SCHEMA samples.tpcds_sf1 TO `<your-client-id>`;
GRANT SELECT ON SCHEMA samples.tpcds_sf1 TO `<your-client-id>`;
```

**Grant SQL warehouse access**

SQL Warehouses → select your warehouse → **Permissions** → add the service principal with **Can use**.

**Find your warehouse ID**

SQL Warehouses → select your warehouse → **Connection details** → copy the last segment of the HTTP Path:
`/sql/1.0/warehouses/abc123def456` → warehouse ID is `abc123def456`

## 3. Configure environment

```bash
cp .env.example .env
```

Open `.env` and fill in:

```env
DATABRICKS_HOST=https://adb-xxxx.azuredatabricks.net
DATABRICKS_CLIENT_ID=your-service-principal-client-id
DATABRICKS_CLIENT_SECRET=your-service-principal-client-secret
DATABRICKS_SQL_WAREHOUSE_ID=your-warehouse-id

MODEL_PROVIDER=ollama
OLLAMA_MODEL=gemma4:e4b
```

Langfuse is optional. If you have an account, add:

```env
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

## 4. Run

```bash
make install   # install dependencies
make build     # build Docker images
make up        # start both services
```

Both services start automatically. The agent waits for the MCP server to be healthy before starting.

| Service | URL |
|---|---|
| Agent API | `http://localhost:8000` |
| MCP Server | `http://localhost:8001` |

Check both are up:

```bash
curl http://localhost:8000/health
curl http://localhost:8001/health
```

## 5. Try it

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What tables are available in the TPC-DS dataset?"}'
```

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What were the top 5 stores by total sales last year?"}'
```

## API

### `GET /health`

```json
{ "status": "ok" }
```

### `POST /chat`

```json
{
  "message": "Which stores had the highest sales?",
  "session_id": "optional-uuid-to-group-conversation-turns",
  "user_id": "optional-user-identifier"
}
```

`session_id` and `user_id` are auto-generated if omitted.

**Response:**

```json
{ "response": "Based on the store_sales table..." }
```

## Make commands

| Command | Description |
|---|---|
| `make install` | Install dependencies via uv |
| `make build` | Build Docker images |
| `make up` | Start both services via docker compose |
| `make down` | Stop and remove containers |
