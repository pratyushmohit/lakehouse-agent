# lakehouse-agent

An autonomous Databricks Lakehouse Operations Agent. Ask business questions in plain English — the agent figures out which tables to query, verifies their schema, runs SQL against a Databricks SQL warehouse, checks pipeline health, and interprets results in business terms. It does not guess: it discovers the right data before it writes a single line of SQL.

## What it does

Instead of a chatbot that generates SQL and hopes for the best, this agent follows a structured reasoning loop before every answer:

1. **Discovers** the right tables in Unity Catalog by keyword
2. **Inspects** column names and types to avoid guessing
3. **Queries** the warehouse with precise, verified SQL
4. **Interprets** results in business language — trends, outliers, the "so what"

Example questions it handles:

- *"What were the top 5 stores by total net sales last quarter?"*
- *"Which product categories have the highest return rates?"*
- *"Did the nightly ETL job succeed? Is the data fresh?"*
- *"Who ran the most expensive queries in the last 24 hours?"*
- *"How much did web sales grow year-over-year for electronics?"*

## Architecture

Two independently deployable services communicate over the [Model Context Protocol (MCP)](https://modelcontextprotocol.io):

```
User
 └── POST /chat
       └── Agent API (FastAPI + LangGraph)          :8000
             └── MCP Client (streamable HTTP)
                   └── MCP Server (FastMCP)          :8001
                         └── Databricks SDK
                               ├── Unity Catalog API   (table discovery)
                               ├── SQL Warehouse       (query execution)
                               ├── Jobs API            (pipeline health)
                               └── system.query.history (cost analysis)
```

**Agent API** (`src/app.py`) — FastAPI server. On startup, connects to the MCP server, loads the tool list, and compiles the LangGraph agent. Each `POST /chat` invokes the agent with a Langfuse trace attached, grouping multi-turn exchanges into a single session.

**MCP Server** (`src/mcp_server/server.py`) — FastMCP server exposing seven Databricks tools over the streamable-HTTP MCP transport. The Databricks `WorkspaceClient` is lazily initialised from environment variables and auto-configured via the SDK's credential chain.

**Why MCP?** Decoupling the tool layer behind the Model Context Protocol means the agent can be swapped out (LangGraph today, another framework tomorrow) without changing any Databricks integration code. The MCP server is also independently testable and could serve multiple agents simultaneously.

## Agent Reasoning Loop

The agent is a cyclic [LangGraph](https://langchain-ai.github.io/langgraph/) ReAct graph — not a linear chain. It loops back from tool results to the model until it has enough information to answer, or until the recursion limit (20 iterations) is reached.

```
START → [agent] → tools_condition → [tool node] → [agent] → ... → END
                       └── END (if no tool call needed)
```

The system prompt enforces a four-step reasoning discipline:

| Step | Action |
|---|---|
| DISCOVER | `search_tables` by business keyword — never assume a table exists |
| EXPLAIN | `explain_table` to verify column names before writing SQL |
| QUERY | `run_query` with aggregations and filters, not raw row dumps |
| INTERPRET | Translate numbers into business language with context |

## Tools

| Tool | Purpose |
|---|---|
| `list_tables` | List all tables in `samples.tpcds_sf1` |
| `search_tables` | Find tables by keyword — searches table names and column names |
| `explain_table` | Get column names, types, and metadata for a table |
| `run_query` | Execute SQL against the Databricks SQL warehouse; returns up to 1,000 rows |
| `get_job_status` | Check recent Databricks job run states for pipeline health |
| `get_query_history` | Query `system.query.history` for cost and performance analysis |
| `list_catalogs` | List all Unity Catalog catalogs in the workspace |

## Observability

Every request is traced end-to-end with [Langfuse](https://langfuse.com) using the v4 OTel-based SDK:

- Each `POST /chat` opens a root span with the user message as input and the agent response as output
- `propagate_attributes` attaches `session_id` and `user_id` to all child observations, so every tool call and LLM invocation in a conversation appears nested under the same Langfuse session
- On shutdown, `get_client().flush()` ensures buffered spans are sent before the process exits

Langfuse is optional — the agent runs without it if the keys are not set.

## LLM Providers

The agent supports two providers, switchable via `MODEL_PROVIDER`:

| Provider | `MODEL_PROVIDER` value | Default model | Notes |
|---|---|---|---|
| Anthropic Claude | `anthropic` (default) | `claude-sonnet-4-6` | Requires `ANTHROPIC_API_KEY` |
| Ollama (local) | `ollama` | `llama3.2` | Requires Ollama running locally |

Override the model with `ANTHROPIC_MODEL` or `OLLAMA_MODEL`.

## Stack

| Component | Role |
|---|---|
| **FastAPI** | HTTP API server |
| **LangGraph** | Cyclic ReAct agent graph |
| **FastMCP** | MCP server framework |
| **langchain-mcp-adapters** | MCP client that exposes tools as LangChain tools |
| **langchain-anthropic** | Claude model integration |
| **langchain-ollama** | Ollama model integration |
| **Databricks SDK** | Unity Catalog, SQL warehouse, Jobs, system tables |
| **Langfuse** | Agent tracing and observability |
| **Docker Compose** | Runs both services with health checks and startup ordering |
| **uv** | Dependency management and virtual environments |

## Dataset

The agent is wired to `samples.tpcds_sf1` — the [TPC-DS](https://www.tpc.org/tpcds/) retail benchmark dataset included with every Databricks workspace. It contains 24 tables across the full retail supply chain: store/web/catalog sales and returns, customers, items, stores, warehouses, inventory, promotions, and date/time dimensions.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop)
- A Databricks workspace with Unity Catalog enabled and a running SQL warehouse
- An Anthropic API key **or** [Ollama](https://ollama.ai) running locally

## 1. Configure Databricks credentials

This project authenticates via a **service principal** — not a personal access token.

**Create a service principal**

Databricks UI → **Settings** → **Identity & Access** → **Service Principals** → **Add service principal**.

**Generate a client secret**

Open the service principal → **Secrets** tab → **Generate secret**. Copy the **Client ID** (on the overview page) and the **Client Secret** (shown only once).

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

SQL Warehouses → select your warehouse → **Connection details** → copy the last segment of the HTTP path:
`/sql/1.0/warehouses/abc123def456` → warehouse ID is `abc123def456`

## 2. Configure environment

```bash
cp .env.example .env
```

Fill in `.env`:

```env
# Databricks
DATABRICKS_HOST=https://adb-xxxx.azuredatabricks.net
DATABRICKS_CLIENT_ID=your-service-principal-client-id
DATABRICKS_CLIENT_SECRET=your-service-principal-client-secret
DATABRICKS_SQL_WAREHOUSE_ID=your-warehouse-id

# LLM — use 'anthropic' (default) or 'ollama'
MODEL_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# For Ollama instead:
# MODEL_PROVIDER=ollama
# OLLAMA_MODEL=gemma4:e4b
# OLLAMA_HOST=http://host.docker.internal:11434
```

Langfuse tracing is optional:

```env
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

## 3. Run

```bash
make install   # install Python dependencies via uv
make build     # build Docker images
make up        # start both services
```

The agent API waits for the MCP server to pass its health check before starting.

| Service | URL |
|---|---|
| Agent API | `http://localhost:8000` |
| MCP Server | `http://localhost:8001` |

Verify both are running:

```bash
curl http://localhost:8000/health
curl http://localhost:8001/health
```

## 4. Try it

```bash
# Explore the dataset
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What tables are available in the TPC-DS dataset?"}'

# Business analytics
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What were the top 5 stores by net sales revenue?"}'

# Pipeline health
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Did any Databricks jobs fail in the last 24 hours?"}'

# Cost analysis
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Which queries consumed the most compute time today?"}'
```

## API

### `GET /health`

```json
{ "status": "ok" }
```

### `POST /chat`

**Request:**

```json
{
  "message": "Which product categories have the highest return rates?",
  "session_id": "optional-uuid",
  "user_id": "optional-user-identifier"
}
```

`session_id` groups multiple turns into a single Langfuse session. Both fields are auto-generated if omitted.

**Response:**

```json
{ "response": "Electronics has the highest return rate at 8.3%, driven primarily by televisions and laptops. This is 2.1× the average across all categories. The data comes from joining catalog_returns with item, covering 2.4M return transactions." }
```

## Development

Run both services locally without Docker:

```bash
# Terminal 1
make mcp-server   # MCP server on :8001

# Terminal 2
make dev          # Agent API on :8000 with hot reload
```

Run tests:

```bash
uv run pytest
```

After changing `pyproject.toml`, run `make install` to update `uv.lock`.

## Make commands

| Command | Description |
|---|---|
| `make install` | Install dependencies via uv |
| `make build` | Build Docker images |
| `make up` | Start both services via Docker Compose |
| `make down` | Stop and remove containers |
| `make dev` | Run agent API locally with hot reload |
| `make mcp-server` | Run MCP server locally |
