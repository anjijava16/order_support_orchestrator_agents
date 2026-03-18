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
from urllib.parse import unquote  # decodes %40 → @, %23 → # etc. in passwords
from uuid import uuid4

import pymysql
import pymysql.cursors
import uvicorn
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


# ─────────────────────────────────────────────────────────────────────────────
#  MySQLSaver  –  custom LangGraph checkpointer backed by MySQL
# ─────────────────────────────────────────────────────────────────────────────

# Split into individual statements so we can execute them one by one
# (pymysql does not support multi-statement execute by default).
SETUP_SQL = [
    """
    CREATE TABLE IF NOT EXISTS checkpoints (
        thread_id            VARCHAR(128) NOT NULL,
        checkpoint_id        VARCHAR(128) NOT NULL,
        parent_checkpoint_id VARCHAR(128),
        checkpoint           LONGBLOB     NOT NULL,
        metadata             LONGBLOB     NOT NULL,
        PRIMARY KEY (thread_id, checkpoint_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS checkpoint_writes (
        thread_id     VARCHAR(128) NOT NULL,
        checkpoint_id VARCHAR(128) NOT NULL,
        task_id       VARCHAR(128) NOT NULL,
        idx           INT          NOT NULL,
        channel       VARCHAR(256) NOT NULL,
        value         LONGBLOB,
        PRIMARY KEY (thread_id, checkpoint_id, task_id, idx)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
]


class MySQLSaver(BaseCheckpointSaver):
    """
    Thread-safe MySQL checkpointer for LangGraph.

    Quick start::

        saver = MySQLSaver.from_conn_string(
            "mysql+pymysql://user:p%40ss@localhost:3306/mydb"
        )
        saver.setup()   # creates tables once – safe to call on every startup
        graph = builder.compile(checkpointer=saver)
    """

    def __init__(self, conn_params: dict) -> None:
        super().__init__()
        self.conn_params = conn_params

    # ── factory ───────────────────────────────────────────────────────────────

    @classmethod
    def from_conn_string(cls, conn_string: str) -> "MySQLSaver":
        """
        Parse ``mysql+pymysql://user:pass@host:port/db``.

        The password may contain URL-encoded special characters:
        ``%40`` → ``@``, ``%23`` → ``#``, ``%21`` → ``!``, etc.
        We always URL-decode the password before handing it to pymysql.

        We use ``rfind('@')`` so that a password which itself contains
        a literal ``@`` (encoded as ``%40`` before this call) never
        confuses the host/userinfo split.
        """
        url = conn_string.replace("mysql+pymysql://", "")

        at_idx = url.rfind("@")
        if at_idx == -1:
            raise ValueError(
                f"Invalid connection string (no '@' separator): {conn_string!r}"
            )

        userinfo = url[:at_idx]
        hostinfo = url[at_idx + 1:]

        # Split on the FIRST colon only – the password may itself contain colons.
        colon_idx    = userinfo.index(":")
        user         = userinfo[:colon_idx]
        password_raw = userinfo[colon_idx + 1:]
        password     = unquote(password_raw)     # %40 → @, etc.

        hostport, db = hostinfo.rsplit("/", 1) if "/" in hostinfo else (hostinfo, "")
        host, port   = hostport.split(":", 1)  if ":" in hostport else (hostport, "3306")

        return cls(
            {
                "host":     host,
                "port":     int(port),
                "user":     user,
                "password": password,
                "database": db,
            }
        )

    # ── internal connection helper ────────────────────────────────────────────

    @contextmanager
    def _cursor(self):
        """
        Open a pymysql connection, yield a DictCursor inside a transaction,
        then commit (or rollback on error).

        ``auth_plugin="mysql_native_password"`` + ``ssl_disabled=True``
        are required for MySQL 8+, which defaults to caching_sha2_password.
        That plugin needs SSL, which is typically absent on localhost dev setups.
        Forcing mysql_native_password bypasses the problem entirely.

        If your DBA has disabled mysql_native_password server-wide, run::

            ALTER USER 'root'@'localhost'
                IDENTIFIED WITH mysql_native_password BY 'yourpassword';
            FLUSH PRIVILEGES;
        """
        conn = pymysql.connect(
            **self.conn_params,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
           # auth_plugin="mysql_native_password",   # MySQL 8 compat
            ssl_disabled=True,                     # no SSL for local dev
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

    # ── one-time table creation ───────────────────────────────────────────────

    def setup(self) -> None:
        """Create checkpointer tables if they do not already exist (idempotent)."""
        with self._cursor() as cur:
            for stmt in SETUP_SQL:
                cur.execute(stmt)

    # ── serialisation helpers ─────────────────────────────────────────────────

    @staticmethod
    def _dumps(obj: Any) -> bytes:
        return pickle.dumps(obj)

    @staticmethod
    def _loads(data: bytes) -> Any:
        return pickle.loads(data)  # noqa: S301

    # ── BaseCheckpointSaver interface ─────────────────────────────────────────

    def get_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        thread_id     = config["configurable"]["thread_id"]
        checkpoint_id = config["configurable"].get("checkpoint_id")

        with self._cursor() as cur:
            if checkpoint_id:
                cur.execute(
                    "SELECT * FROM checkpoints "
                    "WHERE thread_id=%s AND checkpoint_id=%s",
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

        checkpoint: Checkpoint         = self._loads(row["checkpoint"])
        metadata:   CheckpointMetadata = self._loads(row["metadata"])
        parent_id = row.get("parent_checkpoint_id")

        return CheckpointTuple(
            config={
                "configurable": {
                    "thread_id":     thread_id,
                    "checkpoint_id": row["checkpoint_id"],
                }
            },
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=(
                {
                    "configurable": {
                        "thread_id":     thread_id,
                        "checkpoint_id": parent_id,
                    }
                }
                if parent_id
                else None
            ),
        )

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
        query  = (
            "SELECT * FROM checkpoints WHERE thread_id=%s "
            "ORDER BY checkpoint_id DESC"
        )
        params: list = [thread_id]
        if limit:
            query += f" LIMIT {int(limit)}"

        with self._cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

        for row in rows:
            checkpoint: Checkpoint         = self._loads(row["checkpoint"])
            metadata:   CheckpointMetadata = self._loads(row["metadata"])
            parent_id = row.get("parent_checkpoint_id")
            yield CheckpointTuple(
                config={
                    "configurable": {
                        "thread_id":     thread_id,
                        "checkpoint_id": row["checkpoint_id"],
                    }
                },
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config=(
                    {
                        "configurable": {
                            "thread_id":     thread_id,
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
        thread_id     = config["configurable"]["thread_id"]
        checkpoint_id = checkpoint["id"]
        parent_id     = config["configurable"].get("checkpoint_id")

        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO checkpoints
                    (thread_id, checkpoint_id, parent_checkpoint_id,
                     checkpoint, metadata)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    checkpoint = VALUES(checkpoint),
                    metadata   = VALUES(metadata)
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
                "thread_id":     thread_id,
                "checkpoint_id": checkpoint_id,
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[Tuple[str, Any]],
        task_id: str,
    ) -> None:
        thread_id     = config["configurable"]["thread_id"]
        checkpoint_id = config["configurable"]["checkpoint_id"]

        with self._cursor() as cur:
            for idx, (channel, value) in enumerate(writes):
                cur.execute(
                    """
                    INSERT INTO checkpoint_writes
                        (thread_id, checkpoint_id, task_id, idx, channel, value)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE value = VALUES(value)
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


# ─────────────────────────────────────────────────────────────────────────────
#  LangGraph State
# ─────────────────────────────────────────────────────────────────────────────

class TicketState(TypedDict):
    """Complete state for one customer support ticket."""
    messages:             Annotated[list, add_messages]
    ticket_id:            str
    customer_name:        str
    issue_category:       str
    severity:             str
    resolution_steps:     list[str]
    ticket_resolved:      bool
    escalated_to_manager: bool


# ─────────────────────────────────────────────────────────────────────────────
#  LLM & system prompt
# ─────────────────────────────────────────────────────────────────────────────

llm = ChatOpenAI(model="gpt-4o-mini")

SUPPORT_AGENT_SYSINT = (
    "system",
    "You are a professional customer support agent for TechCorp. Your role is to:\n"
    "1. Listen to customer issues and categorise them "
    "   (billing, technical, account, shipping, other)\n"
    "2. Assess severity level (low, medium, high, critical)\n"
    "3. Troubleshoot problems step-by-step using available tools\n"
    "4. Document every resolution step with the document_resolution_step tool\n"
    "5. Escalate to a manager when the issue cannot be resolved or is critical\n\n"
    "Be empathetic, professional, and solution-focused. "
    "Always confirm the customer is satisfied before closing the ticket. "
    "When the customer says the issue is resolved or they are done, "
    "call send_satisfaction_survey and then say goodbye.",
)

WELCOME_MSG = (
    "Hello! Welcome to TechCorp Support. "
    "I'm here to help resolve your issue. "
    "What's the problem you're experiencing today?"
)


# ─────────────────────────────────────────────────────────────────────────────
#  Tools
# ─────────────────────────────────────────────────────────────────────────────

@tool
def categorize_issue(category: str) -> str:
    """Categorise the customer's issue as: billing, technical, account, shipping, or other."""
    if category.lower() in {"billing", "technical", "account", "shipping", "other"}:
        return f"Issue categorised as: {category}"
    return "Please choose from: billing, technical, account, shipping, or other"


@tool
def assess_severity(severity: str) -> str:
    """Assess the severity of the issue as: low, medium, high, or critical."""
    if severity.lower() in {"low", "medium", "high", "critical"}:
        return f"Severity level set to: {severity}"
    return "Please choose from: low, medium, high, or critical"


@tool
def document_resolution_step(step: str) -> str:
    """Document each resolution step taken during the support session."""
    return f"[{datetime.now().isoformat()}] Step documented: {step}"


@tool
def query_knowledge_base(query: str) -> str:
    """Query the internal knowledge base for solutions to common issues."""
    kb = {
        "login":     "Try clearing browser cache, resetting password, or disabling VPN.",
        "payment":   "Verify card details, check expiration date, or try a different payment method.",
        "delivery":  "Track order status in your account or contact the shipping carrier.",
        "account":   "Update profile settings or verify your email address in account settings.",
        "technical": "Restart device, check internet connection, update the application.",
    }
    for key, solution in kb.items():
        if key in query.lower():
            return f"Knowledge Base Result: {solution}"
    return "No matching solutions found. This may require escalation."


@tool
def create_ticket_log(summary: str, status: str = "in_progress") -> str:
    """Create a timestamped log entry for the current ticket."""
    return json.dumps(
        {"timestamp": datetime.now().isoformat(), "summary": summary, "status": status}
    )


@tool
def escalate_to_manager(reason: str) -> str:
    """Escalate this ticket to a manager with the given reason."""
    return f"ESCALATION NOTICE: {reason}\nNotifying manager on duty..."


@tool
def send_satisfaction_survey() -> str:
    """Send a post-resolution satisfaction survey to the customer."""
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


# ─────────────────────────────────────────────────────────────────────────────
#  Graph nodes
# ─────────────────────────────────────────────────────────────────────────────

def support_chat_node(state: TicketState) -> dict:
    """
    Core LLM node.
    • First invocation (no messages yet) → emit the static welcome message.
    • Subsequent invocations → call the LLM with all tools bound.
    """
    if not state["messages"]:
        return {"messages": [AIMessage(content=WELCOME_MSG)]}
    return {
        "messages": [
            llm_with_tools.invoke([SUPPORT_AGENT_SYSINT] + state["messages"])
        ]
    }


def human_node(state: TicketState) -> dict:
    """
    Human-in-the-loop node.

    ``interrupt()`` suspends the graph and persists the checkpoint in MySQL.
    The ``/ticket_response`` endpoint resumes it via ``Command(resume=...)``.

    Sending "close", "exit", or "done" (case-insensitive) marks the ticket
    resolved so the graph terminates on the next routing check.
    """
    user_input: str = interrupt("Waiting for customer response...")

    if user_input.strip().lower() in {"close", "exit", "done"}:
        return {"messages": [("user", user_input)], "ticket_resolved": True}

    return {"messages": [("user", user_input)]}


def tool_node(state: TicketState) -> dict:
    """
    Execute all tool calls present in the latest AIMessage, and propagate
    their side-effects (category, severity, resolution steps, escalation flag)
    back into the graph state so they are persisted in the checkpoint.
    """
    last_msg = state["messages"][-1]
    if not hasattr(last_msg, "tool_calls") or not last_msg.tool_calls:
        return {}

    tool_map = {t.name: t for t in SUPPORT_TOOLS}

    # Work on copies so we can return clean deltas
    resolution_steps: list[str] = list(state.get("resolution_steps", []))
    issue_category:   str       = state.get("issue_category", "")
    severity:         str       = state.get("severity", "")
    escalated:        bool      = state.get("escalated_to_manager", False)
    outbound: list[ToolMessage] = []

    for tc in last_msg.tool_calls:
        name = tc["name"]
        args = tc["args"]

        result = (
            tool_map[name].invoke(args)
            if name in tool_map
            else f"Error: unknown tool '{name}'"
        )

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
        "messages":             outbound,
        "issue_category":       issue_category,
        "severity":             severity,
        "resolution_steps":     resolution_steps,
        "escalated_to_manager": escalated,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Routing (conditional edges)
# ─────────────────────────────────────────────────────────────────────────────

def route_after_agent(
    state: TicketState,
) -> Literal["tools", "human", "__end__"]:
    """After the LLM node: tool calls → tools; resolved → end; else → human."""
    if state.get("ticket_resolved", False):
        return END
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "human"


def route_after_human(
    state: TicketState,
) -> Literal["support_agent", "__end__"]:
    """After the human node: resolved → end; else → agent."""
    if state.get("ticket_resolved", False):
        return END
    return "support_agent"


# ─────────────────────────────────────────────────────────────────────────────
#  Graph construction
# ─────────────────────────────────────────────────────────────────────────────

def build_graph(checkpointer: BaseCheckpointSaver):
    builder = StateGraph(TicketState)

    builder.add_node("support_agent", support_chat_node)
    builder.add_node("human",         human_node)    # ← interrupt() lives here
    builder.add_node("tools",         tool_node)

    builder.add_edge(START, "support_agent")
    builder.add_conditional_edges("support_agent", route_after_agent)
    builder.add_edge("tools", "support_agent")       # tools always feed back to agent
    builder.add_conditional_edges("human", route_after_human)

    return builder.compile(checkpointer=checkpointer)


# ─────────────────────────────────────────────────────────────────────────────
#  Application bootstrap
#
#  Set DATABASE_URL in your environment – special characters in the password
#  MUST be URL-encoded (@ → %40, # → %23, ! → %21, etc.).
#
#  export DATABASE_URL="mysql+pymysql://root:Maxis%40123@localhost:3306/support_tickets_db"
# ─────────────────────────────────────────────────────────────────────────────

_conn_string: str = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root:Maxis%40123@localhost:3306/support_tickets_db",
)

