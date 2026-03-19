"""
transaction_agent.py  (fixed)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from collections.abc import AsyncIterable
from typing import Any

import httpx
import pymysql
import uvicorn
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import (
    BasePushNotificationSender,
    InMemoryPushNotificationConfigStore,
    InMemoryTaskStore,
    TaskUpdater,
)
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    InternalError,
    InvalidParamsError,
    Part,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils import new_agent_text_message, new_task
from a2a.utils.errors import ServerError
from google.adk.agents.llm_agent import LlmAgent
from google.adk.artifacts import InMemoryArtifactService
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, Session   # ← import Session
from google.genai import types as genai_types

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────────────────

INPUT_SCHEMA = {
    "user_id":          "Unique identifier for the user (e.g. 'U-1001')",
    "user_name":        "Full name of the user",
    "user_transaction": "Transaction reference number (e.g. 'TXN-20240317-9988')",
    "user_message":     "The user's request or instruction",
    "user_sid":         "Session identifier for continuity across requests",
}

OUTPUT_SCHEMA = {
    "user_address":             "Resolved billing/shipping address for the user",
    "user_confirmation":        "Unique confirmation code for this operation",
    "user_message":             "Human-readable summary of the operation result",
    "user_transaction_message": "Detailed description of what happened with the transaction",
    "user_status":              "One of: SUCCESS | PENDING | FAILED | REQUIRES_REVIEW",
}


# ──────────────────────────────────────────────────────────────────────────────
# Tools
# ──────────────────────────────────────────────────────────────────────────────

async def verify_transaction(user_id: str, transaction_id: str) -> dict:
    """Verify whether a transaction exists and retrieve its details."""
    if transaction_id.startswith("TXN-"):
        return {
            "found": True,
            "amount": 250.00,
            "currency": "USD",
            "vendor": "Vendor XYZ",
            "status": "PENDING_CONFIRMATION",
        }
    return {"found": False, "error": f"Transaction {transaction_id} not found."}


async def get_user_address(user_id: str) -> dict:
    """Retrieve the billing address associated with a user account."""
    if user_id:
        return {
            "street": "123 Main St",
            "city": "New York",
            "state": "NY",
            "zip": "10001",
            "country": "USA",
            "formatted": "123 Main St, New York, NY 10001, USA",
        }
    return {"error": "User not found"}


async def confirm_transaction(
    user_id: str,
    transaction_id: str,
    user_name: str,
) -> dict:
    """Confirm a pending transaction and generate a confirmation code."""
    raw = f"{user_id}-{transaction_id}-{time.time()}"
    code = "CONF-" + hashlib.md5(raw.encode()).hexdigest()[:12].upper()
    return {
        "confirmation_code": code,
        "message": f"Transaction {transaction_id} confirmed for {user_name}.",
        "status": "SUCCESS",
    }


# ──────────────────────────────────────────────────────────────────────────────
# Agent instructions
# ──────────────────────────────────────────────────────────────────────────────

TRANSACTION_AGENT_INSTRUCTIONS = """
You are a Transaction Processing Assistant. Your job is to handle user
transaction requests by performing the following steps **in order**:

1. Call `verify_transaction` with the provided user_id and transaction_id.
2. If verification succeeds, call `get_user_address` with the user_id.
3. Call `confirm_transaction` with user_id, transaction_id, and user_name.
4. Assemble and return a JSON object **exactly matching** this schema – no
   extra keys, no missing keys, no markdown fences:

{
  "user_address":             "<formatted address from get_user_address>",
  "user_confirmation":        "<confirmation_code from confirm_transaction>",
  "user_message":             "<concise human-readable summary>",
  "user_transaction_message": "<detailed transaction description>",
  "user_status":              "<SUCCESS | PENDING | FAILED | REQUIRES_REVIEW>"
}

