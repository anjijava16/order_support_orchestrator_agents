# =============================================================================
# state.py — Shared State Definition for Multi-Agent E-Commerce System
# =============================================================================

from typing import Annotated, Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field
from langgraph.graph.message import add_messages


# ---------------------------------------------------------------------------
# Agent names (used as literals throughout the graph)
# ---------------------------------------------------------------------------
AgentName = Literal[
    "router",
    "order_agent",
    "delivery_agent",
    "payment_agent",
    "shipping_agent",
    "refund_agent",
    "human_review",
    "END",
]


# ---------------------------------------------------------------------------
# Individual agent result schemas
# ---------------------------------------------------------------------------
class OrderResult(BaseModel):
    order_id: Optional[str] = None
    status: Optional[str] = None
    items: List[Dict[str, Any]] = Field(default_factory=list)
    total_amount: Optional[float] = None
    message: str = ""


class DeliveryResult(BaseModel):
    delivery_id: Optional[str] = None
    estimated_date: Optional[str] = None
    current_location: Optional[str] = None
    status: Optional[str] = None
    message: str = ""


class PaymentResult(BaseModel):
    transaction_id: Optional[str] = None
    amount: Optional[float] = None
    status: Optional[str] = None
    payment_method: Optional[str] = None
    message: str = ""


class ShippingResult(BaseModel):
    tracking_number: Optional[str] = None
    carrier: Optional[str] = None
    shipped_date: Optional[str] = None
    status: Optional[str] = None
    message: str = ""


class RefundResult(BaseModel):
    refund_id: Optional[str] = None
    amount: Optional[float] = None
    status: Optional[str] = None
    reason: Optional[str] = None
    message: str = ""


# ---------------------------------------------------------------------------
# Main shared graph state
# ---------------------------------------------------------------------------
class AgentState(BaseModel):
    """
    Single shared state that flows through every node in the LangGraph.
    Each field is updated by the relevant agent node; the router reads
    `next_agents` to decide which agent(s) to call next.
    """

    # ── User interaction ────────────────────────────────────────────────────
    user_input: str = ""
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)
    session_id: str = "default"

    # ── Routing decisions ───────────────────────────────────────────────────
    next_agents: List[AgentName] = Field(default_factory=list)
    current_agent: Optional[AgentName] = None
    completed_agents: List[AgentName] = Field(default_factory=list)
    router_reasoning: str = ""

    # ── Human-in-the-Loop fields ────────────────────────────────────────────
    requires_human_review: bool = False
    human_review_reason: str = ""
    human_approved: Optional[bool] = None
    human_feedback: str = ""

    # ── Agent results ───────────────────────────────────────────────────────
    order_result: Optional[OrderResult] = None
    delivery_result: Optional[DeliveryResult] = None
    payment_result: Optional[PaymentResult] = None
    shipping_result: Optional[ShippingResult] = None
    refund_result: Optional[RefundResult] = None

    # ── Final output ────────────────────────────────────────────────────────
    final_response: str = ""
    error: Optional[str] = None
    processing_complete: bool = False
