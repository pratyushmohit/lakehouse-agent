# lakehouse-agent

A FastAPI service wrapping a LangGraph conversational agent backed by a local Ollama model, with observability via Langfuse.

## Stack

- **FastAPI** — HTTP API
- **LangGraph** — agent graph orchestration
- **LangChain Ollama** — local LLM (llama3.2)
- **Langfuse** — agent tracing and observability
- **FastMCP** — MCP server/client support
- **uv** — dependency management

## Project structure

```
src/
├── agent/
│   └── agent.py      # LangGraph agent
├── mcp/              # MCP tools
└── app.py            # FastAPI app
```

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- A Databricks workspace with Unity Catalog enabled and a SQL warehouse

## Databricks credentials

This project authenticates via a **service principal** — the production-grade approach (no personal tokens).

**1. Create a service principal**

Databricks UI → **Settings** → **Identity & Access** → **Service Principals** → **Add service principal**. Give it a name (e.g. `lakehouse-agent`).

**2. Generate a client secret**

Open the service principal → **Secrets** tab → **Generate secret**. Copy the **Client ID** (on the SP overview page) and **Client Secret** (only shown once).

**3. Grant workspace access**

Settings → **Identity & Access** → **Service Principals** → select yours → **Roles** → assign **Workspace access**.

**4. Grant Unity Catalog permissions**

In the Databricks UI, run the following in a notebook or SQL editor — replace the placeholders:

```sql
-- Allow the SP to browse catalogs and schemas
GRANT USE CATALOG ON CATALOG <your_catalog> TO `<client-id>`;
GRANT USE SCHEMA ON SCHEMA <your_catalog>.<your_schema> TO `<client-id>`;
-- Allow reading tables
GRANT SELECT ON SCHEMA <your_catalog>.<your_schema> TO `<client-id>`;
```

**5. Grant SQL warehouse access**

SQL Warehouses → select your warehouse → **Permissions** → add the service principal with **Can use** permission.

**6. Find your warehouse ID**

SQL Warehouses → select your warehouse → **Connection details** tab → copy the last segment of the **HTTP Path** (e.g. `/sql/1.0/warehouses/abc123def456` → ID is `abc123def456`).

**7. Populate `.env`**

```bash
cp .env.example .env
```

```env
DATABRICKS_HOST=https://adb-xxxx.azuredatabricks.net
DATABRICKS_CLIENT_ID=<client-id>
DATABRICKS_CLIENT_SECRET=<client-secret>
DATABRICKS_SQL_WAREHOUSE_ID=<warehouse-id>
```

## Getting started

```bash
make install

# Terminal 1 — MCP server (Databricks tools)
make mcp-server

# Terminal 2 — Agent API
make dev
```

The API will be available at `http://localhost:8000`.

## API

### `GET /health`

```json
{ "status": "ok" }
```

### `POST /chat`

**Request**
```json
{ "message": "Hello!" }
```

**Response**
```json
{ "response": "Hi there! How can I help you?" }
```

## Docker

Runs both services (MCP server + agent) via Docker Compose:

```bash
make docker-build
make docker-run   # docker compose up -d
make docker-stop  # docker compose down
```

## Make commands

| Command | Description |
|---|---|
| `make install` | Install dependencies via uv |
| `make mcp-server` | Start the Databricks MCP server on :8001 |
| `make dev` | Start the agent API on :8000 with hot reload |
| `make run` | Start the agent API without hot reload |
| `make docker-build` | Build Docker image |
| `make docker-run` | Start both services via docker compose |
| `make docker-stop` | Tear down docker compose |
