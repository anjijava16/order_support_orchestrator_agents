

# agents.py
from langgraph.prebuilt import ToolNode
from tools import current_time, random_number, reverse_text, check_order_status, process_refund
from langgraph.types import interrupt
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
import os

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tools = [current_time, random_number, reverse_text, check_order_status, process_refund]
llm_with_tools = llm.bind_tools(tools)

# Support Agent: LLM decides what to do, then ToolNode executes
def support_agent(state):
    messages = state.get("messages", [])
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

# Order Agent: LLM for order tracking
def order_agent(state):
    messages = state.get("messages", [])
    order_tools = [check_order_status]
    llm_with_order_tools = llm.bind_tools(order_tools)
    response = llm_with_order_tools.invoke(messages)
    return {"messages": [response]}

# Tool execution node
tool_node = ToolNode(tools)

# Refund Agent (HITL)
def refund_agent(state):
    order_id = state.get("order_id")
    amount = state.get("amount")

    # Pause for human approval
    approval = interrupt({
        "type": "refund_approval",
        "order_id": order_id,
        "amount": amount,
        "message": f"Approve refund of ${amount} for order {order_id}?"
    })

    if not approval:
        return {"messages": [{"type": "human", "content": "Refund cancelled by human."}]}

    # Execute refund tool after approval
    refund_result = process_refund(order_id, amount)
    return {"messages": [{"type": "ai", "content": f"Refund processed: {refund_result}"}]}

# router.py
def router(state):
    msg = state["messages"][-1].content.lower()
    if "refund" in msg:
        return "refund_agent"
    elif "track" in msg or "shipping" in msg:
        return "order_agent"
    else:
        return "support_agent"
