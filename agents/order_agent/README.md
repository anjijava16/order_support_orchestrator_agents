# Order Agent (A2A + LangGraph)

A specialized order management assistant built with **LangGraph** and the **A2A (Agent-to-Agent)** framework.  
It leverages an LLM (GPT‑4o by default) and a set of order‑related tools to help users create orders, check order status, cancel orders, and list their orders.  
> ⚠️ **Tools are stubs** that call a placeholder API (`https://api.example.com/orders`) – replace with your actual order service endpoints.

---

## ✨ Features

- **Create orders** – Place an order for a specified item and quantity.
- **Check order status** – Retrieve the current status of an existing order.
- **Cancel orders** – Cancel an order by its ID.
- **List orders** – Show all orders placed by a user.
- **LLM‑powered conversation** – Understands natural language requests and uses tools accordingly.
- **Structured responses** – Returns a consistent format with status (`input_required`, `completed`, `error`) and a message.
- **Multi‑turn tool use** – The agent can call multiple tools in sequence to fulfill a request.
- **A2A compliant** – Runs as an A2A agent server with task management, streaming, and push notifications.
- **LangGraph orchestration** – Uses LangGraph’s `create_react_agent` for robust state management and tool execution.

---

## 🛠️ Tech Stack

| Component               | Technology                         | Description                                                                                   |
|-------------------------|------------------------------------|-----------------------------------------------------------------------------------------------|
| **Agent Framework**     | A2A (Agent-to-Agent)               | Google’s open protocol for agent communication; provides task management, event queues, etc. |
| **Orchestration**       | LangGraph                          | Stateful, multi‑actor LLM application framework; manages the ReAct agent loop.                |
| **LLM Integration**     | LangChain OpenAI                    | LangChain wrapper for OpenAI‑compatible models (GPT‑4o).                                      |
| **LLM Model**           | GPT‑4o (default)                    | Advanced LLM for understanding order queries and invoking tools.                              |
| **Tools**               | LangChain `@tool` decorator         | Defines order tools (create, get, cancel, list) – currently stubs calling a mock API.        |
| **Memory**              | `MemorySaver` (in‑memory)           | LangGraph checkpointing for conversation persistence (per thread).                            |
| **Server Framework**    | Starlette + Uvicorn                 | ASGI web server to host A2A endpoints.                                                        |
| **HTTP Client**         | `httpx`                             | Async HTTP calls to the order service API (and for A2A push notifications).                   |
| **Data Validation**     | Pydantic                            | Used for structured response format (`OrderResponseFormat`) and A2A types.                    |
| **Configuration**       | Environment variables + `os.getenv` | API keys and model selection.                                                                 |
| **Logging**             | Python `logging`                    | Debug and error logging for the agent and server.                                             |
| **CLI**                 | Click                               | (Optional) Could be used for command‑line entry point (not heavily used here).                |

---

## 📋 Prerequisites

