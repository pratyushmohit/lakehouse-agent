import os
from pathlib import Path
from typing import Annotated

from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from typing_extensions import TypedDict
from langchain_ollama import ChatOllama

_PROMPT_FILE = Path(__file__).parent / "system_prompt.md"
SYSTEM_PROMPT = _PROMPT_FILE.read_text(encoding="utf-8").strip()


class State(TypedDict):
    messages: Annotated[list, add_messages]

def build_agent(tools: list):
    llm = ChatOllama(
        model=os.environ.get("OLLAMA_MODEL", "llama3.2"),
        base_url=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
    ).bind_tools(tools)

    def call_model(state: State):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
        return {"messages": [llm.invoke(messages)]}

    graph = StateGraph(State)
    graph.add_node("agent", call_model)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")

    return graph.compile()
