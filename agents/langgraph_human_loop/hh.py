"""
TechCorp Customer Support Agent
- LangGraph Human-in-the-Loop with interrupt()
- Custom MySQLSaver checkpointer (LangGraph has no built-in MySQL saver)
- FastAPI REST interface
"""

from __future__ import annotations

import json
import os
import pickle
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Annotated, Any, Iterator, Literal, Optional, Sequence, Tuple
from uuid import uuid4

import pymysql
import pymysql.cursors
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages.ai import AIMessage
from langchain_core.messages.tool import ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command, interrupt
from typing_extensions import TypedDict

# ─────────────────────────────────────────────
#  Custom MySQLSaver  (LangGraph ships no built-in MySQL checkpointer)
# ─────────────────────────────────────────────

SETUP_SQL = """
CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id   VARCHAR(128) NOT NULL,
    checkpoint_id VARCHAR(128) NOT NULL,
    parent_checkpoint_id VARCHAR(128),
    checkpoint  LONGBLOB NOT NULL,
    metadata    LONGBLOB NOT NULL,
    PRIMARY KEY (thread_id, checkpoint_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS checkpoint_writes (
    thread_id   VARCHAR(128) NOT NULL,
    checkpoint_id VARCHAR(128) NOT NULL,
    task_id     VARCHAR(128) NOT NULL,
    idx         INT          NOT NULL,
    channel     VARCHAR(256) NOT NULL,
    value       LONGBLOB,
    PRIMARY KEY (thread_id, checkpoint_id, task_id, idx)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


class MySQLSaver(BaseCheckpointSaver):
    """
    Thread-safe MySQL checkpointer for LangGraph.

    Usage:
        saver = MySQLSaver.from_conn_string("mysql+pymysql://user:pass@host:3306/db")
        saver.setup()          # create tables once
        graph = builder.compile(checkpointer=saver)
    """

    def __init__(self, conn_params: dict):
        super().__init__()
        self.conn_params = conn_params
        self._local = threading.local()

    # ── connection management ──────────────────────────────────────────────

    @classmethod
    def from_conn_string(cls, conn_string: str) -> "MySQLSaver":
        """Parse a mysql+pymysql://user:pass@host:port/db connection string."""
        # Strip the driver prefix so pymysql can parse it
        url = conn_string.replace("mysql+pymysql://", "")
        # user:pass@host:port/db
        userinfo, hostinfo = url.split("@", 1)
        user, password = userinfo.split(":", 1)
        if "/" in hostinfo:
            hostport, db = hostinfo.rsplit("/", 1)
        else:
            hostport, db = hostinfo, ""
        if ":" in hostport:
            host, port_str = hostport.split(":", 1)
            port = int(port_str)
        else:
            host, port = hostport, 3306
        return cls({"host": host, "port": port, "user": user,
                    "password": password, "database": db})

    @contextmanager
    def _cursor(self):
        conn = pymysql.connect(
            **self.conn_params,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )
        try:
            with conn.cursor() as cur:
                yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── one-time setup ─────────────────────────────────────────────────────

    def setup(self):
        with self._cursor() as cur:
            for statement in SETUP_SQL.strip().split(";"):
                stmt = statement.strip()
                if stmt:
                    cur.execute(stmt)

    # ── helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _dumps(obj: Any) -> bytes:
        return pickle.dumps(obj)

    @staticmethod
    def _loads(data: bytes) -> Any:
        return pickle.loads(data)  # noqa: S301

    # ── BaseCheckpointSaver interface ──────────────────────────────────────

    def get_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = config["configurable"].get("checkpoint_id")

        with self._cursor() as cur:
            if checkpoint_id:
                cur.execute(
                    "SELECT * FROM checkpoints WHERE thread_id=%s AND checkpoint_id=%s",
                    (thread_id, checkpoint_id),
                )
            else:
                cur.execute(
                    "SELECT * FROM checkpoints WHERE thread_id=%s "
                    "ORDER BY checkpoint_id DESC LIMIT 1",
                    (thread_id,),
                )
            row = cur.fetchone()

        if row is None:
            return None

        checkpoint: Checkpoint = self._loads(row["checkpoint"])
        metadata: CheckpointMetadata = self._loads(row["metadata"])
        parent_id = row.get("parent_checkpoint_id")

        config_out = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": row["checkpoint_id"],
            }
        }
        parent_config = (
            {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_id": parent_id,
                }
            }
            if parent_id
            else None
        )
        return CheckpointTuple(config_out, checkpoint, metadata, parent_config)

    def list(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[dict] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> Iterator[CheckpointTuple]:
        if config is None:
            return
        thread_id = config["configurable"]["thread_id"]
        query = "SELECT * FROM checkpoints WHERE thread_id=%s ORDER BY checkpoint_id DESC"
        params: list = [thread_id]
        if limit:
            query += f" LIMIT {int(limit)}"

        with self._cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

        for row in rows:
            checkpoint: Checkpoint = self._loads(row["checkpoint"])
            metadata: CheckpointMetadata = self._loads(row["metadata"])
            parent_id = row.get("parent_checkpoint_id")
            yield CheckpointTuple(
                config={
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_id": row["checkpoint_id"],
                    }
                },
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config=(
                    {
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_id": parent_id,
                        }
                    }
                    if parent_id
                    else None
                ),
            )

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict,
    ) -> RunnableConfig:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = checkpoint["id"]
        parent_id = config["configurable"].get("checkpoint_id")

        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO checkpoints
                    (thread_id, checkpoint_id, parent_checkpoint_id, checkpoint, metadata)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    checkpoint=VALUES(checkpoint),
                    metadata=VALUES(metadata)
                """,
                (
                    thread_id,
                    checkpoint_id,
                    parent_id,
                    self._dumps(checkpoint),
                    self._dumps(metadata),
                ),
            )

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[Tuple[str, Any]],
        task_id: str,
    ) -> None:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = config["configurable"]["checkpoint_id"]

        with self._cursor() as cur:
            for idx, (channel, value) in enumerate(writes):
                cur.execute(
                    """
                    INSERT INTO checkpoint_writes
                        (thread_id, checkpoint_id, task_id, idx, channel, value)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE value=VALUES(value)
                    """,
                    (
                        thread_id,
                        checkpoint_id,
                        task_id,
                        idx,
                        channel,
                        self._dumps(value),
                    ),
                )


# ─────────────────────────────────────────────
#  State
# ─────────────────────────────────────────────

class TicketState(TypedDict):
    """State for customer support ticket resolution."""
    messages: Annotated[list, add_messages]
    ticket_id: str
    customer_name: str
    issue_category: str
    severity: str
    resolution_steps: list[str]
    ticket_resolved: bool
    escalated_to_manager: bool


# ─────────────────────────────────────────────
#  LLM & prompts
# ─────────────────────────────────────────────

llm = ChatOpenAI(model="gpt-4o-mini")

SUPPORT_AGENT_SYSINT = (
    "system",
    "You are a professional customer support agent for TechCorp. Your role is to:\n"
    "1. Listen to customer issues and categorize them (billing, technical, account, shipping, other)\n"
    "2. Assess severity level (low, medium, high, critical)\n"
    "3. Troubleshoot problems step-by-step using available tools\n"
    "4. Document resolution steps using the document_resolution_step tool\n"
    "5. Escalate to manager if issue cannot be resolved or is critical\n"
    "Be empathetic, professional, and solution-focused. "
    "Always confirm the customer is satisfied before closing the ticket.\n"
    "When the customer says they are done or the issue is resolved, "
    "call send_satisfaction_survey and then say goodbye.",
)

WELCOME_MSG = (
    "Hello! Welcome to TechCorp Support. I'm here to help resolve your issue. "
    "What's the problem you're experiencing today?"
)


# ─────────────────────────────────────────────
#  Tools
# ─────────────────────────────────────────────

@tool
def categorize_issue(category: str) -> str:
    """Categorize the customer's issue as: billing, technical, account, shipping, or other."""
    valid_categories = ["billing", "technical", "account", "shipping", "other"]
    if category.lower() in valid_categories:
        return f"Issue categorized as: {category}"
    return "Please choose from: billing, technical, account, shipping, or other"


