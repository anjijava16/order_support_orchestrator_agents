"""
transaction_agent.py
=====================
A2A + Google ADK example that accepts structured JSON input and returns
structured JSON output.

Expected INPUT  (from user / orchestrator):
{
    "user_id":          "U-1001",
    "user_name":        "Alice Johnson",
    "user_transaction": "TXN-20240317-9988",
    "user_message":     "Verify and confirm my transaction",
    "user_sid":         "SESSION-XYZ-001"
}

Expected OUTPUT (returned as artifact):
{
    "user_address":              "123 Main St, New York, NY 10001",
    "user_confirmation":         "CONF-20240317-ABC123",
    "user_message":              "Transaction verified and confirmed successfully.",
    "user_transaction_message":  "Payment of $250.00 to Vendor XYZ processed.",
    "user_status":               "SUCCESS"
}
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterable
from typing import Any

import httpx
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
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Pydantic-style input / output schemas (plain dataclasses for clarity)
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
# Tools – async functions that the LLM agent can call
# ──────────────────────────────────────────────────────────────────────────────

async def verify_transaction(user_id: str, transaction_id: str) -> dict:
    """
    Verify whether a transaction exists and retrieve its details.

    Args:
        user_id:        The ID of the user who owns the transaction.
        transaction_id: The transaction reference number to verify.

    Returns:
        A dict with keys: found (bool), amount, currency, vendor, status.
    """
    # --- Replace with a real API call ---
    # async with httpx.AsyncClient() as client:
    #     resp = await client.get(
    #         "https://api.example.com/transactions/verify",
    #         params={"user_id": user_id, "txn_id": transaction_id},
    #     )
    #     resp.raise_for_status()
    #     return resp.json()

    # Simulated response for demonstration
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
    """
    Retrieve the billing address associated with a user account.

    Args:
        user_id: The user's unique identifier.

    Returns:
        A dict with address fields: street, city, state, zip, country.
    """
    # --- Replace with a real API call ---
    # Simulated response
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
    """
    Confirm (authorise) a pending transaction and generate a confirmation code.

    Args:
        user_id:        The user's unique identifier.
        transaction_id: The transaction to confirm.
        user_name:      The user's full name (used for receipt).

    Returns:
        A dict with: confirmation_code, message, status.
    """
    # --- Replace with a real API call ---
    import hashlib, time  # noqa: E401

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


# ──────────────────────────────────────────────────────────────────────────────
# TransactionAgent  (mirrors ShippingAgent pattern from the reference code)
# ──────────────────────────────────────────────────────────────────────────────

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
            session_service=InMemorySessionService(),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_agent(self) -> LlmAgent:
        model_name = os.getenv("TRANSACTION_MODEL", "gpt-4o")
        return LlmAgent(
            model=LiteLlm(model=model_name),
            name="transaction_agent",
            description="Verifies, addresses, and confirms user transactions.",
            instruction=TRANSACTION_AGENT_INSTRUCTIONS,
            tools=[
                verify_transaction,
                get_user_address,
                confirm_transaction,
            ],
        )

    def _build_prompt(self, payload: dict) -> str:
        """
        Convert the structured JSON input into a natural-language prompt
        that the agent understands, while preserving all field values.
        """
        return (
            f"Process the following transaction request:\n"
            f"- user_id: {payload.get('user_id', 'UNKNOWN')}\n"
            f"- user_name: {payload.get('user_name', 'UNKNOWN')}\n"
            f"- user_transaction: {payload.get('user_transaction', 'UNKNOWN')}\n"
            f"- user_sid: {payload.get('user_sid', 'UNKNOWN')}\n"
            f"- user_message: {payload.get('user_message', '')}\n\n"
            f"Follow the steps in your instructions and return ONLY the JSON output."
        )

    # ------------------------------------------------------------------
    # Public streaming interface (same contract as ShippingAgent.stream)
    # ------------------------------------------------------------------

    async def stream(
        self, query: str | dict, context_id: str
    ) -> AsyncIterable[dict[str, Any]]:
        """
        Stream agent responses.

        `query` may be either:
          - a raw string (legacy / plain-text callers)
          - a dict matching INPUT_SCHEMA  (structured callers)

        Yields dicts: {is_task_complete, require_user_input, content}
        where `content` on completion is a JSON string matching OUTPUT_SCHEMA.
        """
        # ── Normalise input ──────────────────────────────────────────
        if isinstance(query, dict):
            prompt = self._build_prompt(query)
        else:
            # Try to parse as JSON; fall back to plain text
            try:
                payload = json.loads(query)
                prompt = self._build_prompt(payload)
            except (json.JSONDecodeError, TypeError):
                prompt = query  # plain-text fallback

        # ── Session management ───────────────────────────────────────
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
            )

        content = genai_types.Content(
            role="user",
            parts=[genai_types.Part.from_text(text=prompt)],
        )

        # ── Run agent and stream events ──────────────────────────────
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

                # ── Validate / wrap output to guarantee OUTPUT_SCHEMA ─
                response_text = self._ensure_output_schema(response_text)

                yield {
                    "is_task_complete": True,
                    "require_user_input": False,
                    "content": response_text,
                }
                break
            else:
                yield {
                    "is_task_complete": False,
                    "require_user_input": False,
                    "content": "Processing your transaction request...",
                }

    # ------------------------------------------------------------------
    # Output schema enforcement
    # ------------------------------------------------------------------

    def _ensure_output_schema(self, raw: str) -> str:
        """
        Parse the agent's raw text output and guarantee that the returned
        JSON contains exactly the keys defined in OUTPUT_SCHEMA.
        Missing keys are filled with sensible defaults.
        """
        required_keys = set(OUTPUT_SCHEMA.keys())

        # Strip markdown fences if present
        cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

        try:
            data: dict = json.loads(cleaned)
        except json.JSONDecodeError:
            # Agent returned plain text – wrap it
            data = {
                "user_address": "",
                "user_confirmation": "",
                "user_message": raw,
                "user_transaction_message": "",
                "user_status": "FAILED",
            }

        # Fill any missing keys
        defaults = {
            "user_address": "",
            "user_confirmation": "",
            "user_message": "Operation completed.",
            "user_transaction_message": "",
            "user_status": "PENDING",
        }
        for key in required_keys:
            data.setdefault(key, defaults[key])

        # Remove any extra keys the agent might have added
        data = {k: data[k] for k in required_keys}

        return json.dumps(data, indent=2)


# ──────────────────────────────────────────────────────────────────────────────
# A2A Executor
# ──────────────────────────────────────────────────────────────────────────────

class TransactionAgentExecutor(AgentExecutor):
    """
    Bridges the A2A request lifecycle with TransactionAgent.

    Input  – the A2A message text is expected to be a JSON string
             matching INPUT_SCHEMA (or a plain string for backward-compat).
    Output – artifact text is a JSON string matching OUTPUT_SCHEMA.
    """

    def __init__(self):
        self.agent = TransactionAgent()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        error = self._validate_request(context)
        if error:
            raise ServerError(error=InvalidParamsError())

        # ── Extract raw text; try to parse as structured JSON ─────────
        raw_input: str = context.get_user_input()
        try:
            query: str | dict = json.loads(raw_input)  # structured path
        except (json.JSONDecodeError, TypeError):
            query = raw_input  # plain-text path

        task = context.current_task
        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.context_id)

        try:
            async for item in self.agent.stream(query, task.context_id):
                is_complete = item["is_task_complete"]
                needs_input = item["require_user_input"]

                if not is_complete and not needs_input:
                    # Intermediate progress event
                    await updater.update_status(
                        TaskState.working,
                        new_agent_text_message(
                            item["content"],
                            task.context_id,
                            task.id,
                        ),
                    )
                elif needs_input:
                    await updater.update_status(
                        TaskState.input_required,
                        new_agent_text_message(
                            item["content"],
                            task.context_id,
                            task.id,
                        ),
                        final=True,
                    )
                    break
                else:
                    # Final structured JSON result
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
        """Return True if the request is invalid."""
        raw = context.get_user_input()
        if not raw or not raw.strip():
            return True  # empty input → invalid

        try:
            payload = json.loads(raw)
            # Require at minimum user_id and user_transaction
            required = {"user_id", "user_transaction"}
            if not required.issubset(payload.keys()):
                logger.warning(
                    "Missing required fields. Got: %s", list(payload.keys())
                )
                # Not a hard failure – agent will handle gracefully
        except (json.JSONDecodeError, TypeError):
            pass  # plain-text input is still allowed

        return False  # always proceed; let the agent handle edge cases

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        raise ServerError(error=UnsupportedOperationError())


# ──────────────────────────────────────────────────────────────────────────────
# A2A Server setup
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
        # Callers should send JSON strings like these:
        json.dumps({
            "user_id": "U-1001",
            "user_name": "Alice Johnson",
            "user_transaction": "TXN-20240317-9988",
            "user_message": "Please verify and confirm my transaction.",
            "user_sid": "SESSION-XYZ-001",
        }),
        json.dumps({
            "user_id": "U-2002",
            "user_name": "Bob Smith",
            "user_transaction": "TXN-20240318-1122",
            "user_message": "Confirm payment",
            "user_sid": "SESSION-ABC-002",
        }),
    ],
)

transaction_capabilities = AgentCapabilities(
    streaming=True,
    push_notifications=False,
)

transaction_agent_card = AgentCard(
    name="Transaction Agent",
    description=(
        "Structured JSON-in / JSON-out agent for transaction verification "
        "and confirmation."
    ),
    url=f"http://{HOST}:{PORT}/",
    version="1.0.0",
    default_input_modes=["text", "text/plain"],
    default_output_modes=["text", "text/plain"],
    capabilities=transaction_capabilities,
    skills=[transaction_skill],
)

# Shared infrastructure
_httpx_client = httpx.AsyncClient()
_push_config_store = InMemoryPushNotificationConfigStore()
_push_sender = BasePushNotificationSender(
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

# ──────────────────────────────────────────────────────────────────────────────
# Entry-point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting Transaction Agent on http://%s:%d", HOST, PORT)
    uvicorn.run(transaction_app.build(), host=HOST, port=PORT)