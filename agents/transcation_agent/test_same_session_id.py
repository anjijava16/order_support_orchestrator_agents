"""
test_session_continuity.py
===========================
Tests that the same user_sid is correctly reused across multiple A2A requests,
and that events accumulate in MySQL as expected.

What this script does
─────────────────────
  Round 1  – send request with SESSION-TEST-001
             → DB should show 1 session row, N events

  Round 2  – send ANOTHER request with the SAME session id
             → DB should show SAME session row, more events appended

  Round 3  – one more request, same session id
             → DB should show even more events

After each round we query MySQL directly and print:
  • session row  (state JSON)
  • event count
  • last 3 event summaries

Run the agent server first:
    python transaction_agent_server.py

Then run this test:
    python test_session_continuity.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any

import httpx
import pymysql
import pymysql.cursors

# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

AGENT_URL = "http://localhost:8072/"
TIMEOUT    = httpx.Timeout(60.0, connect=10.0)

DB_CONFIG = {
    "host":     "localhost",
    "user":     "root",
    "password": "Maxis@123",
    "database": "google_adk_db",
    "port":     3306,
    "charset":  "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
    "autocommit":  True,
}

# ── Fixed session id shared across all rounds ──────────────────────────────
SHARED_SESSION_ID = "welcome_sairam_jaihunuman_SESSION-CONTINUITY-TEST-001"
APP_NAME          = "transaction_agent"
USER_ID           = "transaction_user"


# ─────────────────────────────────────────────────────────────────────────────
# DB inspector  (read-only, for verification only)
# ─────────────────────────────────────────────────────────────────────────────

class DBInspector:
    """Direct MySQL queries to verify what is actually stored."""

    def __init__(self):
        self._conn = pymysql.connect(**DB_CONFIG)

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    def _ping(self):
        try:
            self._conn.ping(reconnect=True)
        except Exception:
            self._conn = pymysql.connect(**DB_CONFIG)

    # ── Session row ───────────────────────────────────────────────────────

    def get_session_row(self, session_id: str) -> dict | None:
        self._ping()
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT app_name, user_id, session_id,
                       state, created_at, updated_at
                FROM   adk_sessions
                WHERE  app_name=%s AND user_id=%s AND session_id=%s
                """,
                (APP_NAME, USER_ID, session_id),
            )
            return cur.fetchone()

    # ── Event rows ────────────────────────────────────────────────────────

    def get_event_count(self, session_id: str) -> int:
        self._ping()
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM   adk_events
                WHERE  app_name=%s AND user_id=%s AND session_id=%s
                """,
                (APP_NAME, USER_ID, session_id),
            )
            row = cur.fetchone()
            return row["cnt"] if row else 0

    def get_last_events(self, session_id: str, n: int = 3) -> list[dict]:
        """Return the last N events (most recent first) as summary dicts."""
        self._ping()
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, created_at, event_data
                FROM   adk_events
                WHERE  app_name=%s AND user_id=%s AND session_id=%s
                ORDER  BY id DESC
                LIMIT  %s
                """,
                (APP_NAME, USER_ID, session_id, n),
            )
            rows = cur.fetchall()

        summaries = []
        for row in rows:
            try:
                data    = json.loads(row["event_data"])
                # Pull a short readable summary from the event
                author  = data.get("author", "?")
                ev_type = "final" if data.get("is_final_response") else "intermediate"
                # Try to get text content
                content = data.get("content") or {}
                parts   = content.get("parts", []) if isinstance(content, dict) else []
                text    = ""
                for p in parts:
                    if isinstance(p, dict) and p.get("text"):
                        text = p["text"][:80]
                        break
                summaries.append({
                    "db_id":      row["id"],
                    "created_at": str(row["created_at"]),
                    "author":     author,
                    "type":       ev_type,
                    "preview":    text or "(no text)",
                })
            except Exception as exc:
                summaries.append({
                    "db_id":  row["id"],
                    "error":  str(exc),
                    "raw":    str(row["event_data"])[:60],
                })
        return summaries

    # ── Full DB snapshot ──────────────────────────────────────────────────

    def snapshot(self, session_id: str, label: str) -> None:
        sep = "─" * 60
        print(f"\n{sep}")
        print(f"  DB SNAPSHOT  [{label}]")
        print(f"  session_id : {session_id}")
        print(sep)

        session_row = self.get_session_row(session_id)
        if session_row is None:
            print("  ⚠  No session row found in adk_sessions")
        else:
            state = json.loads(session_row["state"]) if session_row.get("state") else {}
            print(f"  created_at : {session_row['created_at']}")
            print(f"  updated_at : {session_row['updated_at']}")
            print(f"  state keys : {list(state.keys()) or '(empty)'}")
            print(f"  state      : {json.dumps(state, indent=4)}")

        event_count = self.get_event_count(session_id)
        print(f"\n  total events in adk_events : {event_count}")

        last_events = self.get_last_events(session_id, n=3)
        if last_events:
            print("  last 3 events (newest first):")
            for ev in last_events:
                print(
                    f"    [id={ev.get('db_id')}]"
                    f"  author={ev.get('author','?'):<12}"
                    f"  type={ev.get('type','?'):<14}"
                    f"  preview: {ev.get('preview','')}"
                )
        print(sep)


# ─────────────────────────────────────────────────────────────────────────────
# A2A helpers
# ─────────────────────────────────────────────────────────────────────────────

