from __future__ import annotations
# graph.py

from langgraph.graph import StateGraph, END
from custom_agents import support_agent, order_agent, refund_agent, tool_node, router
from langchain_core.messages import HumanMessage
from typing import TypedDict, List, Annotated
from langgraph.graph.message import add_messages

# # MySQL connection string
# checkpointer = SqlAlchemySaver.from_conn_string(
#     "mysql+pymysql://user:password@localhost/langgraph_db"
# )


"""
TechCorp Customer Support Agent
- LangGraph Human-in-the-Loop with interrupt()
- Custom MySQLSaver checkpointer (LangGraph has no built-in MySQL saver)
- FastAPI REST interface
"""



import json
import os
import pickle
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Annotated, Any, Iterator, Literal, Optional, Sequence, Tuple
from uuid import uuid4
from urllib.parse import unquote

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
        # URL-decode user and password to handle special characters
        user = unquote(user)
        password = unquote(password)
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

# State definition
class State(TypedDict):
    messages: Annotated[List, add_messages]
    order_id: str
    amount: float

graph = StateGraph(State)

# Add nodes
graph.add_node("support_agent", support_agent)
graph.add_node("order_agent", order_agent)
graph.add_node("refund_agent", refund_agent)
graph.add_node("tools", tool_node)

# Helper to determine if we should call tools
def should_continue(state):
    messages = state.get("messages", [])
    if not messages:
        return "end"
    last_message = messages[-1]
    # If the last message has tool calls, go to tools node
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "end"

# Helper to route to appropriate agent based on message content
def route_to_agent(state):
    messages = state.get("messages", [])
    if not messages:
        return "support_agent"
    # Check the user's message to determine which agent to route to
    user_msg = messages[0].content.lower() if hasattr(messages[0], 'content') else ""
    if "refund" in user_msg:
        return "refund_agent"
    elif "track" in user_msg or "shipping" in user_msg:
        return "order_agent"
    else:
        return "support_agent"

# Entry point: route to appropriate agent
graph.set_entry_point("support_agent")

# From each agent, check if tools were called
for agent in ["support_agent", "order_agent", "refund_agent"]:
    graph.add_conditional_edges(
        agent,
        should_continue,
        {
            "tools": "tools",
            "end": END
        }
    )

# After tools, go back to support_agent to continue
graph.add_edge("tools", "support_agent")

from urllib.parse import quote_plus
password = quote_plus("Maxis@123")

_conn_string = f"mysql+pymysql://root:{password}@localhost:3306/support_tickets_db"
import urllib.parse



password = "Maxis@123"
encoded_password = urllib.parse.quote_plus(password)
_conn_string = f"mysql+pymysql://root:{encoded_password}@localhost:3306/support_tickets_db"

print(f"Using MySQL connection string: { _conn_string }")
_conn_string = "mysql+pymysql://root:Maxis%40123@localhost:3306/support_tickets_db"
checkpointer = MySQLSaver.from_conn_string(_conn_string)
# Compile graph with MySQL persistence
app = graph.compile(checkpointer=checkpointer)