print(f"Connecting to MySQL: {_conn_string}")
checkpointer = MySQLSaver.from_conn_string(_conn_string)
#checkpointer.setup()    # idempotent – CREATE TABLE IF NOT EXISTS
graph        = build_graph(checkpointer)


# ─────────────────────────────────────────────────────────────────────────────
#  FastAPI application
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="TechCorp Customer Support API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _config(ticket_id: str) -> dict:
    return {"configurable": {"thread_id": ticket_id}}


@app.post("/create_ticket")
def create_ticket(customer_name: str):
    """
    Open a new support ticket.

    The graph runs until it hits ``interrupt()`` inside ``human_node``,
    saves the checkpoint to MySQL, then returns the agent's welcome message.
    The frontend should store the ``ticket_id`` and use it for all follow-up calls.
    """
    ticket_id = str(uuid4())[:8]
    initial_state: TicketState = {
        "messages":             [],
        "ticket_id":            ticket_id,
        "customer_name":        customer_name,
        "issue_category":       "",
        "severity":             "",
        "resolution_steps":     [],
        "ticket_resolved":      False,
        "escalated_to_manager": False,
    }

    try:
        result = graph.invoke(initial_state, config=_config(ticket_id))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    last_ai = next(
        (m for m in reversed(result["messages"]) if isinstance(m, AIMessage)), None
    )
    return {
        "ticket_id":     ticket_id,
        "customer_name": customer_name,
        "agent_message": last_ai.content if last_ai else WELCOME_MSG,
    }


