# =============================================================================
# agents.py — Individual Agent Implementations
# =============================================================================
#
#  Each agent is a pure function:  (AgentState) -> dict
#  It returns only the keys it wants to UPDATE in the shared state.
#  LangGraph merges the returned dict back into the state automatically.
#
# =============================================================================

import random
import string
from datetime import datetime, timedelta
from state import (
    AgentState,
    OrderResult,
    DeliveryResult,
    PaymentResult,
    ShippingResult,
    RefundResult,
)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------
def _uid(prefix: str, n: int = 8) -> str:
    """Generate a random ID like ORD-A3F9B2C1."""
    return f"{prefix}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=n))}"


def _future_date(days: int) -> str:
    return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# 1. ORDER AGENT
# ---------------------------------------------------------------------------
def order_agent(state: AgentState) -> dict:
    """
    Handles: place order, cancel order, view order status, modify order.
    In production this would call your order-management system / database.
    Here we simulate the result so the graph logic stays clear.
    """
    print("\n🛒  [Order Agent] Processing …")

    user_input = state.user_input.lower()

    # --- Simulate different order operations --------------------------------
    if any(w in user_input for w in ["cancel", "cancelled"]):
        result = OrderResult(
            order_id=_uid("ORD"),
            status="cancelled",
            message="Your order has been successfully cancelled. Refund will be initiated within 3-5 business days.",
        )
    elif any(w in user_input for w in ["status", "where", "track"]):
        result = OrderResult(
            order_id=_uid("ORD"),
            status="processing",
            items=[{"name": "Product XYZ", "qty": 2, "price": 49.99}],
            total_amount=99.98,
            message="Your order is currently being processed and will be shipped within 24 hours.",
        )
    elif any(w in user_input for w in ["place", "buy", "purchase", "order"]):
        result = OrderResult(
            order_id=_uid("ORD"),
            status="confirmed",
            items=[{"name": "Product ABC", "qty": 1, "price": 79.99}],
            total_amount=79.99,
            message="Order placed successfully! You will receive a confirmation email shortly.",
        )
    else:
        result = OrderResult(
            order_id=_uid("ORD"),
            status="unknown",
            message="I've retrieved your order information. Please let me know if you need anything else.",
        )

    print(f"   ✅ Order Agent done → status={result.status}")
    return {
        "order_result": result,
        "completed_agents": state.completed_agents + ["order_agent"],
        "current_agent": "order_agent",
    }


# ---------------------------------------------------------------------------
# 2. DELIVERY AGENT
# ---------------------------------------------------------------------------
def delivery_agent(state: AgentState) -> dict:
    """
    Handles: delivery status, estimated delivery date, delivery issues,
    reschedule delivery.
    """
    print("\n📦  [Delivery Agent] Processing …")

    user_input = state.user_input.lower()

    if any(w in user_input for w in ["delay", "late", "delayed"]):
        result = DeliveryResult(
            delivery_id=_uid("DEL"),
            estimated_date=_future_date(5),
            current_location="Sorting Facility - Chicago, IL",
            status="delayed",
            message=(
                "We apologize for the delay. Your package is currently at the Chicago sorting facility "
                "due to high volume. New estimated delivery: " + _future_date(5)
            ),
        )
        # Flag high-value delay issues for human review
        return {
            "delivery_result": result,
            "completed_agents": state.completed_agents + ["delivery_agent"],
            "current_agent": "delivery_agent",
            "requires_human_review": True,
            "human_review_reason": "Delivery delay detected — supervisor review recommended before issuing compensation.",
        }

    elif any(w in user_input for w in ["schedule", "reschedule", "change"]):
        result = DeliveryResult(
            delivery_id=_uid("DEL"),
            estimated_date=_future_date(3),
            status="rescheduled",
            message=f"Your delivery has been rescheduled to {_future_date(3)}. You will receive an SMS confirmation.",
        )
    else:
        result = DeliveryResult(
            delivery_id=_uid("DEL"),
            estimated_date=_future_date(2),
            current_location="Local Distribution Center",
            status="in_transit",
            message=f"Your package is on its way! Estimated delivery: {_future_date(2)}.",
        )

    print(f"   ✅ Delivery Agent done → status={result.status}")
    return {
        "delivery_result": result,
        "completed_agents": state.completed_agents + ["delivery_agent"],
        "current_agent": "delivery_agent",
    }


