# order_support_orchestrator_agents


🧠 A2A Order Tracking System — Flow Diagram


Order support Orchestrator Agents 

# High Level Flow
```

Customer (Chat UI)
        │
        ▼
Customer Support Agent (NLP) (Customer)
        │
        ▼
🧠 Host / Orchestrator Agent
        │
 ┌──────┼────────┬──────────┬───────────┬──────────┐
 ▼      ▼        ▼          ▼           ▼          ▼
Order  Shipping Returns  Knowledge  Notification  (others)
Agent  Agent    Agent    Base Agent Agent
        │
        ▼
🧠 Host Agent aggregates responses
        │
        ▼
Customer Support Agent formats reply
        │
        ▼
Customer


```

```

Presentation Layer
    - Chat UI

Conversation Layer
    - Customer Support Agent

Orchestration Layer
    - Host Agent

Service Layer
    - Order Agent
    - Shipping Agent
    - Returns Agent
    - Knowledge Agent
    - Notification Agent

Data Layer
    - Databases
    - APIs
    - External services


```


# More agents

```
Recommended Agents for Your Project (Balanced)

If you want powerful but manageable, use:

🎯 12–15 Agents Setup Core

Host Orchestrator Agent

Customer Support Agent

Order Management Agent

Shipping & Tracking Agent

Returns & Refund Agent

Notification Agent

Knowledge Base Agent

-- Advanced

Sentiment Analysis Agent

Escalation Agent

Inventory Agent

Payment Agent

Delivery Issue Agent

Address Validation Agent

Analytics Agent

```

---

# Deep Project Summary

## Overview