- Python 3.9+
- An [OpenAI](https://openai.com/) API key (or any OpenAI‑compatible endpoint if you change the model)
- A backend order service that implements the expected REST endpoints (or modify the tools to integrate with your system)

---

## 📦 Installation

1. **Clone the repository**  
   ```bash
   git clone https://github.com/your-repo/order-agent.git
   cd order-agent
   ```

2. **Create and activate a virtual environment**  
   ```bash
   python -m venv venv
   source venv/bin/activate   # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**  
   ```bash
   pip install langchain langchain-openai langgraph a2a httpx uvicorn starlette pydantic click
   ```

---

## ⚙️ Configuration

Set the following environment variables (e.g., in a `.env` file or shell):

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | Your OpenAI API key | **(required)** |
| `model_source` | Model provider (`google` not yet implemented; only `openai` currently) | `openai` |

The agent currently uses `gpt-4o` with temperature 0. You can change the model by modifying the `ChatOpenAI` instantiation in `OrderAgent.__init__`.

---

## 🚀 Usage

Start the A2A agent server:

```bash
python order_agent.py
```

By default the server runs on `http://localhost:8070`.  
The agent card is registered with the A2A runtime, so any A2A client can discover and interact with it.

### Example interactions (via an A2A client):

- *“I'd like to order a pizza”*
- *“What's the status of my order #12345?”*
- *“Cancel my order #67890”*
- *“Show me all my orders”*

The agent will respond with natural language, using the tools as needed.

---

## 🔍 How It Works (Deep Dive)

### System Flow

```
┌────────────┐     ┌─────────────────┐     ┌─────────────────────┐     ┌─────────────────┐
│ A2A Client │────▶│ A2A Server       │────▶│ OrderAgentExecutor  │────▶│   OrderAgent    │
│ (any)      │     │ (Starlette app)  │     │                     │     │  (LangGraph)    │
└────────────┘     └─────────────────┘     └─────────────────────┘     └─────────────────┘
                                                      │                           │
                                                      ▼                           ▼
                                             ┌─────────────────┐      ┌─────────────────────┐
                                             │  Order Tools    │      │  MemorySaver        │
                                             │ (stub API calls)│      │ (per‑thread state)  │
                                             └─────────────────┘      └─────────────────────┘
```

1. **Client sends a task** (e.g., “Cancel order #123”) to the A2A endpoint `/tasks/send`.
2. **A2A request handler** (`DefaultRequestHandler`) validates the message, creates or retrieves a task, and invokes the `OrderAgentExecutor`.
3. **Executor** extracts the query and context ID, then calls the `OrderAgent.stream()` method.
4. **OrderAgent** (LangGraph ReAct agent) processes the query:
   - It uses the system prompt and tools.
   - The agent may call tools (e.g., `cancel_order`) and observe results.
   - The conversation state is saved via `MemorySaver` using the `thread_id` (which is the A2A task `context_id`).
5. **Streaming updates**:
   - As the agent runs, the executor yields status updates (e.g., “Processing your order request...”) back to the A2A client via the event queue.
   - When the agent finishes, it produces a structured response (`OrderResponseFormat`), which is converted to a final artifact.
6. **Task completion**: The executor marks the task as completed and sends the final message.

### Application Flow (Detailed)

- **Initialization**  
  `OrderAgent.__init__` sets up the LLM (`ChatOpenAI`), tools, and creates the LangGraph `create_react_agent` with a response formatter.

- **Streaming**  
  `OrderAgent.stream(query, context_id)`:
  1. Builds input messages (`[("user", query)]`).
  2. Streams the graph execution with `stream_mode='values'`.
  3. During streaming, it yields intermediate status messages for tool calls or tool results.
  4. At the end, it calls `get_agent_response(config)` to extract the structured output.

- **Response Formatting**  
  The agent is configured with `response_format=(self.FORMAT_INSTRUCTION, OrderResponseFormat)`.  
  LangGraph ensures the final output conforms to `OrderResponseFormat` (status + message).  
  `get_agent_response` reads this from the graph state and returns a unified dict.

- **A2A Integration**  
  `OrderAgentExecutor` adapts the `OrderAgent` to the A2A `AgentExecutor` interface:
  - `execute()` streams the agent’s responses and sends `TaskState` updates.
  - `cancel()` raises `UnsupportedOperationError` (cancellation not implemented).
  - Request validation is minimal (placeholder).

- **Agent Card**  
  In `main()`, an `AgentCard` is created with a skill describing order management capabilities. The server advertises this card, enabling discovery.

---

## 🔌 Extending with Real Order Service

The current tools use a mock API (`https://api.example.com/orders`). To integrate with a real order management system:

1. **Replace the base URL** in each tool (or make it configurable).
2. **Adjust request/response formats** to match your service.
3. **Add authentication** if needed (e.g., API keys in headers).
4. **Enhance error handling** to provide user‑friendly messages.

Example of a modified `create_order` tool with a real endpoint and auth:

```python
@tool
async def create_order(item: str, quantity: int = 1, user_id: str = "guest"):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://your-orders-api.com/orders",
            json={"item": item, "qty": quantity, "customer": user_id},
            headers={"Authorization": f"Bearer {os.getenv('ORDER_API_KEY')}"}
        )
        resp.raise_for_status()
        return resp.json()
```

You may also want to replace synchronous `httpx` calls with async versions to integrate better with LangGraph’s async streaming.

---

## 📁 Project Structure

```
order_agent.py                      # Main agent and server code
├── OrderAgent                      # LangGraph ReAct agent
├── OrderAgentExecutor              # A2A executor wrapper
├── order tools (create_order, etc.)# Stub tools for order operations
├── OrderResponseFormat             # Pydantic model for structured output
└── main()                          # Server startup with A2A app
```

---

## 🧪 Testing

Test the agent using any A2A client or by sending HTTP requests to the A2A endpoints.  
For a quick manual test, use `curl`:

```bash
curl -X POST http://localhost:8070/tasks/send \
  -H "Content-Type: application/json" \
  -d '{"message": {"parts": [{"text": "Create an order for 2 pizzas"}]}}'
```

> ⚠️ The exact payload may vary; refer to the [A2A protocol documentation](https://github.com/google/A2A).

---

## 📄 License

This project is provided as‑is without a specific license. If you intend to use it, please add your own license.

---

## 🙌 Contributing

Contributions are welcome! Feel free to open issues or pull requests to improve the stub implementation, add real order service backends, or enhance the agent’s capabilities.

---

## 📚 References

- [A2A Framework](https://github.com/google/A2A)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [LangChain Tools](https://python.langchain.com/docs/modules/agents/tools/)
- [OpenAI API](https://platform.openai.com/docs/api-reference)