If any tool returns an error, set user_status to "FAILED" and describe the
error in user_message. Always return valid JSON – nothing else.
"""


import asyncio
import json
import logging
import queue
import threading
import uuid
from contextlib import contextmanager
from typing import Optional

import pymysql
from google.adk.events import Event
from google.adk.sessions import BaseSessionService, Session

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Thread-safe PyMySQL connection pool
# ─────────────────────────────────────────────────────────────────────────────

class _ConnectionPool:
    """
    A fixed-size pool of PyMySQL connections.
    Each checkout is exclusive to one thread — no shared-connection races.
    """

    def __init__(self, config: dict, pool_size: int = 10):
        self._config = config
        self._pool: queue.Queue = queue.Queue(maxsize=pool_size)
        for _ in range(pool_size):
            self._pool.put(self._new_conn())

    def _new_conn(self):
        return pymysql.connect(
            host=self._config["host"],
            user=self._config["user"],
            password=self._config["password"],
            database=self._config["database"],
            port=self._config.get("port", 3306),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
            connect_timeout=10,
        )

    def _ensure_alive(self, conn):
        """Ping and replace if connection is dead."""
        try:
            conn.ping(reconnect=False)
            return conn
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            return self._new_conn()

    @contextmanager
    def get(self):
        """
        Context manager — borrows a connection from the pool,
        guarantees return even on exception.

        Usage:
            with pool.get() as conn:
                with conn.cursor() as cur:
                    cur.execute(...)
        """
        conn = self._pool.get()          # blocks until one is free
        conn = self._ensure_alive(conn)
        try:
            yield conn
        except Exception:
            # On error replace the connection so we don't return a broken one
            try:
                conn.close()
            except Exception:
                pass
            conn = self._new_conn()
            raise
        finally:
            self._pool.put(conn)         # always return to pool


# ─────────────────────────────────────────────────────────────────────────────
# MySQLSessionService
# ─────────────────────────────────────────────────────────────────────────────

class MySQLSessionService(BaseSessionService):
    """
    Fully persistent, thread-safe MySQL session service for Google ADK.

    Schema
    ──────
    adk_sessions  – one row per (app_name, user_id, session_id)
                    `state` column holds the latest accumulated key-value state.

    adk_events    – one row per event appended to a session.
                    Used to replay full conversation history on get_session.

    Checkpoint behaviour
    ────────────────────
    Every call to append_event():
      1. Merges event.actions.state_delta into session.state (in-memory).
      2. Writes the updated state back to adk_sessions  (checkpoint).
      3. Inserts the serialised Event into adk_events    (history).

    On get_session() the saved state is loaded directly — no need to
    replay every event just to recover state, but the full event list is
    also attached so the LLM runner has access to conversation history.
    """

    def __init__(self, config: dict, pool_size: int = 10):
        self._pool = _ConnectionPool(config, pool_size)
        self._ensure_tables()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _ensure_tables(self) -> None:
        with self._pool.get() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS adk_sessions (
                        app_name   VARCHAR(255) NOT NULL,
                        user_id    VARCHAR(255) NOT NULL,
                        session_id VARCHAR(255) NOT NULL,
                        state      JSON NOT NULL DEFAULT (JSON_OBJECT()),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                                    ON UPDATE CURRENT_TIMESTAMP,
                        PRIMARY KEY (app_name, user_id, session_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS adk_events (
                        id         BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        app_name   VARCHAR(255) NOT NULL,
                        user_id    VARCHAR(255) NOT NULL,
                        session_id VARCHAR(255) NOT NULL,
                        event_data LONGTEXT     NOT NULL,
                        created_at TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_lookup (app_name, user_id, session_id, id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _deserialise_events(rows: list[dict]) -> list[Event]:
        events = []
        for row in rows:
            try:
                data = json.loads(row["event_data"])
                events.append(Event.model_validate(data))
            except Exception as exc:
                logger.warning("Skipping undeserialisable event: %s", exc)
        return events

    @staticmethod
    def _serialise_event(event: Event) -> str:
        try:
            return json.dumps(event.model_dump(mode="json"))
        except Exception as exc:
            logger.warning("Could not serialise event: %s", exc)
            return "{}"

    # ── create_session ────────────────────────────────────────────────────────

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: Optional[str] = None,
        state: Optional[dict] = None,
        **kwargs,
    ) -> Session:
        sid   = session_id or str(uuid.uuid4())
        state = state or {}

        def _run():
            with self._pool.get() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT IGNORE INTO adk_sessions
                            (app_name, user_id, session_id, state)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (app_name, user_id, sid, json.dumps(state)),
                    )
            logger.debug("Session created  %s/%s/%s", app_name, user_id, sid)

        await asyncio.to_thread(_run)
        return Session(app_name=app_name, user_id=user_id, id=sid, state=state)

    # ── get_session ───────────────────────────────────────────────────────────

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        **kwargs,
    ) -> Optional[Session]:
        """
        Load session + full event history from MySQL.
        State is read directly from the checkpoint column — fast & consistent.
        Events are attached so the LLM has the full conversation context.
        """

        def _run():
            with self._pool.get() as conn:          # ← own connection per call
                with conn.cursor() as cur:
                    # 1. Session header + checkpointed state
                    cur.execute(
                        """
                        SELECT app_name, user_id, session_id, state
                        FROM   adk_sessions
                        WHERE  app_name=%s AND user_id=%s AND session_id=%s
                        """,
                        (app_name, user_id, session_id),
                    )
                    row = cur.fetchone()
                    if not row:
                        return None, []

                    # 2. Full ordered event history
                    cur.execute(
                        """
                        SELECT event_data
                        FROM   adk_events
                        WHERE  app_name=%s AND user_id=%s AND session_id=%s
                        ORDER  BY id ASC
                        """,
                        (app_name, user_id, session_id),
                    )
                    event_rows = cur.fetchall()
                    return row, event_rows

        row, event_rows = await asyncio.to_thread(_run)

        if row is None:
            logger.debug("Session not found  %s/%s/%s", app_name, user_id, session_id)
            return None

        state   = json.loads(row["state"]) if row.get("state") else {}
        history = self._deserialise_events(event_rows)

        session        = Session(app_name=app_name, user_id=user_id, id=session_id, state=state)
        session.events = history

        logger.debug(
            "Session loaded  %s/%s/%s  state_keys=%s  events=%d",
            app_name, user_id, session_id, list(state.keys()), len(history),
        )
        return session

    # ── append_event  ← THE KEY CHECKPOINT METHOD ─────────────────────────────

    async def append_event(self, session: Session, event: Event) -> Event:
        """
        Called by the ADK runner after EVERY agent turn.

        Step 1 – Apply state_delta to in-memory session.state  (checkpoint merge).
        Step 2 – Persist updated state → adk_sessions           (checkpoint write).
        Step 3 – Insert serialised event → adk_events           (history write).

        After this, the next get_session() will return the full updated state
        AND the complete event history — giving the agent its prior context.
        """

        # ── Step 1: merge state delta ────────────────────────────────────────
        if event.actions and event.actions.state_delta:
            session.state.update(event.actions.state_delta)
            logger.debug(
                "State delta merged  session=%s  delta=%s",
                session.id, event.actions.state_delta,
            )

        serialised    = self._serialise_event(event)
        current_state = json.dumps(session.state)   # snapshot before thread hand-off

        def _run():
            with self._pool.get() as conn:          # ← own connection per call
                with conn.cursor() as cur:
                    # ── Step 2: checkpoint state ─────────────────────────────
                    cur.execute(
                        """
                        UPDATE adk_sessions
                        SET    state = %s
                        WHERE  app_name=%s AND user_id=%s AND session_id=%s
                        """,
                        (current_state, session.app_name, session.user_id, session.id),
                    )
                    # ── Step 3: append event history ─────────────────────────
                    cur.execute(
                        """
                        INSERT INTO adk_events
                            (app_name, user_id, session_id, event_data)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (session.app_name, session.user_id, session.id, serialised),
                    )
            logger.debug(
                "Event persisted  session=%s  state_keys=%s",
                session.id, list(json.loads(current_state).keys()),
            )

        await asyncio.to_thread(_run)

        # Keep in-memory list in sync
        session.events = getattr(session, "events", None) or []
        session.events.append(event)

        return event

    # ── delete_session ────────────────────────────────────────────────────────

    async def delete_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        **kwargs,
    ) -> None:
        def _run():
            with self._pool.get() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM adk_events WHERE app_name=%s AND user_id=%s AND session_id=%s",
                        (app_name, user_id, session_id),
                    )
                    cur.execute(
                        "DELETE FROM adk_sessions WHERE app_name=%s AND user_id=%s AND session_id=%s",
                        (app_name, user_id, session_id),
                    )

        await asyncio.to_thread(_run)
        logger.debug("Session deleted  %s/%s/%s", app_name, user_id, session_id)

    # ── list_sessions ─────────────────────────────────────────────────────────

    async def list_sessions(
        self,
        *,
        app_name: str,
        user_id: str,
        **kwargs,
    ) -> list[Session]:
        def _run():
            with self._pool.get() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT app_name, user_id, session_id, state
                        FROM   adk_sessions
                        WHERE  app_name=%s AND user_id=%s
                        ORDER  BY created_at ASC
                        """,
                        (app_name, user_id),
                    )
                    return cur.fetchall()

        rows = await asyncio.to_thread(_run)
        return [
            Session(
                app_name=r["app_name"],
                user_id=r["user_id"],
                id=r["session_id"],
                state=json.loads(r["state"]) if r.get("state") else {},
            )
            for r in rows
        ]

# ## How checkpoint / conversation continuity now works
# ```
# Request 1  (session_id = "abc")
# ──────────────────────────────
# create_session("abc")  →  INSERT into adk_sessions  (state = {})
# runner calls append_event() per turn:
#   • state_delta {"last_txn": "TXN-001"} merged into session.state
#   • UPDATE adk_sessions SET state = '{"last_txn":"TXN-001"}'
#   • INSERT into adk_events  (full event JSON)

# Request 2  (same session_id = "abc")
# ──────────────────────────────────────
# get_session("abc")
#   • SELECT from adk_sessions  → state = {"last_txn":"TXN-001"}  ✅ restored
#   • SELECT from adk_events    → all prior turns attached as session.events ✅
# Agent has full prior context — acts as a true checkpoint.

class TransactionAgent:
    """Google ADK-powered transaction processing agent."""

    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self):
        self._agent = self._build_agent()
        self._user_id = "transaction_user"
        self._runner = Runner(
            app_name=self._agent.name,
            agent=self._agent,
            artifact_service=InMemoryArtifactService(),
            session_service=MySQLSessionService({
                "host":     os.getenv("DB_HOST", "localhost"),
                "user":     os.getenv("DB_USER", "root"),
                "password": os.getenv("DB_PASSWORD", "Maxis@123"),
                "database": os.getenv("DB_NAME", "google_adk_db"),
            }),
        )

    def _build_agent(self) -> LlmAgent:
        model_name = os.getenv("TRANSACTION_MODEL", "gpt-4o")
        return LlmAgent(
            model=LiteLlm(model=model_name),
            name="transaction_agent",
            description="Verifies, addresses, and confirms user transactions.",
            instruction=TRANSACTION_AGENT_INSTRUCTIONS,
            tools=[verify_transaction, get_user_address, confirm_transaction],
        )

    def _build_prompt(self, payload: dict) -> str:
        return (
            f"Process the following transaction request:\n"
            f"- user_id: {payload.get('user_id', 'UNKNOWN')}\n"
            f"- user_name: {payload.get('user_name', 'UNKNOWN')}\n"
            f"- user_transaction: {payload.get('user_transaction', 'UNKNOWN')}\n"
            f"- user_sid: {payload.get('user_sid', 'UNKNOWN')}\n"
            f"- user_message: {payload.get('user_message', '')}\n\n"
            f"Follow the steps in your instructions and return ONLY the JSON output."
        )

    
    async def stream_working(
        self, query: str | dict, context_id: str
    ) -> AsyncIterable[dict[str, Any]]:
        # ── Normalise input ──────────────────────────────────────────────────
        if isinstance(query, dict):
            prompt = self._build_prompt(query)
        else:
            try:
                prompt = self._build_prompt(json.loads(query))
            except (json.JSONDecodeError, TypeError):
                prompt = query

        # ── Session management ───────────────────────────────────────────────
        # FIX: always pass app_name + user_id so the composite key is correct.
        session_service = self._runner.session_service
        session = await session_service.get_session(
            app_name=self._agent.name,
            user_id=self._user_id,
            session_id=context_id,
        )

        if session is None:
            session = await session_service.create_session(
                app_name=self._agent.name,
                user_id=self._user_id,
                session_id=context_id,
                state={},
            )

        # FIX: use session.id (the real ADK Session attribute), not session["session_id"]
        content = genai_types.Content(
            role="user",
            parts=[genai_types.Part.from_text(text=prompt)],
        )

        async for event in self._runner.run_async(
            user_id=self._user_id,
            session_id=session.id,       # ← session.id, not session.get(...)
            new_message=content,
        ):
            if event.is_final_response():
                response_text = ""
                if event.content and event.content.parts:
                    texts = [p.text for p in event.content.parts if p.text]
                    response_text = "\n".join(texts)

                    if not response_text:
                        for part in event.content.parts:
                            if part.function_response:
                                response_text = json.dumps(
                                    part.function_response.model_dump()
                                )
                                break

                yield {
                    "is_task_complete": True,
                    "require_user_input": False,
                    "content": self._ensure_output_schema(response_text),
                }
                break
            else:
                yield {
                    "is_task_complete": False,
                    "require_user_input": False,
                    "content": "Processing your transaction request...",
                }

    def _ensure_output_schema(self, raw: str) -> str:
        required_keys = set(OUTPUT_SCHEMA.keys())
        cleaned = (
            raw.strip()
            .removeprefix("```json")
            .removeprefix("```")
            .removesuffix("```")
            .strip()
        )

        try:
            data: dict = json.loads(cleaned)
        except json.JSONDecodeError:
            data = {
                "user_address": "",
                "user_confirmation": "",
                "user_message": raw,
                "user_transaction_message": "",
                "user_status": "FAILED",
            }

        defaults = {
            "user_address": "",
            "user_confirmation": "",
            "user_message": "Operation completed.",
            "user_transaction_message": "",
            "user_status": "PENDING",
        }
        for key in required_keys:
            data.setdefault(key, defaults[key])

        return json.dumps({k: data[k] for k in required_keys}, indent=2)
    async def stream(
                self, query: str | dict, context_id: str
            ) -> AsyncIterable[dict[str, Any]]:
    # ── Normalise input ──────────────────────────────────────────────────
        if isinstance(query, dict):
            payload = query
            prompt  = self._build_prompt(query)
            print(f"prompt: {prompt}  and  payload: {payload}")
        else:
            try:
                payload = json.loads(query)
                prompt  = self._build_prompt(payload)
                print(f"prompt: {prompt}  and  payload: {payload}")
            except (json.JSONDecodeError, TypeError):
                payload = {}
                prompt  = query

        # ── Use user_sid as the stable ADK session key ───────────────────────
        # task.context_id changes every A2A request — user_sid is caller-controlled
        # and stays the same across requests, giving true session continuity.
        user_sid   = payload.get("user_sid") or context_id
        session_id = user_sid                              # ← THE KEY CHANGE

        logger.info(
            "stream()  context_id=%s  user_sid=%s  → adk_session=%s",
            context_id, payload.get("user_sid"), session_id,
        )

        # ── Session management ───────────────────────────────────────────────
        session_service = self._runner.session_service
        session = await session_service.get_session(
            app_name=self._agent.name,
            user_id=self._user_id,
            session_id=session_id,
        )

        if session is None:
            logger.info("No existing session — creating  session_id=%s", session_id)
            session = await session_service.create_session(
                app_name=self._agent.name,
                user_id=self._user_id,
                session_id=session_id,
                state={},
            )
        else:
            logger.info(
                "Resuming session  session_id=%s  prior_events=%d  state=%s",
                session_id, len(session.events or []), session.state,
            )

        content = genai_types.Content(
            role="user",
            parts=[genai_types.Part.from_text(text=prompt)],
        )

        async for event in self._runner.run_async(
            user_id=self._user_id,
            session_id=session.id,
            new_message=content,
        ):
            if event.is_final_response():
                response_text = ""
                if event.content and event.content.parts:
                    texts = [p.text for p in event.content.parts if p.text]
                    response_text = "\n".join(texts)

                    if not response_text:
                        for part in event.content.parts:
                            if part.function_response:
                                response_text = json.dumps(
                                    part.function_response.model_dump()
                                )
                                break

                yield {
                    "is_task_complete": True,
                    "require_user_input": False,
                    "content": self._ensure_output_schema(response_text),
                }
                break
            else:
                yield {
                    "is_task_complete": False,
                    "require_user_input": False,
                    "content": "Processing your transaction request...",
                }


# ──────────────────────────────────────────────────────────────────────────────
# A2A Executor  (unchanged logic, cleaned up)
# ──────────────────────────────────────────────────────────────────────────────

class TransactionAgentExecutor(AgentExecutor):

    def __init__(self):
        self.agent = TransactionAgent()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if self._validate_request(context):
            raise ServerError(error=InvalidParamsError())

        raw_input: str = context.get_user_input()
        try:
            query: str | dict = json.loads(raw_input)
        except (json.JSONDecodeError, TypeError):
            query = raw_input

        task = context.current_task
        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.context_id)

        try:
            async for item in self.agent.stream(query, task.context_id):
                if not item["is_task_complete"] and not item["require_user_input"]:
                    await updater.update_status(
                        TaskState.working,
                        new_agent_text_message(item["content"], task.context_id, task.id),
                    )
                elif item["require_user_input"]:
                    await updater.update_status(
                        TaskState.input_required,
                        new_agent_text_message(item["content"], task.context_id, task.id),
                        final=True,
                    )
                    break
                else:
                    await updater.add_artifact(
                        [Part(root=TextPart(text=item["content"]))],
                        name="transaction_result",
                    )
                    await updater.complete()
                    break

        except Exception as exc:
            logger.error("TransactionAgentExecutor error: %s", exc, exc_info=True)
            raise ServerError(error=InternalError()) from exc

    def _validate_request(self, context: RequestContext) -> bool:
        """Return True if the request is invalid (empty body)."""
        raw = context.get_user_input()
        return not raw or not raw.strip()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise ServerError(error=UnsupportedOperationError())


# ──────────────────────────────────────────────────────────────────────────────
# A2A Server
# ──────────────────────────────────────────────────────────────────────────────

HOST = os.getenv("HOST", "localhost")
PORT = int(os.getenv("PORT", "8072"))

transaction_skill = AgentSkill(
    id="transaction_processing",
    name="Transaction Processing Tool",
    description=(
        "Accepts structured user + transaction data (JSON), verifies the "
        "transaction, resolves the user address, and returns a structured "
        "confirmation response (JSON)."
    ),
    tags=["transaction", "payment", "confirmation", "verification"],
    examples=[
        json.dumps({
            "user_id": "U-1001",
            "user_name": "Alice Johnson",
            "user_transaction": "TXN-20240317-9988",
            "user_message": "Please verify and confirm my transaction.",
            "user_sid": "SESSION-XYZ-001",
        }),
    ],
)

transaction_agent_card = AgentCard(
    name="Transaction Agent",
    description="Structured JSON-in / JSON-out agent for transaction verification and confirmation.",
    url=f"http://{HOST}:{PORT}/",
    version="1.0.0",
    default_input_modes=["text", "text/plain"],
    default_output_modes=["text", "text/plain"],
    capabilities=AgentCapabilities(streaming=True, push_notifications=False),
    skills=[transaction_skill],
)

_httpx_client       = httpx.AsyncClient()
_push_config_store  = InMemoryPushNotificationConfigStore()
_push_sender        = BasePushNotificationSender(
    httpx_client=_httpx_client,
    config_store=_push_config_store,
)
_task_store = InMemoryTaskStore()

transaction_handler = DefaultRequestHandler(
    agent_executor=TransactionAgentExecutor(),
    task_store=_task_store,
    push_config_store=_push_config_store,
    push_sender=_push_sender,
)

transaction_app = A2AStarletteApplication(
    agent_card=transaction_agent_card,
    http_handler=transaction_handler,
)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting Transaction Agent on http://%s:%d", HOST, PORT)
    uvicorn.run(transaction_app.build(), host=HOST, port=PORT)