@tool
def assess_severity(severity: str) -> str:
    """Assess the severity of the issue as: low, medium, high, or critical."""
    valid_severities = ["low", "medium", "high", "critical"]
    if severity.lower() in valid_severities:
        return f"Severity level set to: {severity}"
    return "Please choose from: low, medium, high, or critical"


@tool
def document_resolution_step(step: str) -> str:
    """Document each resolution step taken during the support session."""
    timestamp = datetime.now().isoformat()
    return f"[{timestamp}] Step documented: {step}"


@tool
def query_knowledge_base(query: str) -> str:
    """Query the knowledge base for solutions to common issues."""
    knowledge_base = {
        "login": "Try clearing browser cache, resetting password, or disabling VPN.",
        "payment": "Verify card details, check expiration date, or try a different payment method.",
        "delivery": "Track order status in your account or contact shipping carrier.",
        "account": "Update profile settings or verify email address in account settings.",
        "technical": "Restart device, check internet connection, update application.",
    }
    for key, solution in knowledge_base.items():
        if key in query.lower():
            return f"Knowledge Base Result: {solution}"
    return "No matching solutions found. This may require escalation."


@tool
def create_ticket_log(summary: str, status: str = "in_progress") -> str:
    """Create a log entry for the current ticket."""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "summary": summary,
        "status": status,
    }
    return json.dumps(log_entry)


