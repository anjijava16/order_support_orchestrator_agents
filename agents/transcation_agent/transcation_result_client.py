"""
transaction_client.py
======================
A2A Client example for the Transaction Agent.

Demonstrates three usage patterns:
  1. Single request  – fire-and-forget, wait for final result
  2. Streaming       – receive intermediate working events + final result
  3. Batch           – send multiple transactions concurrently

Run the server first:
    python transaction_agent.py

Then run this client:
    python transaction_client.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

AGENT_BASE_URL = "http://localhost:8072"

# A2A JSON-RPC endpoints
JSONRPC_ENDPOINT   = f"{AGENT_BASE_URL}/"          # tasks/send  (non-streaming)
STREAMING_ENDPOINT = f"{AGENT_BASE_URL}/"          # tasks/sendSubscribe  (SSE)
AGENT_CARD_URL     = f"{AGENT_BASE_URL}/.well-known/agent.json"

TIMEOUT = httpx.Timeout(60.0, connect=10.0)


# ──────────────────────────────────────────────────────────────────────────────
# Typed helpers
# ──────────────────────────────────────────────────────────────────────────────

def make_input_payload(
    user_id: str,
    user_name: str,
    user_transaction: str,
    user_message: str,
    user_sid: str | None = None,
) -> dict[str, str]:
    """Build the structured JSON input that the Transaction Agent expects."""
    return {
        "user_id":          user_id,
        "user_name":        user_name,
        "user_transaction": user_transaction,
        "user_message":     user_message,
        "user_sid":         user_sid or str(uuid.uuid4()),
    }


def build_jsonrpc_request(
    method: str,
    payload: dict,
    message_id: str | None = None,
) -> dict:
    """Wrap an input payload in a JSON-RPC 2.0 envelope."""
    return {
        "jsonrpc": "2.0",
        "id":      message_id or str(uuid.uuid4()),
        "method":  method,
        "params": {
            "message": {
                "role":  "user",
                "parts": [
                    {
                        "kind": "text",
                        # The agent expects the input as a JSON *string*
                        "text": json.dumps(payload),
                    }
                ],
                "messageId": str(uuid.uuid4()),
            }
        },
    }


def extract_output(response_json: dict) -> dict[str, Any]:
    """
    Pull the structured JSON output out of a tasks/send response.

    The agent stores its result in:
        result.artifacts[0].parts[0].text   (JSON string → OUTPUT_SCHEMA)
    """
    try:
        result    = response_json["result"]
        artifacts = result.get("artifacts", [])
        if artifacts:
            text = artifacts[0]["parts"][0]["text"]
            return json.loads(text)

        # Fall back to status message
        status_msg = (
            result.get("status", {})
                  .get("message", {})
                  .get("parts", [{}])[0]
                  .get("text", "")
        )
        return {"raw": status_msg}

    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        return {"error": f"Could not parse response: {exc}", "raw": response_json}


def pretty(data: dict) -> str:
    return json.dumps(data, indent=2)


# ──────────────────────────────────────────────────────────────────────────────
# Pattern 1 – Single blocking request  (tasks/send)
# ──────────────────────────────────────────────────────────────────────────────

async def send_single_request(payload: dict) -> dict[str, Any]:
    """
    Send one transaction request and block until the agent returns a result.
    Returns the parsed OUTPUT_SCHEMA dict.
    """
    rpc_body = build_jsonrpc_request("message/send", payload)

    logger.info("──── [SINGLE] Sending request ────────────────────────────")
    logger.info("INPUT:\n%s", pretty(payload))

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            JSONRPC_ENDPOINT,
            json=rpc_body,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()

    result = extract_output(response.json())

    logger.info("OUTPUT:\n%s", pretty(result))
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Pattern 2 – Streaming request  (tasks/sendSubscribe via SSE)
# ──────────────────────────────────────────────────────────────────────────────

async def send_streaming_request(payload: dict) -> dict[str, Any]:
    """
    Send one transaction request and consume Server-Sent Events (SSE).

    Prints intermediate "working" events and returns the final OUTPUT_SCHEMA dict.
    """
    rpc_body = build_jsonrpc_request("message/stream", payload)

    logger.info("──── [STREAM] Sending request ────────────────────────────")
    logger.info("INPUT:\n%s", pretty(payload))

    final_output: dict[str, Any] = {}
    event_count = 0

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        async with client.stream(
            "POST",
            STREAMING_ENDPOINT,
            json=rpc_body,
            headers={
                "Content-Type": "application/json",
                "Accept":        "text/event-stream",
            },
        ) as stream:
            async for raw_line in stream.aiter_lines():
                if not raw_line.startswith("data:"):
                    continue

                data_str = raw_line[len("data:"):].strip()
                if not data_str or data_str == "[DONE]":
                    break

                try:
                    event = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                event_count += 1
                result = event.get("result", {})
                state  = result.get("status", {}).get("state", "")

                if state == "working":
                    # Intermediate progress message
                    msg_parts = (
                        result.get("status", {})
                              .get("message", {})
                              .get("parts", [{}])
                    )
                    progress_text = msg_parts[0].get("text", "") if msg_parts else ""
                    logger.info("[EVENT %d] working → %s", event_count, progress_text)

                elif state == "completed":
                    # Final result – extract artifact
                    artifacts = result.get("artifacts", [])
                    if artifacts:
                        text = artifacts[0]["parts"][0]["text"]
                        try:
                            final_output = json.loads(text)
                        except json.JSONDecodeError:
                            final_output = {"raw": text}

                    logger.info("[EVENT %d] completed", event_count)
                    break

                elif state in ("failed", "input_required"):
                    logger.warning("[EVENT %d] terminal state: %s", event_count, state)
                    break

    logger.info("OUTPUT:\n%s", pretty(final_output))
    return final_output


# ──────────────────────────────────────────────────────────────────────────────
# Pattern 3 – Batch / concurrent requests
# ──────────────────────────────────────────────────────────────────────────────

async def send_batch(payloads: list[dict]) -> list[dict[str, Any]]:
    """
    Send multiple transaction requests concurrently and return all results.
    """
    logger.info("──── [BATCH] Sending %d requests concurrently ────────────", len(payloads))

    tasks = [send_single_request(p) for p in payloads]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, (payload, result) in enumerate(zip(payloads, results)):
        if isinstance(result, Exception):
            logger.error("Batch[%d] FAILED – %s", i, result)
        else:
            logger.info(
                "Batch[%d] %s → status=%s  confirmation=%s",
                i,
                payload["user_transaction"],
                result.get("user_status"),
                result.get("user_confirmation"),
            )

    return [r for r in results if not isinstance(r, Exception)]


# ──────────────────────────────────────────────────────────────────────────────
# Utility – fetch the Agent Card (service discovery)
# ──────────────────────────────────────────────────────────────────────────────

async def fetch_agent_card() -> dict:
    """
    Retrieve the Agent Card from the well-known URL.
    The Agent Card describes the agent's skills, capabilities, and I/O modes.
    """
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(AGENT_CARD_URL)
        response.raise_for_status()
    card = response.json()
    logger.info("──── Agent Card ──────────────────────────────────────────")
    logger.info(pretty(card))
    return card


# ──────────────────────────────────────────────────────────────────────────────
# Demo runner
# ──────────────────────────────────────────────────────────────────────────────

async def main() -> None:

    # ── 0. Discover what the agent can do ───────────────────────────
    await fetch_agent_card()

    # ── 1. Single request ───────────────────────────────────────────
    single_payload = make_input_payload(
        user_id          = "U-1001",
        user_name        = "Alice Johnson",
        user_transaction = "TXN-20240317-9988",
        user_message     = "Please verify and confirm my transaction.",
        user_sid         = "SESSION-XYZ-001",
    )
    single_result = await send_single_request(single_payload)

    # Access individual output fields
    print("\n── Single Result ──────────────────────────────────────────")
    print(f"  user_address:             {single_result.get('user_address')}")
    print(f"  user_confirmation:        {single_result.get('user_confirmation')}")
    print(f"  user_message:             {single_result.get('user_message')}")
    print(f"  user_transaction_message: {single_result.get('user_transaction_message')}")
    print(f"  user_status:              {single_result.get('user_status')}")

    # ── 2. Streaming request ────────────────────────────────────────
    streaming_payload = make_input_payload(
        user_id          = "U-2002",
        user_name        = "Bob Smith",
        user_transaction = "TXN-20240318-1122",
        user_message     = "Confirm my payment please.",
        user_sid         = "SESSION-BOB-002",
    )
    streaming_result = await send_streaming_request(streaming_payload)

    print("\n── Streaming Result ───────────────────────────────────────")
    print(f"  user_status:       {streaming_result.get('user_status')}")
    print(f"  user_confirmation: {streaming_result.get('user_confirmation')}")

    # ── 3. Batch / concurrent ───────────────────────────────────────
    batch_payloads = [
        make_input_payload("U-3001", "Carol White",  "TXN-BATCH-0001", "Process batch transaction 1"),
        make_input_payload("U-3002", "David Brown",  "TXN-BATCH-0002", "Process batch transaction 2"),
        make_input_payload("U-3003", "Eva Martinez", "TXN-BATCH-0003", "Process batch transaction 3"),
    ]
    batch_results = await send_batch(batch_payloads)

    print("\n── Batch Results ──────────────────────────────────────────")
    for i, r in enumerate(batch_results):
        print(f"  [{i}] status={str(r.get('user_status')):<10}  conf={r.get('user_confirmation')}")


if __name__ == "__main__":
    asyncio.run(main())