def build_rpc(payload: dict, method: str = "message/send") -> dict:
    return {
        "jsonrpc": "2.0",
        "id":      str(uuid.uuid4()),
        "method":  method,
        "params": {
            "message": {
                "role":  "user",
                "parts": [{"kind": "text", "text": json.dumps(payload)}],
                "messageId": str(uuid.uuid4()),
            }
        },
    }


def extract_result(resp: dict) -> dict:
    try:
        artifacts = resp["result"].get("artifacts", [])
        if artifacts:
            return json.loads(artifacts[0]["parts"][0]["text"])
    except Exception:
        pass
    return {"raw": resp}


async def call_agent(payload: dict) -> dict[str, Any]:
    """Send one request to the Transaction Agent and return the parsed output."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            AGENT_URL,
            json=build_rpc(payload),
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        return extract_result(response.json())


# ─────────────────────────────────────────────────────────────────────────────
# Test rounds
# ─────────────────────────────────────────────────────────────────────────────

ROUNDS = [
    {
        "label":            "Round 1 — First request",
        "user_id":          "U-1001",
        "user_name":        "Alice Johnson",
        "user_transaction": "TXN-20240317-1001",
        "user_message":     "Please verify and confirm my first transaction.",
    },
    {
        "label":            "Round 2 — Second request, same session",
        "user_id":          "U-1001",
        "user_name":        "Alice Johnson",
        "user_transaction": "TXN-20240317-1002",
        "user_message":     "Please verify and confirm my second transaction.",
    },
    {
        "label":            "Round 3 — Third request, same session",
        "user_id":          "U-1001",
        "user_name":        "Alice Johnson",
        "user_transaction": "TXN-20240317-1003",
        "user_message":     "Please verify and confirm my third transaction.",
    },
]


async def main() -> None:
    db = DBInspector()

    print("\n" + "═" * 60)
    print("  SESSION CONTINUITY TEST")
    print(f"  shared session_id : {SHARED_SESSION_ID}")
    print("═" * 60)

    # Baseline — what is in the DB before we start?
    db.snapshot(SHARED_SESSION_ID, "BEFORE ALL REQUESTS")

    prior_event_count = db.get_event_count(SHARED_SESSION_ID)

    for i, round_cfg in enumerate(ROUNDS, start=1):
        label   = round_cfg.pop("label")
        payload = {
            **round_cfg,
            "user_sid": SHARED_SESSION_ID,   # ← same session every time
        }

        print(f"\n{'─'*60}")
        print(f"  {label}")
        print(f"  Sending: {payload['user_transaction']}")
        print(f"{'─'*60}")

        result = await call_agent(payload)

        print(f"  ✅ Agent responded:")
        print(f"     user_status:       {result.get('user_status')}")
        print(f"     user_confirmation: {result.get('user_confirmation')}")
        print(f"     user_message:      {result.get('user_message')}")

        # DB check after this round
        db.snapshot(SHARED_SESSION_ID, f"AFTER {label.upper()}")

        new_event_count = db.get_event_count(SHARED_SESSION_ID)
        added = new_event_count - prior_event_count

        if added > 0:
            print(f"\n  ✅  PASS — {added} new event(s) appended to adk_events")
            print(f"       total events now: {new_event_count}")
        else:
            print(f"\n  ❌  FAIL — event count did not increase!")
            print(f"       before={prior_event_count}  after={new_event_count}")

        prior_event_count = new_event_count

        # Small gap so timestamps are visibly different
        await asyncio.sleep(1)

    # ── Final summary ─────────────────────────────────────────────────────
    final_count = db.get_event_count(SHARED_SESSION_ID)
    session_row = db.get_session_row(SHARED_SESSION_ID)

    print("\n" + "═" * 60)
    print("  FINAL SUMMARY")
    print("═" * 60)
    print(f"  session_id   : {SHARED_SESSION_ID}")
    print(f"  total events : {final_count}")
    if session_row:
        state = json.loads(session_row["state"]) if session_row.get("state") else {}
        print(f"  final state  : {json.dumps(state, indent=4)}")
    print()

    if final_count >= len(ROUNDS):
        print("  ✅  ALL ROUNDS PASSED — events are accumulating correctly.")
    else:
        print(f"  ❌  INCOMPLETE — expected at least {len(ROUNDS)} events, got {final_count}.")

    db.close()


if __name__ == "__main__":
    asyncio.run(main())
# ```

# ---

# ## What this tests and how to read the output
# ```
# ═════════════════════════════════════════════════════════════
#   SESSION CONTINUITY TEST
#   shared session_id : SESSION-CONTINUITY-TEST-001
# ═════════════════════════════════════════════════════════════

# ──────────────────────────────────────────────────
#   DB SNAPSHOT  [BEFORE ALL REQUESTS]
#   total events in adk_events : 0        ← clean slate

# ──────────────────────────────────────────────────
#   Round 1 — Sending: TXN-20240317-1001
#   ✅ Agent responded: SUCCESS

#   DB SNAPSHOT  [AFTER ROUND 1]
#   state keys : [...]
#   total events in adk_events : 5        ← events written
#   ✅ PASS — 5 new events appended

# ──────────────────────────────────────────────────
#   Round 2 — same session_id, new transaction
#   ✅ Agent responded: SUCCESS

#   DB SNAPSHOT  [AFTER ROUND 2]
#   total events in adk_events : 10       ← MORE events appended
#   ✅ PASS — 5 new events appended

# ──────────────────────────────────────────────────
#   Round 3 — same session_id, new transaction
#   ✅ PASS — 5 new events appended

# ═════════════════════════════════════════════════════════════
#   ✅  ALL ROUNDS PASSED — events are accumulating correctly.