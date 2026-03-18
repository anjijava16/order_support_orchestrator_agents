# =============================================================================
# graph.py — LangGraph Graph Construction & Entry Point
# =============================================================================
#
#  Architecture
#  ────────────
#
#   START
#     │
#     ▼
#  [router_node]              ← decides which agents to call
#     │
#     ├──────────────────────────────────────────────────────┐
#     │  (conditional fan-out — can be 1 or multiple)        │
#     ▼                                                       ▼
#  [order_agent]         [payment_agent]       [delivery_agent] …
#     │                       │                      │
#     └───────────────────────┴──────────────────────┘
#                             │
#                   (join — all agents done)
#                             │
#                    [should_review?]
#                      /           \
#              yes /                 \ no
#               ▼                     ▼
#       [human_review_node]     [synthesize_response]
#               │                     │
#               ▼                     │
#       [synthesize_response] ────────┘
#               │
#             END
#
# =============================================================================

from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver

from state import AgentState
from router import router_node, route_after_router
from agents import order_agent, delivery_agent, payment_agent, shipping_agent, refund_agent
from human_loop import human_review_node, synthesize_response, should_review, after_human_review


# ---------------------------------------------------------------------------
# Build the Graph
# ---------------------------------------------------------------------------
def build_graph(checkpointer=None):
    """
    Constructs and compiles the multi-agent LangGraph.

    Args:
        checkpointer: A LangGraph checkpointer for persistence (optional).
                      Pass `MemorySaver()` for in-memory state between turns.

    Returns:
        Compiled LangGraph app.
    """
    builder = StateGraph(AgentState)

    # ── Add all nodes ────────────────────────────────────────────────────────
    builder.add_node("router", router_node)
    builder.add_node("order_agent", order_agent)
    builder.add_node("payment_agent", payment_agent)
    builder.add_node("delivery_agent", delivery_agent)
    builder.add_node("shipping_agent", shipping_agent)
    builder.add_node("refund_agent", refund_agent)
    builder.add_node("human_review", human_review_node)
    builder.add_node("synthesize", synthesize_response)

    # ── Entry edge ───────────────────────────────────────────────────────────
    builder.add_edge(START, "router")

    # ── Router → fan-out to agent(s) ─────────────────────────────────────────
    builder.add_conditional_edges(
        "router",
        route_after_router,
        {
            "order_agent":    "order_agent",
            "payment_agent":  "payment_agent",
            "delivery_agent": "delivery_agent",
            "shipping_agent": "shipping_agent",
            "refund_agent":   "refund_agent",
            "human_review":   "human_review",
        },
    )

    # ── Each agent → should_review gate ──────────────────────────────────────
    for agent_node in ["order_agent", "payment_agent", "delivery_agent",
                       "shipping_agent", "refund_agent"]:
        builder.add_conditional_edges(
            agent_node,
            should_review,
            {
                "human_review": "human_review",
                "synthesize":   "synthesize",
            },
        )

    # ── Human review → always synthesize ─────────────────────────────────────
    builder.add_conditional_edges(
        "human_review",
        after_human_review,
        {"synthesize": "synthesize"},
    )

    # ── Synthesize → END ─────────────────────────────────────────────────────
    builder.add_edge("synthesize", END)

    # ── Compile with optional checkpointer ───────────────────────────────────
    compile_kwargs = {}
    if checkpointer:
        compile_kwargs["checkpointer"] = checkpointer
        # Interrupt BEFORE human_review so the graph pauses for human input
        compile_kwargs["interrupt_before"] = ["human_review"]

    return builder.compile(**compile_kwargs)


# ---------------------------------------------------------------------------
# Pretty-print helpers
# ---------------------------------------------------------------------------
def print_banner():
    print("\n" + "█" * 65)
    print("█  🤖  E-COMMERCE MULTI-AGENT SYSTEM  (LangGraph + HITL)  █")
    print("█" * 65)


def print_separator():
    print("\n" + "─" * 65)