@tool
def escalate_to_manager(reason: str) -> str:
    """Escalate this ticket to a manager with the given reason."""
    return f"ESCALATION NOTICE: {reason}\nNotifying manager on duty..."


@tool
def send_satisfaction_survey() -> str:
    """Send a satisfaction survey to the customer after issue resolution."""
    return "Satisfaction survey sent to customer. Thank you for contacting TechCorp Support!"


SUPPORT_TOOLS = [
    categorize_issue,
    assess_severity,
    document_resolution_step,
    query_knowledge_base,
    create_ticket_log,
    escalate_to_manager,
    send_satisfaction_survey,
]

llm_with_tools = llm.bind_tools(SUPPORT_TOOLS)


# ─────────────────────────────────────────────
#  Graph nodes
# ─────────────────────────────────────────────

def support_chat_node(state: TicketState) -> dict:
    """
    Core LLM node: generates the next agent message.
    On first call (no messages) it emits the welcome message.
    """
    if not state["messages"]:
        return {"messages": [AIMessage(content=WELCOME_MSG)]}
    new_output = llm_with_tools.invoke([SUPPORT_AGENT_SYSINT] + state["messages"])
    return {"messages": [new_output]}


def human_node(state: TicketState) -> dict:
    """
    Human-in-the-loop node.
    Uses LangGraph's interrupt() to pause execution and wait for
    a customer/manager message. The graph is resumed via Command(resume=...).
    
    Typing "close", "exit", or "done" (case-insensitive) resolves the ticket.
    """
    # interrupt() suspends the graph here and returns the resumed value.
    user_input: str = interrupt("Waiting for customer response...")

    if user_input.strip().lower() in {"close", "exit", "done"}:
        return {
            "messages": [("user", user_input)],
            "ticket_resolved": True,
        }
    return {"messages": [("user", user_input)]}


