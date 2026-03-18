# =============================================================================
# router.py — Intelligent Router Node
# =============================================================================
#
#  The router is the brain of the graph. Given the user's message it decides:
#    • WHICH agent(s) to call  (can be 1 or many)
#    • What the INTENT is
#    • Whether to short-circuit directly to human review
#
#  We use keyword-based routing here so the demo runs without an API key.
#  Swap in an LLM call (see the commented section) for production use.
#
# =============================================================================

import re
from typing import List
from state import AgentState, AgentName


# ---------------------------------------------------------------------------
# Rule-based routing table
#   Each row = (keywords,  agents_to_invoke)
#   Rules are checked in order; ALL matching rules fire (multi-agent support).
# ---------------------------------------------------------------------------
ROUTING_RULES: List[tuple[List[str], List[AgentName]]] = [
    # ── Refund keywords ──────────────────────────────────────────────────────
    (["refund", "money back", "reimburse", "reimbursement", "return"],
     ["refund_agent"]),

    # ── Payment keywords ─────────────────────────────────────────────────────
    (["payment", "pay", "invoice", "receipt", "bill", "charged", "charge",
      "transaction", "credit card", "debit card", "declined", "failed payment"],
     ["payment_agent"]),

    # ── Delivery keywords ────────────────────────────────────────────────────
    (["delivery", "deliver", "arrive", "arrived", "missing", "not received",
      "delay", "delayed", "reschedule", "schedule delivery"],
     ["delivery_agent"]),

    # ── Shipping keywords ────────────────────────────────────────────────────
    (["shipping", "shipped", "tracking", "track", "carrier", "label",
      "ship", "shipment", "usps", "fedex", "ups", "dhl"],
     ["shipping_agent"]),

    # ── Order keywords ───────────────────────────────────────────────────────
    (["order", "purchase", "buy", "bought", "cancel", "cancelled",
      "modify order", "change order", "order status", "order id"],
     ["order_agent"]),
]

# Keywords that ALWAYS require human review regardless of intent
HUMAN_REVIEW_KEYWORDS = [
    "legal", "lawsuit", "sue", "attorney", "fraud", "scam", "police",
    "complaint", "escalate", "manager", "supervisor", "unacceptable",
    "stolen", "identity theft",
]

# Multi-agent combos: when BOTH sets of keywords appear, fire ALL listed agents
MULTI_AGENT_COMBOS: List[tuple[List[str], List[str], List[AgentName]]] = [
    # "I want a refund for my order and the payment was already taken"
    (["refund", "return"], ["payment", "charged", "pay"],
     ["order_agent", "payment_agent", "refund_agent"]),

    # "Where is my delivery / shipping status"
    (["delivery", "deliver"], ["shipping", "track", "tracking"],
     ["delivery_agent", "shipping_agent"]),

    # "Cancel order and refund"
    (["cancel", "cancelled"], ["refund", "money back"],
     ["order_agent", "refund_agent"]),

    # "Order not received and need refund"
    (["not received", "missing", "never arrived"], ["refund", "money back"],
     ["delivery_agent", "refund_agent"]),
]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _contains_any(text: str, keywords: List[str]) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)


def _extract_agents(user_input: str) -> tuple[List[AgentName], str]:
    """
    Returns (agents_list, reasoning_string).
    Multi-agent combos take priority over single-agent rules.
    """
    text = user_input.lower()
    reasoning_parts: List[str] = []

    # 1. Check for immediate human escalation --------------------------------
    for kw in HUMAN_REVIEW_KEYWORDS:
        if kw in text:
            return (
                ["human_review"],
                f"Keyword '{kw}' detected → immediate human escalation.",
            )

    # 2. Check multi-agent combos first  (highest specificity) ---------------
    for set_a, set_b, agents in MULTI_AGENT_COMBOS:
        if _contains_any(text, set_a) and _contains_any(text, set_b):
            reasoning_parts.append(
                f"Multi-agent combo matched ({set_a[:1]} ∩ {set_b[:1]}) → {agents}"
            )
            return agents, " | ".join(reasoning_parts)

    # 3. Single-rule matching (all matching rules fire) ----------------------
    matched_agents: List[AgentName] = []
    for keywords, agents in ROUTING_RULES:
        if _contains_any(text, keywords):
            for a in agents:
                if a not in matched_agents:
                    matched_agents.append(a)
            reasoning_parts.append(
                f"Rule matched {keywords[:2]} → {agents}"
            )

    if matched_agents:
        return matched_agents, " | ".join(reasoning_parts)

    # 4. Fallback — ask for clarification via human review -------------------
    return (
        ["human_review"],
        "No clear intent detected → routing to human review for clarification.",
    )


# ---------------------------------------------------------------------------
# Router Node  (called by LangGraph)
# ---------------------------------------------------------------------------
def router_node(state: AgentState) -> dict:
    """
    Analyses user_input and populates `next_agents` + `router_reasoning`.
    """
    print(f"\n🔀  [Router] Analysing: '{state.user_input[:80]}…'")

    agents, reasoning = _extract_agents(state.user_input)

    print(f"   → Routing to: {agents}")
    print(f"   → Reason: {reasoning}")

    return {
        "next_agents": agents,
        "router_reasoning": reasoning,
        "current_agent": "router",
    }


# ---------------------------------------------------------------------------
# Routing condition used by LangGraph add_conditional_edges
# ---------------------------------------------------------------------------
def route_after_router(state: AgentState) -> List[str]:
    """
    Returns the list of next nodes LangGraph should fan-out to.
    LangGraph supports returning a list for parallel fan-out (Send API).
    """
    return state.next_agents if state.next_agents else ["human_review"]