def display_result(state: AgentState):
    print_separator()
    print("📋  FINAL RESPONSE")
    print_separator()
    print(state.final_response)
    print_separator()
    print(f"Agents invoked : {state.completed_agents}")
    print(f"Human reviewed : {state.requires_human_review}")
    if state.requires_human_review:
        status = "✅ Approved" if state.human_approved else "❌ Rejected"
        print(f"Human decision : {status}")
    print_separator()


# ---------------------------------------------------------------------------
# Main interactive loop
# ---------------------------------------------------------------------------
def main():
    print_banner()

    # Build graph with MemorySaver so state persists across turns in a session
    memory = MemorySaver()
    app = build_graph(checkpointer=memory)

    # Thread ID identifies the conversation session
    config = {"configurable": {"thread_id": "demo-session-001"}}

    print("\nAvailable agents: Order | Payment | Delivery | Shipping | Refund")
    print("Type 'quit' to exit | Type 'history' to see conversation log\n")

    conversation_history = []

    while True:
        print_separator()
        user_input = input("👤  You: ").strip()

        if not user_input:
            continue
        if user_input.lower() == "quit":
            print("Goodbye! 👋")
            break
        if user_input.lower() == "history":
            if conversation_history:
                for turn in conversation_history:
                    print(f"  User : {turn['user']}")
                    print(f"  Bot  : {turn['response'][:100]}…\n")
            else:
                print("No history yet.")
            continue

        # ── Build initial state ──────────────────────────────────────────────
        initial_state = AgentState(
            user_input=user_input,
            conversation_history=conversation_history,
            session_id="demo-session-001",
        )

        # ── Run graph ────────────────────────────────────────────────────────
        try:
            # stream_mode="values" gives us state snapshots after each node
            final_state = None
            for state_snapshot in app.stream(
                initial_state,
                config=config,
                stream_mode="values",
            ):
                final_state = state_snapshot

            if final_state is None:
                print("⚠️  No output from graph.")
                continue

            # Wrap dict in AgentState if needed
            if isinstance(final_state, dict):
                final_state = AgentState(**final_state)

            display_result(final_state)
            conversation_history.append(
                {"user": user_input, "response": final_state.final_response}
            )

        except Exception as exc:
            print(f"\n❌  Graph error: {exc}")
            raise


# ---------------------------------------------------------------------------
# Demo mode — runs a fixed set of scenarios without requiring user input
# ---------------------------------------------------------------------------
DEMO_SCENARIOS = [
    "I want to check my order status",
    "My payment was declined and I need a refund",
    "Where is my delivery? It's delayed and I need a refund for my order",
    "I need a shipping tracking number for my package",
    "Cancel my order and process a refund please",
    "I want to escalate this to a manager — this is unacceptable fraud!",
]


def run_demo():
    """Runs all demo scenarios non-interactively (no human prompts)."""
    print_banner()
    print("\n🎬  Running DEMO mode (non-interactive) …\n")

    # Demo uses auto-approve for human review to avoid blocking
    import human_loop as hl

    _original_review = hl.human_review_node

    def auto_approve_human_review(state: AgentState) -> dict:
        print("\n🤖  [AUTO-APPROVE] Simulating human approval for demo …")
        return {
            "human_approved": True,
            "human_feedback": "Auto-approved in demo mode.",
            "completed_agents": state.completed_agents + ["human_review"],
            "current_agent": "human_review",
        }

    hl.human_review_node = auto_approve_human_review

    # Rebuild graph with patched human review
    app = build_graph()  # No checkpointer in demo

    for i, scenario in enumerate(DEMO_SCENARIOS, 1):
        print(f"\n{'=' * 65}")
        print(f"  SCENARIO {i}: {scenario}")
        print(f"{'=' * 65}")

        state = AgentState(user_input=scenario, session_id=f"demo-{i}")
        final = None
        for snapshot in app.stream(state, stream_mode="values"):
            final = snapshot

        if final:
            if isinstance(final, dict):
                final = AgentState(**final)
            display_result(final)

    # Restore original
    hl.human_review_node = _original_review
    print("\n✅  Demo complete!")


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        run_demo()
    else:
        main()
