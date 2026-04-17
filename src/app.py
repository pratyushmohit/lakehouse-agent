import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from langchain_mcp_adapters.client import MultiServerMCPClient

from src.agent.agent import build_agent
from src.agent.schemas import ChatRequest

# load_dotenv must run before langfuse.get_client() initialises from env
load_dotenv()

from langfuse import get_client, propagate_attributes  # noqa: E402

_agent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agent
    mcp_url = os.environ.get("MCP_SERVER_URL", "http://localhost:8001/mcp")
    client = MultiServerMCPClient(
        {"databricks": {"url": mcp_url, "transport": "streamable_http"}}
    )
    tools = await client.get_tools()
    _agent = build_agent(tools)
    yield
    _agent = None
    get_client().flush()


app = FastAPI(title="Lakehouse Agent", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat")
async def chat(request: ChatRequest):
    if _agent is None:
        raise HTTPException(status_code=503, detail="Agent not ready")
    langfuse = get_client()

    with langfuse.start_as_current_observation(
        as_type="span",
        name="chat-response",
        input={"message": request.message},
    ) as span:
        with propagate_attributes(
            trace_name="chat-response",
            session_id=request.session_id,
            user_id=request.user_id,
        ):
            result = await _agent.ainvoke(
                {"messages": [{"role": "user", "content": request.message}]}
            )
            response = result["messages"][-1].content
            span.update(output={"response": response})

    return {"response": response}