# ---------------------------------------------------------------------------
# 3. PAYMENT AGENT
# ---------------------------------------------------------------------------
def payment_agent(state: AgentState) -> dict:
    """
    Handles: payment verification, failed payments, invoice requests,
    payment method updates.
    """
    print("\n💳  [Payment Agent] Processing …")

    user_input = state.user_input.lower()

    if any(w in user_input for w in ["fail", "failed", "decline", "declined", "error"]):
        result = PaymentResult(
            transaction_id=_uid("TXN"),
            status="failed",
            message=(
                "Your payment was declined. Common reasons: insufficient funds, incorrect card details, "
                "or bank security check. Please try a different payment method or contact your bank."
            ),
        )
        return {
            "payment_result": result,
            "completed_agents": state.completed_agents + ["payment_agent"],
            "current_agent": "payment_agent",
            "requires_human_review": True,
            "human_review_reason": "Payment failure flagged — may need manual verification to prevent fraud.",
        }

    elif any(w in user_input for w in ["invoice", "receipt", "bill"]):
        result = PaymentResult(
            transaction_id=_uid("TXN"),
            amount=149.99,
            status="completed",
            payment_method="Visa ending in 4242",
            message="Invoice has been sent to your registered email address.",
        )
    elif any(w in user_input for w in ["refund", "charge", "charged"]):
        result = PaymentResult(
            transaction_id=_uid("TXN"),
            amount=149.99,
            status="under_review",
            message="Payment discrepancy detected. Our team will review and resolve within 24 hours.",
        )
    else:
        result = PaymentResult(
            transaction_id=_uid("TXN"),
            amount=99.99,
            status="completed",
            payment_method="Mastercard ending in 5678",
            message="Payment processed successfully.",
        )

    print(f"   ✅ Payment Agent done → status={result.status}")
    return {
        "payment_result": result,
        "completed_agents": state.completed_agents + ["payment_agent"],
        "current_agent": "payment_agent",
    }


# ---------------------------------------------------------------------------
# 4. SHIPPING AGENT
# ---------------------------------------------------------------------------
def shipping_agent(state: AgentState) -> dict:
    """
    Handles: shipping label generation, carrier selection, tracking number,
    shipping cost queries.
    """
    print("\n🚚  [Shipping Agent] Processing …")

    user_input = state.user_input.lower()

    if any(w in user_input for w in ["track", "tracking"]):
        result = ShippingResult(
            tracking_number=_uid("TRACK"),
            carrier="FedEx",
            shipped_date=(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
            status="in_transit",
            message="Your package is in transit. Track at fedex.com with the tracking number above.",
        )
    elif any(w in user_input for w in ["cost", "price", "rate", "charge"]):
        result = ShippingResult(
            carrier="Multiple carriers available",
            status="quote_ready",
            message="Standard (5-7 days): $4.99 | Express (2-3 days): $12.99 | Overnight: $24.99",
        )
    elif any(w in user_input for w in ["label", "generate", "print"]):
        result = ShippingResult(
            tracking_number=_uid("TRACK"),
            carrier="UPS",
            shipped_date=datetime.now().strftime("%Y-%m-%d"),
            status="label_created",
            message="Shipping label generated. Drop off at any UPS location.",
        )
    else:
        result = ShippingResult(
            tracking_number=_uid("TRACK"),
            carrier="USPS",
            status="shipped",
            message="Package has been shipped and is on the way.",
        )

    print(f"   ✅ Shipping Agent done → status={result.status}")
    return {
        "shipping_result": result,
        "completed_agents": state.completed_agents + ["shipping_agent"],
        "current_agent": "shipping_agent",
    }


# ---------------------------------------------------------------------------
# 5. REFUND AGENT
# ---------------------------------------------------------------------------
def refund_agent(state: AgentState) -> dict:
    """
    Handles: refund requests, refund status, partial refunds, return processing.
    High-value refunds always go to human review.
    """
    print("\n💰  [Refund Agent] Processing …")

    user_input = state.user_input.lower()

    # Determine refund amount from context (order result if available)
    refund_amount = state.order_result.total_amount if state.order_result else 0.0
    if refund_amount is None:
        refund_amount = 0.0

    # Simulate: high-value refunds need human approval
    HIGH_VALUE_THRESHOLD = 100.0
    needs_review = refund_amount > HIGH_VALUE_THRESHOLD

    if any(w in user_input for w in ["status", "where", "when"]):
        result = RefundResult(
            refund_id=_uid("RFD"),
            amount=refund_amount or 49.99,
            status="processing",
            message="Your refund is being processed. It will appear in your account within 5-7 business days.",
        )
    elif any(w in user_input for w in ["partial"]):
        result = RefundResult(
            refund_id=_uid("RFD"),
            amount=round((refund_amount or 49.99) / 2, 2),
            status="approved",
            reason="Partial refund for damaged items",
            message="Partial refund approved. Amount will be credited within 3-5 business days.",
        )
    else:
        result = RefundResult(
            refund_id=_uid("RFD"),
            amount=refund_amount or 79.99,
            status="initiated" if not needs_review else "pending_approval",
            reason="Customer request",
            message=(
                "Refund initiated successfully. Estimated credit: 5-7 business days."
                if not needs_review
                else "Refund request received. Due to the amount, it requires supervisor approval (pending)."
            ),
        )

    print(f"   ✅ Refund Agent done → status={result.status}, review={needs_review}")
    update: dict = {
        "refund_result": result,
        "completed_agents": state.completed_agents + ["refund_agent"],
        "current_agent": "refund_agent",
    }
    if needs_review:
        update["requires_human_review"] = True
        update["human_review_reason"] = (
            f"High-value refund of ${result.amount:.2f} requires supervisor approval."
        )
    return update