def tool_node(state: TicketState) -> dict:
    """
    Execute tool calls made by the LLM and update derived state fields.
    We run the tools manually so we can also update ticket metadata
    (issue_category, severity, escalated_to_manager, resolution_steps).
    """
    last_msg = state["messages"][-1]
    if not hasattr(last_msg, "tool_calls") or not last_msg.tool_calls:
        return {}

    tool_map = {t.name: t for t in SUPPORT_TOOLS}
    outbound: list[ToolMessage] = []

    # Mutable copies of list/flag fields
    resolution_steps: list[str] = list(state.get("resolution_steps", []))
    issue_category: str = state.get("issue_category", "")
    severity: str = state.get("severity", "")
    escalated: bool = state.get("escalated_to_manager", False)

    for tc in last_msg.tool_calls:
        name = tc["name"]
        args = tc["args"]

        if name not in tool_map:
            result = f"Error: unknown tool '{name}'"
        else:
            result = tool_map[name].invoke(args)

        # Mirror side-effects into state
        if name == "categorize_issue":
            issue_category = args.get("category", issue_category)
        elif name == "assess_severity":
            severity = args.get("severity", severity)
        elif name == "document_resolution_step":
            resolution_steps.append(args.get("step", ""))
        elif name == "escalate_to_manager":
            escalated = True

        outbound.append(
            ToolMessage(content=str(result), name=name, tool_call_id=tc["id"])
        )

    return {
        "messages": outbound,
        "issue_category": issue_category,
        "severity": severity,
        "resolution_steps": resolution_steps,
        "escalated_to_manager": escalated,
    }


# ─────────────────────────────────────────────
#  Routing / conditional edges
# ─────────────────────────────────────────────

def route_after_agent(state: TicketState) -> Literal["tools", "human", "__end__"]:
    """
    After support_chat_node:
    - If the LLM requested tool calls → go to tool_node
    - If the ticket is resolved → end
    - Otherwise → wait for human input
    """
    if state.get("ticket_resolved", False):
        return END
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "human"


def route_after_human(state: TicketState) -> Literal["support_agent", "__end__"]:
    """After human_node: end if resolved, otherwise back to the agent."""
    if state.get("ticket_resolved", False):
        return END
    return "support_agent"


# ─────────────────────────────────────────────
#  Graph construction
# ─────────────────────────────────────────────

def build_graph(checkpointer: BaseCheckpointSaver):
    builder = StateGraph(TicketState)

    builder.add_node("support_agent", support_chat_node)
    builder.add_node("human", human_node)       # interrupt lives here
    builder.add_node("tools", tool_node)

    builder.add_edge(START, "support_agent")
    builder.add_conditional_edges("support_agent", route_after_agent)
    builder.add_edge("tools", "support_agent")  # after tools → back to agent
    builder.add_conditional_edges("human", route_after_human)

    return builder.compile(checkpointer=checkpointer)


# ─────────────────────────────────────────────
#  FastAPI app
# ─────────────────────────────────────────────

