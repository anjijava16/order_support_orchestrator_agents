# =============================================================================
# human_loop.py — Human-in-the-Loop Node + Response Synthesizer
# =============================================================================

from state import AgentState


# ---------------------------------------------------------------------------
# Human Review Node
# ---------------------------------------------------------------------------
def human_review_node(state: AgentState) -> dict:
    """
    This is the INTERRUPT point.  In a real deployment, LangGraph pauses here
    and the UI shows the human a review form.  The human submits feedback
    which is injected back via graph.update_state().

    In this demo we run it interactively on the console.
    """
    print("\n" + "=" * 60)
    print("🧑  HUMAN REVIEW REQUIRED")
    print("=" * 60)
    print(f"Reason      : {state.human_review_reason}")
    print(f"User input  : {state.user_input}")
    print(f"Agents done : {state.completed_agents}")
    print("-" * 60)

    # Show partial results collected so far
    if state.order_result:
        print(f"Order Result    : {state.order_result.message}")
    if state.payment_result:
        print(f"Payment Result  : {state.payment_result.message}")
    if state.delivery_result:
        print(f"Delivery Result : {state.delivery_result.message}")
    if state.shipping_result:
        print(f"Shipping Result : {state.shipping_result.message}")
    if state.refund_result:
        print(f"Refund Result   : {state.refund_result.message}")

    print("=" * 60)

    # ----- Interactive console prompt (replace with UI webhook in prod) -----
    while True:
        decision = input("👤  Approve? [y/n]: ").strip().lower()
        if decision in ("y", "yes"):
            feedback = input("👤  Enter feedback / notes (optional): ").strip()
            print("   ✅  Human APPROVED the action.")
            return {
                "human_approved": True,
                "human_feedback": feedback or "Approved by supervisor.",
                "completed_agents": state.completed_agents + ["human_review"],
                "current_agent": "human_review",
            }
        elif decision in ("n", "no"):
            feedback = input("👤  Reason for rejection: ").strip()
            print("   ❌  Human REJECTED the action.")
            return {
                "human_approved": False,
                "human_feedback": feedback or "Rejected by supervisor.",
                "completed_agents": state.completed_agents + ["human_review"],
                "current_agent": "human_review",
            }
        else:
            print("   Please enter 'y' or 'n'.")


# ---------------------------------------------------------------------------
# Response Synthesizer — final node that assembles the answer
# ---------------------------------------------------------------------------
def synthesize_response(state: AgentState) -> dict:
    """
    Collects all agent results and human feedback into one coherent response.
    """
    print("\n📝  [Synthesizer] Building final response …")

    parts: list[str] = []

    # ----- Human review outcome --------------------------------------------
    if state.requires_human_review:
        if state.human_approved is True:
            parts.append(
                f"✅ **Supervisor Approved** — {state.human_feedback}"
            )
        elif state.human_approved is False:
            parts.append(
                f"❌ **Supervisor Rejected** — {state.human_feedback}\n"
                "  Please contact support for further assistance."
            )
        # If human_approved is None: review was skipped / not needed

    # ----- Agent summaries -------------------------------------------------
    if state.order_result:
        parts.append(f"🛒 **Order**: {state.order_result.message}")
        if state.order_result.order_id:
            parts.append(f"   Order ID: `{state.order_result.order_id}`")

    if state.payment_result:
        parts.append(f"💳 **Payment**: {state.payment_result.message}")
        if state.payment_result.transaction_id:
            parts.append(f"   Transaction ID: `{state.payment_result.transaction_id}`")

    if state.delivery_result:
        parts.append(f"📦 **Delivery**: {state.delivery_result.message}")

    if state.shipping_result:
        parts.append(f"🚚 **Shipping**: {state.shipping_result.message}")
        if state.shipping_result.tracking_number:
            parts.append(f"   Tracking: `{state.shipping_result.tracking_number}`")

    if state.refund_result:
        parts.append(f"💰 **Refund**: {state.refund_result.message}")
        if state.refund_result.refund_id:
            parts.append(f"   Refund ID: `{state.refund_result.refund_id}`")

    # ----- Router reasoning (debug / transparency) -------------------------
    if state.router_reasoning:
        parts.append(f"\n_Router reasoning: {state.router_reasoning}_")

    final_response = "\n".join(parts) if parts else "Your request has been processed."

    print("   ✅  Synthesis complete.")
    return {
        "final_response": final_response,
        "processing_complete": True,
    }


# ---------------------------------------------------------------------------
# Conditions used by LangGraph
# ---------------------------------------------------------------------------
def should_review(state: AgentState) -> str:
    """After agents run, decide if we need human review or can go straight to synthesis."""
    if state.requires_human_review and state.human_approved is None:
        return "human_review"
    return "synthesize"


def after_human_review(state: AgentState) -> str:
    """After human review always synthesize (whether approved or rejected)."""
    return "synthesize"