**Order Support Orchestrator Agents** is a **multi-agent e-commerce customer support system** built on the [A2A (Agent-to-Agent)](https://google.github.io/A2A/) protocol. A central Host/Orchestrator Agent routes customer queries to domain-specific agents, each running as an **independent A2A server** on a dedicated port. The project is deliberately **polyglot in AI frameworks** — each agent uses a different framework — making it both a production-oriented architecture and a comparative learning resource.

```
Presentation Layer (Chat UI)
        │
Conversation Layer (Customer Support Agent / NLP)
        │
Orchestration Layer (Host / Orchestrator Agent)
        │
   ┌────┴────┬──────────┬───────────┬──────────┬──────────┐
   ▼         ▼          ▼           ▼          ▼          ▼
 Order    Shipping   Returns   Knowledge  Notification  Payment
 Agent    Agent      Agent     Agent      Agent         Agent
(LangGraph) (ADK)  (CrewAI)  (LangGraph) (Strands)   (Raw OpenAI)
  :8070    :8071     :8072      TBD       :8073        :8075
   │         │          │           │          │          │
   └─────────┴──────────┴───────────┴──────────┴──────────┘
                        │
                   Data Layer
              (Databases, APIs, AWS)
```

---

## Agent Inventory

### Core A2A Agent Servers

| # | Agent | Port | Framework | LLM | Status |
|---|-------|------|-----------|-----|--------|
| 1 | **Order Agent** | 8070 | LangGraph + A2A SDK | GPT-4o (OpenAI) | Implemented |
| 2 | **Shipping Agent** | 8071 | Google ADK + A2A SDK | GPT-4o (LiteLLM) | Partial |
| 3 | **Returns Agent** | 8072 | CrewAI (planned) | — | Scaffolded |
| 4 | **Notification Agent** | 8073 | Strands Agents | — | Scaffolded |
| 5 | **Payment Agent** | 8075 | Raw OpenAI API | Llama 3.1 8B (OpenRouter) | Implemented |
| 6 | **Knowledge Agent** | TBD | LangGraph | — | Scaffolded |
| 7 | **Tracking Agent** | TBD | No framework | — | Scaffolded |
| 8 | **Escalation Agent** | TBD | AutoGen | — | Scaffolded |
| 9 | **Delivery Agent** | 8076 | AutoGen | — | Scaffolded |
| 10 | **Travel Assistant** | 9090 | LangChain | — | Scaffolded |
| 11 | **Transaction Agent** | 8072 | Google ADK + A2A SDK | GPT-4o (LiteLLM) | Fully Implemented |

### Human-in-the-Loop Implementations

| Module | Framework | Description |
|--------|-----------|-------------|
| `agents/a2a_human_in_loop/` | Google ADK + `RemoteA2aAgent` | A2A-based HITL — reimbursement agent delegates >$100 approvals to a remote approval agent via A2A |
| `agents/langgraph_human_loop/` | LangGraph + `MemorySaver` + `interrupt()` | Full multi-agent graph: Router → 5 agents → human review → synthesizer |
| `agents/langgraph_human_loop/human_loop_fastapi/` | LangGraph + Custom MySQLSaver + FastAPI | Production-grade HITL with persistent MySQL checkpointing, REST API for chat + approval |
| `agents/langgraph_human_loop/chatbot_with_hitl.py` | LangGraph + `interrupt()` + `Command(resume=)` | Stock trading bot — `purchase_stock` tool uses `interrupt()` for human approval |
| `agents/langgraph_human_loop/chat_api_human_langgraph.py` | LangGraph + `interrupt()` | BaristaBot cafe ordering system with HITL order confirmation |
| `agents/langgraph_human_loop/support_agent.py` | LangGraph + Custom MySQLSaver + FastAPI | TechCorp support agent with MySQL-backed checkpointing and full HITL via REST |

---

## Detailed Agent Deep-Dives

### Order Agent (Port 8070)
- **Framework**: LangGraph `create_react_agent` + A2A SDK
- **LLM**: GPT-4o via `ChatOpenAI`
- **Tools**: `create_order`, `get_order_status`, `cancel_order`, `list_orders` (stub HTTP calls)
- **Memory**: `MemorySaver` (in-memory per thread)
- **Response Format**: Pydantic `OrderResponseFormat` (status + message)
- **Server**: Starlette + Uvicorn via A2A
- **Subfolder structure**:
  - `workflow/state.py` — `OrderState` Pydantic model with customer info, items, validation/payment status, conversation messages
  - `workflow/graph.py, nodes.py, edges.py, chain.py, tools.py` — scaffolded
  - `agent/hello_world.py` — simple `HelloWorldAgent` class

### Payment Agent (Port 8075)
- **Framework**: Raw A2A SDK (no LLM framework — direct `AsyncOpenAI` client)
- **LLM**: Meta-Llama 3.1 8B via OpenRouter
- **Tools**: `process_payment`, `get_payment_status`, `refund_payment`, `list_payments` (stubs)
- **Tool Schema Generation**: Dynamic via Python `inspect` module → OpenAI function calling format
- **Pattern**: Custom LLM loop with `tool_choice="auto"`, iterative tool execution

### Transaction Agent (Port 8072)
- **Framework**: Google ADK (`LlmAgent`) + A2A SDK
- **LLM**: GPT-4o via LiteLLM
- **Tools**: `verify_transaction`, `get_user_address`, `confirm_transaction`
- **Pattern**: Structured JSON input/output — accepts `INPUT_SCHEMA`, returns `OUTPUT_SCHEMA`
- **Output enforcement**: `_ensure_output_schema()` strips markdown fences, fills missing keys, removes extra keys
- **Client**: Full example with 3 patterns — single request, SSE streaming, batch concurrent

---

## LangGraph Multi-Agent HITL System

The most architecturally rich component lives in `agents/langgraph_human_loop/`.

### Graph Architecture
```
START → Router → [order|payment|delivery|shipping|refund] agents
                          │
                    should_review?
                     /          \
                  yes            no
                   │              │
             human_review     synthesize
                   │              │
              synthesize        END
                   │
                  END
```

### Key Components

| File | Role |
|------|------|
| `state.py` | Shared `AgentState` (Pydantic) with typed result models per agent |
| `router.py` | Keyword-based intent router with multi-agent combo detection, escalation keywords |
| `agents.py` | 5 simulated agent functions (order, delivery, payment, shipping, refund) |
| `human_loop.py` | HITL interrupt node + response synthesizer + conditional edges |
| `graph.py` | `StateGraph` builder with `interrupt_before=["human_review"]`, CLI interactive loop |
| `api.py` | FastAPI REST: `/chat`, `/human-review`, `/status/{sid}`, `/pending-reviews` |

### HITL Triggers
- Delivery delays → supervisor compensation review
- Payment failures → fraud verification
- High-value refunds (>$100)
- Legal/escalation keywords ("fraud", "sue", "manager")
- Unknown intent → human clarification

### Custom MySQLSaver
Both `support_agent.py` and `human_loop_fastapi/graph.py` implement a custom `MySQLSaver` extending `BaseCheckpointSaver`:
- Thread-safe pymysql connections
- Pickle serialization for checkpoint/metadata
- `from_conn_string()` factory with URL-encoded password support
- Tables: `checkpoints` + `checkpoint_writes`

---

## API Layer (`api/`)

- **Status**: Scaffolded — `api/main.py` is empty
- **Structure**: `router/`, `services/`, `utils/`, `client/`, `hosting/` — directories ready
- **Intended**: Central API gateway for the orchestrator system

---

## Client Layer (`client/`)

All clients follow identical patterns — A2A JSON-RPC clients using `httpx`:

| Client | Target Port | Sample Query |
|--------|-------------|--------------|
| `order_client.py` | 8070 | "What is my order status 123" |
| `shipping_client.py` | 8071 | "What is shipping status ID=12345" |
| `returns_client.py` | 8072 | "I want to return my order #12345" |
| `notification_agent.py` | 8073 | "Show me my notifications" |
| `payment_agent.py` | 8075 | "Tell me about my payment details" |
| `delivery_agent.py` | 8076 | "What's the delivery status of order ORD-12345" |
| `travel_assitant.py` | 9090 | "What is my order status 123" |
| `langchain_client.py` | — | LangChain middleware demo (logging, summarization, HITL) |

### Client Capabilities
1. **Agent card discovery** via `GET /.well-known/agent.json`
2. **Non-streaming** `message/send` via JSON-RPC 2.0
3. **True streaming** via `httpx.stream()` with SSE/JSON chunk parsing
4. **Multi-turn conversations** with `contextId` threading

---

## Protocols & Communication

| Protocol | Usage |
|----------|-------|
| **A2A (Agent-to-Agent)** | Primary inter-agent protocol. Agents expose `/.well-known/agent.json` (agent cards with skills). Tasks exchanged via JSON-RPC 2.0 |
| **JSON-RPC 2.0** | Transport layer for A2A — `message/send` (blocking), `message/stream` (SSE) |
| **MCP** | Listed in dependencies (`mcp==1.19.0`, `langchain-mcp-adapters`), `mcp_servers/` directory scaffolded |
| **SSE (Server-Sent Events)** | Streaming responses via `text/event-stream` for progressive updates |
| **REST / FastAPI** | Used by HITL systems — chat + human approval endpoints |

---

## Technology Stack

### AI Frameworks (per `pyproject.toml`)

| Category | Packages |
|----------|----------|
| **LangGraph / LangChain** | `langgraph==1.0.2`, `langchain==1.0.2`, `langchain-openai`, `langchain-litellm`, `langchain-mcp-adapters` |
| **Google ADK** | `google-adk[a2a]==1.19.0` |
| **A2A SDK** | `a2a-sdk[http-server]==0.3.16` |
| **CrewAI** | `crewai[tools]>=0.80.0,<1.0.0` |
| **BeeAI** | `beeai-framework[a2a]==0.1.75` |
| **Strands Agents** | `strands-agents[a2a]` |
| **AutoGen** | `autogen-agentchat>=0.7.5`, `autogen-ext[openai]>=0.7.5` |
| **MCP** | `mcp==1.19.0` |
| **LiteLLM** | `litellm==1.80.16` (unified LLM gateway) |

### Infrastructure

| Category | Packages |
|----------|----------|
| **Server** | Starlette + Uvicorn (A2A), FastAPI (HITL APIs) |
| **Database** | `pymysql>=1.1.2` (MySQL checkpointing) |
| **HTTP** | `httpx` (async clients), `boto3` / `botocore` (AWS) |
| **Search** | `duckduckgo-search` |

### Planned (empty dependency groups in `pyproject.toml`)
- OpenAI Agents SDK
- LlamaIndex Workflows
- Microsoft Agents
- Semantic Kernel

---

## Directory Structure

```
order_support_orchestrator_agents/
├── main.py                          # Entry point placeholder
├── pyproject.toml                   # Dependencies & tool config
├── README.md
├── create_summary_doc.py            # Generate Word doc project summary
│
├── agents/                          # All agent implementations
│   ├── order_agent/                 # LangGraph — port 8070
│   ├── shipping_agent/              # Google ADK — port 8071
│   ├── returns_agent/               # CrewAI — port 8072
│   ├── notification_agent/          # Strands — port 8073
│   ├── payment_agent/               # Raw OpenAI — port 8075
│   ├── delivery_agent/              # AutoGen — port 8076
│   ├── knowledge_agent/             # LangGraph — TBD
│   ├── tracking_agent/              # No framework — TBD
│   ├── escalation_agent/            # AutoGen — TBD
│   ├── transcation_agent/           # Google ADK — port 8072
│   ├── travel_assitant_agent/       # LangChain — port 9090
│   ├── a2a_human_in_loop/           # ADK HITL via RemoteA2aAgent
│   ├── langgraph_human_loop/        # LangGraph HITL (multiple variants)
│   ├── binary_llm_apps/             # Binary data experiments
│   └── projects_deepdive/           # Reference materials (PDFs)
│
├── api/                             # Central API gateway (scaffolded)
│   ├── main.py
│   ├── router/
│   ├── services/
│   ├── utils/
│   ├── client/
│   └── hosting/
│
├── client/                          # A2A JSON-RPC test clients
│   ├── order_client.py
│   ├── shipping_client.py
│   ├── returns_client.py
│   ├── notification_agent.py
│   ├── payment_agent.py
│   ├── delivery_agent.py
│   ├── travel_assitant.py
│   └── langchain_client.py
│
├── common/                          # Shared models & utils (scaffolded)
│   ├── model/
│   └── utils/
│
├── mcp_servers/                     # MCP server implementations (scaffolded)
├── notebooks/                       # Jupyter notebooks
└── samples/                         # Sample code & experiments
```

### Per-Agent Subfolder Convention

Each agent follows a consistent internal structure:

```
<agent_name>/
├── main.py              # A2A server entry-point (Uvicorn)
├── README.md            # Agent-specific documentation
├── agent/               # Core agent logic / classes
├── agentcard/           # Agent card definition
├── client/              # Agent-specific test client
├── evaluation/          # Test harness (scaffolded)
├── executor/            # A2A AgentExecutor bridge
├── hello/               # Hello-world / smoke-test agent
├── memory/              # Memory / session management
├── prompt/              # System prompts & instructions
├── tools/               # Tool definitions (functions)
├── utils/               # Internal utilities
└── workflow/            # LangGraph state, nodes, edges, graph
```

---

## Key Architectural Patterns

| Pattern | Where Used |
|---------|------------|
| **Multi-framework polyglot** | Each agent uses a different AI framework — serves as a comparative learning resource |
| **A2A agent discovery** | All agents expose `AgentCard` with skills at `/.well-known/agent.json` |
| **Structured JSON I/O** | Transaction agent demonstrates strict input/output schema enforcement |
| **Human-in-the-Loop (3 variants)** | (1) A2A `LongRunningFunctionTool`, (2) LangGraph `interrupt()` + `Command(resume=)`, (3) FastAPI REST approval |
| **Custom checkpointing** | `MySQLSaver` — custom `BaseCheckpointSaver` for LangGraph persistence in MySQL |
| **Streaming everywhere** | Clients demonstrate SSE-based incremental streaming with chunk counting |
| **Multi-agent fan-out** | LangGraph router invokes multiple agents in parallel (e.g., "cancel order and refund") |
| **Evaluation scaffolding** | Every agent has an `evaluation/` directory ready for test harnesses |
| **Memory scaffolding** | Every agent has a `memory/` directory — OpenSearch-backed ADK memory service available |

---

## Running the Project

### Prerequisites
- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) (recommended package manager)
- OpenAI API key (for GPT-4o agents)
- MySQL (for HITL checkpointing, optional)