@app.post("/ticket_response")
def ticket_response(ticket_id: str, customer_message: str):
    """
    Submit a customer message to an existing (interrupted) ticket.

    LangGraph reloads the checkpoint from MySQL and resumes execution from
    the ``interrupt()`` call in ``human_node`` with ``customer_message`` as
    the resumed value.  The graph then runs until the next interrupt or END.
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
        "ticket_id":      ticket_id,
        "agent_response": last_ai.content if last_ai else "",
        "severity":       result.get("severity", ""),
        "category":       result.get("issue_category", ""),
        "escalated":      result.get("escalated_to_manager", False),
        "resolved":       result.get("ticket_resolved", False),
        "steps_taken":    result.get("resolution_steps", []),
    }


@app.get("/ticket_status")
def get_ticket_status(ticket_id: str):
    """Return the latest persisted state for a ticket (non-mutating read)."""
    try:
        snapshot = graph.get_state(_config(ticket_id))
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if snapshot is None or not snapshot.values:
        raise HTTPException(status_code=404, detail=f"Ticket '{ticket_id}' not found")

    v = snapshot.values
    return {
        "ticket_id":      ticket_id,
        "customer_name":  v.get("customer_name", ""),
        "issue_category": v.get("issue_category", ""),
        "severity":       v.get("severity", ""),
        "resolved":       v.get("ticket_resolved", False),
        "escalated":      v.get("escalated_to_manager", False),
        "steps_taken":    v.get("resolution_steps", []),
        "message_count":  len(v.get("messages", [])),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # reload=False is correct for production; use reload=True only during dev
    uvicorn.run("support_agent:app", host="0.0.0.0", port=8200, reload=False)