app = FastAPI(title="TechCorp Support API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Build once at startup
# _conn_string = os.getenv(
#     "DATABASE_URL",
#     "mysql+pymysql://root:Maxis@123@localhost:3306/support_tickets_db",
# )
from urllib.parse import quote_plus
password = quote_plus("Maxis@123")

_conn_string = f"mysql+pymysql://root:{password}@localhost:3306/support_tickets_db"
import urllib.parse

password = "Maxis@123"
encoded_password = urllib.parse.quote_plus(password)
_conn_string = f"mysql+pymysql://root:{encoded_password}@localhost:3306/support_tickets_db"

print(f"Using MySQL connection string: { _conn_string }")
checkpointer = MySQLSaver.from_conn_string(_conn_string)
checkpointer.setup()
graph = build_graph(checkpointer)


def _config(ticket_id: str) -> dict:
    return {"configurable": {"thread_id": ticket_id}}


@app.post("/create_ticket")
def create_ticket(customer_name: str):
    """
    Open a new support ticket.
    Returns the ticket_id and the agent's welcome message.
    The graph pauses at the human node waiting for the first customer message.
    """
    ticket_id = str(uuid4())[:8]
    initial_state: TicketState = {
        "messages": [],
        "ticket_id": ticket_id,
        "customer_name": customer_name,
        "issue_category": "",
        "severity": "",
        "resolution_steps": [],
        "ticket_resolved": False,
        "escalated_to_manager": False,
    }

    try:
        result = graph.invoke(initial_state, config=_config(ticket_id))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # The last AI message is the welcome message (graph suspended at human node)
    last_ai = next(
        (m for m in reversed(result["messages"]) if isinstance(m, AIMessage)), None
    )
    return {
        "ticket_id": ticket_id,
        "customer_name": customer_name,
        "agent_message": last_ai.content if last_ai else WELCOME_MSG,
    }


@app.post("/ticket_response")
def ticket_response(ticket_id: str, customer_message: str):
    """
    Submit a customer message to an existing ticket.
    The graph resumes from the interrupt() in human_node.
    """
    try:
        result = graph.invoke(
            Command(resume=customer_message),
            config=_config(ticket_id),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    last_ai = next(
        (m for m in reversed(result["messages"]) if isinstance(m, AIMessage)), None
    )
    return {
        "ticket_id": ticket_id,
        "agent_response": last_ai.content if last_ai else "",
        "severity": result.get("severity", ""),
        "category": result.get("issue_category", ""),
        "escalated": result.get("escalated_to_manager", False),
        "resolved": result.get("ticket_resolved", False),
        "steps_taken": result.get("resolution_steps", []),
    }


@app.get("/ticket_status")
def get_ticket_status(ticket_id: str):
    """Return the latest persisted state for a ticket."""
    try:
        state = graph.get_state(_config(ticket_id))
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if state is None or not state.values:
        raise HTTPException(status_code=404, detail="Ticket not found")

    vals = state.values
    return {
        "ticket_id": ticket_id,
        "customer_name": vals.get("customer_name", ""),
        "issue_category": vals.get("issue_category", ""),
        "severity": vals.get("severity", ""),
        "resolved": vals.get("ticket_resolved", False),
        "escalated": vals.get("escalated_to_manager", False),
        "steps_taken": vals.get("resolution_steps", []),
        "message_count": len(vals.get("messages", [])),
    }
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8200, reload=True)
# from langgraph.graph import StateGraph, START, END
# from langchain_openai import ChatOpenAI
# from typing import Annotated, Literal
# from typing_extensions import TypedDict
# from langgraph.graph.message import add_messages
# from langchain_core.messages.ai import AIMessage
# from langchain_core.tools import tool
# from langgraph.checkpoint.postgres import PostgresSaver
# from langgraph.types import Command, interrupt
# from langgraph.prebuilt import ToolNode
# from langchain_core.messages.tool import ToolMessage
# from datetime import datetime
# from fastapi import FastAPI
# from fastapi.middleware.cors import CORSMiddleware
# import os
# import json
# from uuid import uuid4

# llm = ChatOpenAI()

# class TicketState(TypedDict):
#     """State for customer support ticket resolution."""
#     messages: Annotated[list, add_messages]
#     ticket_id: str
#     customer_name: str
#     issue_category: str
#     severity: str
#     resolution_steps: list[str]
#     ticket_resolved: bool
#     escalated_to_manager: bool

# SUPPORT_AGENT_SYSINT = (
#     "system",
#     "You are a professional customer support agent for TechCorp. Your role is to:\n"
#     "1. Listen to customer issues and categorize them (billing, technical, account, shipping, other)\n"
#     "2. Assess severity level (low, medium, high, critical)\n"
#     "3. Troubleshoot problems step-by-step using available tools\n"
#     "4. Document resolution steps\n"
#     "5. Escalate to manager if issue cannot be resolved or is critical\n"
#     "Be empathetic, professional, and solution-focused. Always confirm the customer is satisfied before closing the ticket."
# )

# WELCOME_MSG = "Hello! Welcome to TechCorp Support. I'm here to help resolve your issue. What's the problem you're experiencing today?"

# def human_agent_node(state: TicketState) -> TicketState:
#     """Receive input from customer or manager."""
#     last_msg = state["messages"][-1]
#     print(f"\n[Agent]: {last_msg.content}\n")
    
#     user_input = interrupt("Customer/Manager response")
#     print()
    
#     if user_input.lower() in {"close", "exit", "done"}:
#         state["ticket_resolved"] = True
    
#     return state | {"messages": [("user", user_input)]}

# def maybe_exit_node(state: TicketState) -> Literal["support_agent", "__end__"]:
#     """Check if ticket is resolved."""
#     if state.get("ticket_resolved", False):
#         return END
#     else:
#         return "support_agent"

# @tool
# def categorize_issue(category: str) -> str:
#     """Categorize the customer's issue."""
#     valid_categories = ["billing", "technical", "account", "shipping", "other"]
#     if category.lower() in valid_categories:
#         return f"Issue categorized as: {category}"
#     return "Please choose from: billing, technical, account, shipping, or other"

# @tool
# def assess_severity(severity: str) -> str:
#     """Assess the severity of the issue."""
#     valid_severities = ["low", "medium", "high", "critical"]
#     if severity.lower() in valid_severities:
#         return f"Severity level set to: {severity}"
#     return "Please choose from: low, medium, high, or critical"

# @tool
# def document_resolution_step(step: str) -> str:
#     """Document each resolution step taken."""
#     timestamp = datetime.now().isoformat()
#     return f"[{timestamp}] Step documented: {step}"

# @tool
# def query_knowledge_base(query: str) -> str:
#     """Query the knowledge base for solutions."""
#     knowledge_base = {
#         "login": "Try clearing browser cache, resetting password, or disabling VPN.",
#         "payment": "Verify card details, check expiration date, or try a different payment method.",
#         "delivery": "Track order status in your account or contact shipping carrier.",
#         "account": "Update profile settings or verify email address in account settings.",
#         "technical": "Restart device, check internet connection, update application."
#     }
    
#     for key, solution in knowledge_base.items():
#         if key in query.lower():
#             return f"Knowledge Base Result: {solution}"
    
#     return "No matching solutions found. This may require escalation."

# @tool
# def create_ticket_log(summary: str, status: str) -> str:
#     """Create a log entry for the ticket."""
#     log_entry = {
#         "timestamp": datetime.now().isoformat(),
#         "summary": summary,
#         "status": status
#     }
#     return json.dumps(log_entry)

# @tool
# def escalate_to_manager(reason: str) -> str:
#     """Escalate ticket to manager."""
#     escalation_msg = f"ESCALATION NOTICE: {reason}\nNotifying manager on duty..."
#     return escalation_msg

# @tool
# def send_satisfaction_survey() -> str:
#     """Send satisfaction survey to customer."""
#     return "Satisfaction survey sent. We'd appreciate your feedback!"

# def support_agent_node(state: TicketState) -> TicketState:
#     """Process tool calls from the support agent."""
#     tool_msg = state.get("messages", [])[-1]
#     outbound_msgs = []
    
#     if not hasattr(tool_msg, "tool_calls") or not tool_msg.tool_calls:
#         return state

#     for tool_call in tool_msg.tool_calls:
#         tool_name = tool_call["name"]
#         args = tool_call["args"]
        
#         if tool_name == "categorize_issue":
#             state["issue_category"] = args.get("category", "other")
#             response = f"Issue categorized as: {args.get('category')}"
        
#         elif tool_name == "assess_severity":
#             state["severity"] = args.get("severity", "medium")
#             response = f"Severity level: {args.get('severity')}"
        
#         elif tool_name == "document_resolution_step":
#             step = args.get("step", "")
#             state["resolution_steps"].append(step)
#             response = f"Step documented: {step}"
        
#         elif tool_name == "query_knowledge_base":
#             response = query_knowledge_base.invoke(args.get("query", ""))
        
#         elif tool_name == "create_ticket_log":
#             response = create_ticket_log.invoke(
#                 args.get("summary", ""),
#                 args.get("status", "in_progress")
#             )
        
#         elif tool_name == "escalate_to_manager":
#             state["escalated_to_manager"] = True
#             response = escalate_to_manager.invoke(args.get("reason", ""))
        
#         elif tool_name == "send_satisfaction_survey":
#             response = send_satisfaction_survey.invoke()
        
#         else:
#             response = f"Unknown tool: {tool_name}"
        
#         outbound_msgs.append(
#             ToolMessage(
#                 content=str(response),
#                 name=tool_name,
#                 tool_call_id=tool_call["id"],
#             )
#         )
    
#     return {"messages": outbound_msgs, "resolution_steps": state.get("resolution_steps", [])}

# def maybe_route_to_tools(state: TicketState) -> str:
#     """Route to tools or human based on message type."""
#     if not (msgs := state.get("messages", [])):
#         raise ValueError("No messages in state")
    
#     msg = msgs[-1]
    
#     if state.get("ticket_resolved", False):
#         return END
    
#     elif hasattr(msg, "tool_calls") and len(msg.tool_calls) > 0:
#         return "tools"
    
#     else:
#         return "human"

# support_tools = [
#     categorize_issue,
#     assess_severity,
#     query_knowledge_base,
#     create_ticket_log,
#     escalate_to_manager,
#     send_satisfaction_survey
# ]

# tool_node = ToolNode(support_tools)
# llm_with_tools = llm.bind_tools(support_tools)

# def support_chat_node(state: TicketState) -> TicketState:
#     """Support agent with tools."""

#     if state["messages"]:
#         new_output = llm_with_tools.invoke([SUPPORT_AGENT_SYSINT] + state["messages"])
#     else:
#         new_output = AIMessage(content=WELCOME_MSG)
    
#     return {"messages": [new_output]}

# def build_graph_with_mysql():
#     """Build the support ticket graph with MySQL persistence."""
#     graph_builder = StateGraph(TicketState)
    
#     graph_builder.add_node("support_agent", support_chat_node)
#     graph_builder.add_node("human", human_agent_node)
#     graph_builder.add_node("tools", tool_node)
    
#     graph_builder.add_conditional_edges("support_agent", maybe_route_to_tools)
#     graph_builder.add_conditional_edges("human", maybe_exit_node)
#     graph_builder.add_edge("tools", "support_agent")
#     graph_builder.add_edge(START, "support_agent")
    
#     # MySQL Checkpointer
#     conn_string = os.getenv(
#         "DATABASE_URL",
#         "mysql+pymysql://root:password@localhost:3306/support_tickets_db"
#     )
    
#     checkpointer = PostgresSaver.from_conn_string(conn_string)
#     checkpointer.setup()
    
#     return graph_builder.compile(checkpointer=checkpointer)

# # FastAPI Application
# app = FastAPI()
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# graph = build_graph_with_mysql()

# @app.post("/create_ticket")
# def create_ticket(customer_name: str):
#     """Create a new support ticket."""
#     ticket_id = str(uuid4())[:8]
    
#     initial_state = {
#         "messages": [],
#         "ticket_id": ticket_id,
#         "customer_name": customer_name,
#         "issue_category": "",
#         "severity": "",
#         "resolution_steps": [],
#         "ticket_resolved": False,
#         "escalated_to_manager": False
#     }
    
#     config = {"configurable": {"thread_id": ticket_id}}
#     result = graph.invoke(initial_state, config=config)
    
#     return {
#         "ticket_id": ticket_id,
#         "customer_name": customer_name,
#         "welcome_message": result["messages"][-1].content
#     }

# @app.post("/ticket_response")
# def ticket_response(ticket_id: str, customer_message: str):
#     """Process customer response."""
#     config = {"configurable": {"thread_id": ticket_id}}
#     result = graph.invoke(
#         Command(resume=customer_message),
#         config=config
#     )
    
#     return {
#         "ticket_id": ticket_id,
#         "agent_response": result["messages"][-1].content,
#         "severity": result.get("severity", ""),
#         "category": result.get("issue_category", ""),
#         "escalated": result.get("escalated_to_manager", False),
#         "steps_taken": result.get("resolution_steps", [])
#     }

# @app.get("/ticket_status")
# def get_ticket_status(ticket_id: str):
#     """Get current ticket status."""
#     return {
#         "ticket_id": ticket_id,
#         "status": "Contact support for details"
#     }