"""
LangChain agent with middleware example.

This includes:
  • Logging
  • Summarization
  • Human approvals
"""

from typing import Any, Callable

from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    before_model,
    after_model,
    wrap_model_call,
    AgentState,
    Runtime,
    SummarizationMiddleware,
    HumanInTheLoopMiddleware,
)

# ————————————————
# 1) LOGGING MIDDLEWARE
# ————————————————

@before_model
def log_before_model(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    # Log context length and last user message
    last_msg = state["messages"][-1].content if state["messages"] else "<none>"
    print(f"[LOG] About to call model with {len(state['messages'])} messages. Last msg: {last_msg}")
    return None

@after_model
def log_after_model(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    # Print last model output
    last_reply = state["messages"][-1].content if state["messages"] else "<none>"
    print(f"[LOG] Model replied: {last_reply}")
    return None

# ————————————————
# 2) CUSTOM SUMMARIZATION
# ————————————————

summarization = SummarizationMiddleware(
    model="openai:gpt-4o-mini",
    max_tokens_before_summary=3000,
    messages_to_keep=10,
)

# ————————————————
# 3) HUMAN APPROVAL
# ————————————————

human_approval = HumanInTheLoopMiddleware(
    interrupt_on={
        "dangerous_tool": {
            "description": "This action may affect live data – require approval",
            "allowed_decisions": ["approve", "reject"],
        }
    }
)

# ————————————————
# CREATE AGENT WITH MIDDLEWARE
# ————————————————

agent = create_agent(
    model="openai:gpt-4o",
    tools=[
        # Your tool definitions here. Each tool should have a .name
    ],
    middleware=[
        log_before_model,
        summarization,
        human_approval,
        log_after_model,
    ],
)

# ————————————————
# RUN AGENT
# ————————————————

response = agent.invoke(
    {"messages": [{"role": "user", "content": "Fetch me monthly sales data"}]}
)

print("Final Response:", response["messages"][-1].content)