### Quick Start

```bash
# Install dependencies
uv sync

# Start an agent server (e.g., Order Agent)
uv run agents/order_agent/main.py

# In another terminal, run the client
uv run client/order_client.py

# Or run the Transaction Agent with its dedicated client
uv run agents/transcation_agent/transcation_agent_server.py
uv run agents/transcation_agent/transcation_result_client.py
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | Required for GPT-4o agents |
| `OPENROUTER_API_KEY` | — | Required for Payment Agent (Llama 3.1) |
| `TRANSACTION_MODEL` | `gpt-4o` | LLM model for Transaction Agent |
| `HOST` | `localhost` | Server bind address |
| `PORT` | varies | Per-agent port (see agent table above) |

---

## Maturity Assessment

| Component | Status |
|-----------|--------|
| Order Agent | ✅ Implemented |
| Payment Agent | ✅ Implemented |
| Transaction Agent | ✅ Fully Implemented (server + client + structured I/O) |
| A2A Human-in-Loop | ✅ Implemented |
| LangGraph HITL System | ✅ Fully Implemented (graph + API + CLI + MySQL) |
| All A2A Clients | ✅ Implemented (streaming + non-streaming + multi-turn) |
| Shipping / Returns / Notification / Knowledge / Tracking / Escalation / Delivery / Travel Agents | 🟡 Scaffolded |
| API Gateway | 🟡 Scaffolded |
| Common Utilities | 🟡 Scaffolded |
| MCP Servers | 🟡 Empty Placeholder |
| Evaluation Suites | 🟡 Scaffolded Per Agent |
