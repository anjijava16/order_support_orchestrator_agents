# =============================================================================
# api.py — FastAPI REST API for the Multi-Agent System
# =============================================================================
#
#  Endpoints:
#    POST /chat           — Send a message, get a response
#    POST /human-review   — Submit human approval / rejection
#    GET  /status/{sid}   — Get current session state
#    GET  /health         — Health check
#
#  Run with:  uvicorn api:app --reload
#
# =============================================================================

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import uuid

from langgraph.checkpoint.memory import MemorySaver
from graph import build_graph
from state import AgentState

app = FastAPI(
    title="E-Commerce Multi-Agent API",
    description="LangGraph-powered multi-agent system with Human-in-the-Loop",
    version="1.0.0",
)

# Global in-memory state (use Redis / DB in production)
memory = MemorySaver()
graph_app = build_graph(checkpointer=memory)

# Track sessions awaiting human review: {session_id: AgentState}
pending_human_reviews: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None  # auto-generated if not supplied


class ChatResponse(BaseModel):
    session_id: str
    response: str
    agents_invoked: list[str]
    requires_human_review: bool
    human_review_reason: Optional[str] = None
    processing_complete: bool


class HumanReviewRequest(BaseModel):
    session_id: str
    approved: bool
    feedback: Optional[str] = ""


class HumanReviewResponse(BaseModel):
    session_id: str
    decision: str
    final_response: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok", "service": "E-Commerce Multi-Agent System"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    Main chat endpoint.  Processes the user message through the agent graph.
    If the result requires human review the response will flag it so the
    frontend can display a review UI.
    """
    session_id = req.session_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": session_id}}

    initial_state = AgentState(
        user_input=req.message,
        session_id=session_id,
    )

    try:
        final_state = None
        for snapshot in graph_app.stream(initial_state, config=config, stream_mode="values"):
            final_state = snapshot

        if final_state is None:
            raise HTTPException(status_code=500, detail="Graph produced no output")

        if isinstance(final_state, dict):
            state = AgentState(**final_state)
        else:
            state = final_state

        # If human review is needed, store session for later resolution
        if state.requires_human_review and state.human_approved is None:
            pending_human_reviews[session_id] = final_state

        return ChatResponse(
            session_id=session_id,
            response=state.final_response or "Processing …",
            agents_invoked=state.completed_agents,
            requires_human_review=state.requires_human_review,
            human_review_reason=state.human_review_reason if state.requires_human_review else None,
            processing_complete=state.processing_complete,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/human-review", response_model=HumanReviewResponse)
async def submit_human_review(req: HumanReviewRequest):
    """
    Submit a human review decision.
    The graph resumes from the interrupted state.
    """
    config = {"configurable": {"thread_id": req.session_id}}

    # Inject human decision into the paused graph state
    graph_app.update_state(
        config,
        {
            "human_approved": req.approved,
            "human_feedback": req.feedback or ("Approved." if req.approved else "Rejected."),
        },
        as_node="human_review",  # resume AS IF the human_review node just finished
    )

    # Continue graph execution from the checkpoint
    final_state = None
    for snapshot in graph_app.stream(None, config=config, stream_mode="values"):
        final_state = snapshot

    if final_state is None:
        raise HTTPException(status_code=500, detail="Graph produced no output after human review")

    if isinstance(final_state, dict):
        state = AgentState(**final_state)
    else:
        state = final_state

    # Remove from pending
    pending_human_reviews.pop(req.session_id, None)

    return HumanReviewResponse(
        session_id=req.session_id,
        decision="approved" if req.approved else "rejected",
        final_response=state.final_response,
    )


@app.get("/status/{session_id}")
async def get_session_status(session_id: str):
    """Return the current state of a session."""
    config = {"configurable": {"thread_id": session_id}}
    try:
        checkpoint = graph_app.get_state(config)
        if checkpoint is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return {
            "session_id": session_id,
            "pending_human_review": session_id in pending_human_reviews,
            "state": checkpoint.values,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/pending-reviews")
async def list_pending_reviews():
    """List all sessions awaiting human review."""
    return {
        "count": len(pending_human_reviews),
        "sessions": list(pending_human_reviews.keys()),
    }

