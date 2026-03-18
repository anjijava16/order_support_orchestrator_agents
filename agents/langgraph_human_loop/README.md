# 🤖 E-Commerce Multi-Agent System
## Built with LangGraph + Human-in-the-Loop (HITL)

---

## 📐 Architecture Overview

```
                        ┌─────────────────────────────┐
   User Input           │         ROUTER NODE          │
   ──────────►          │  (keyword / LLM-based rules) │
                        └──────────────┬──────────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │     conditional fan-out (1 or many)  │
                    ▼                  ▼                   ▼
            ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐
            │ ORDER AGENT │  │PAYMENT AGENT │  │ DELIVERY AGENT   │
            └──────┬──────┘  └──────┬───────┘  └────────┬─────────┘
                   │                │                    │
                   ▼                ▼                    ▼
            ┌─────────────┐  ┌──────────────────────────────────────┐
            │SHIPPING AGT │  │         REFUND AGENT                 │
            └──────┬──────┘  └──────────────────────────────────────┘
                   │
                   ▼
         ┌──────────────────┐
         │  should_review?  │ ◄── checks requires_human_review flag
         └────────┬─────────┘
          YES ◄───┴──► NO
           ▼              ▼
    ┌─────────────┐  ┌──────────────────┐
    │HUMAN REVIEW │  │   SYNTHESIZER    │
    │    (HITL)   │  │  (final answer)  │
    └──────┬──────┘  └────────┬─────────┘
           │                  │
           ▼                  │
    ┌──────────────┐          │
    │  SYNTHESIZER │──────────┘
    └──────┬───────┘
           │
          END
```

---

## 🗂️ File Structure

```
ecommerce_agents/
│
├── state.py          # Shared AgentState (Pydantic model)
├── router.py         # Router node — decides which agents to invoke
├── agents.py         # All 5 agent implementations
├── human_loop.py     # Human Review node + Response Synthesizer
├── graph.py          # LangGraph builder + CLI entry point
├── api.py            # FastAPI REST API wrapper
└── requirements.txt  # Python dependencies
```

---

## 🚀 Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Run interactive CLI
```bash
python graph.py
```

### 3. Run demo (no user prompts)
```bash
python graph.py --demo
```

### 4. Run REST API
```bash
pip install fastapi uvicorn
uvicorn api:app --reload
# Swagger UI → http://localhost:8000/docs
```

---

## 🔀 Router Logic

The Router is the **first node** and the **brain** of the system.

| User says...                                  | Agents invoked                              |
|----------------------------------------------|----------------------------------------------|
| "Check my order status"                       | `order_agent`                               |
| "My payment was declined"                     | `payment_agent`                             |
| "Where is my delivery?"                       | `delivery_agent`                            |
| "Give me a tracking number"                   | `shipping_agent`                            |
| "I want a refund"                             | `refund_agent`                              |
| "Cancel order and get a refund"               | `order_agent` + `refund_agent`              |
| "Refund + payment was already charged"        | `order_agent` + `payment_agent` + `refund_agent` |
| "Delivery delayed + need refund"              | `delivery_agent` + `refund_agent`           |
| "This is fraud / I want a manager"            | `human_review` (immediate escalation)       |

---

## 🧑 Human-in-the-Loop (HITL)

Human review is **automatically triggered** in these cases:

| Trigger                            | Agent         | Example                                              |
|------------------------------------|---------------|------------------------------------------------------|
| Delivery delay detected            | Delivery      | Supervisor decides if compensation is warranted      |
| Payment failure                    | Payment       | Manual fraud check before retrying                  |
| High-value refund (> $100)         | Refund        | Supervisor must approve large refunds                |
| Legal / escalation keywords        | Router        | "fraud", "sue", "manager" → immediate escalation    |
| Unknown intent                     | Router        | Fallback to human clarification                     |

### HITL Flow (LangGraph)

```python
# Graph pauses before human_review node
app = builder.compile(
    checkpointer=MemorySaver(),
    interrupt_before=["human_review"]   # ← PAUSE HERE
)

# Human submits their decision via API or CLI
graph_app.update_state(config, {
    "human_approved": True,
    "human_feedback": "Verified — proceed with refund."
})

# Graph resumes from checkpoint
for snapshot in graph_app.stream(None, config=config):
    ...
```

---

## 🔌 REST API Endpoints

| Method | Endpoint              | Description                                |
|--------|-----------------------|--------------------------------------------|
| POST   | `/chat`               | Send a user message                        |
| POST   | `/human-review`       | Submit approval / rejection                |
| GET    | `/status/{session_id}`| Get current session state                  |
| GET    | `/pending-reviews`    | List sessions awaiting human review        |
| GET    | `/health`             | Health check                               |

### Example: Chat Request
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "My payment failed and I need a refund"}'
```

### Example: Human Review
```bash
curl -X POST http://localhost:8000/human-review \
  -H "Content-Type: application/json" \
  -d '{"session_id": "abc-123", "approved": true, "feedback": "Verified legit"}'
```

---

## 🤖 Agent Responsibilities

| Agent            | Handles                                                       |
|------------------|---------------------------------------------------------------|
| **Order Agent**  | Place, cancel, modify, track orders                          |
| **Payment Agent**| Verify payments, failed transactions, invoices               |
| **Delivery Agent**| Delivery status, ETAs, delay handling, rescheduling         |
| **Shipping Agent**| Tracking numbers, carriers, label generation, shipping costs|
| **Refund Agent** | Initiate refunds, check status, partial refunds              |

---

## 🔧 Swapping to LLM-based Routing

Replace the keyword logic in `router.py` with an LLM call:

```python
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

llm = ChatOpenAI(model="gpt-4o-mini")

SYSTEM_PROMPT = """
You are a routing assistant for an e-commerce support system.
Given a user message, return a JSON list of agents to invoke.
Available agents: order_agent, payment_agent, delivery_agent, shipping_agent, refund_agent, human_review.
Return ONLY a JSON list, e.g. ["order_agent", "refund_agent"]
"""

def router_node(state: AgentState) -> dict:
    response = llm.invoke([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": state.user_input}
    ])
    agents = json.loads(response.content)
    return {"next_agents": agents, "router_reasoning": "LLM-based routing"}
```

---

## 📦 State Schema (AgentState)

```python
class AgentState(BaseModel):
    user_input: str                    # Raw user message
    next_agents: List[AgentName]       # Router output
    completed_agents: List[AgentName]  # Audit trail

    requires_human_review: bool        # HITL trigger flag
    human_review_reason: str           # Why review is needed
    human_approved: Optional[bool]     # None = pending
    human_feedback: str                # Supervisor notes

    order_result: Optional[OrderResult]
    payment_result: Optional[PaymentResult]
    delivery_result: Optional[DeliveryResult]
    shipping_result: Optional[ShippingResult]
    refund_result: Optional[RefundResult]

    final_response: str                # Synthesized answer
    processing_complete: bool
```
