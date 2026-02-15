# Payment Agent (A2A)

A specialized payment processing assistant built with the **A2A (Agent-to-Agent)** framework.  
It leverages an LLM (via OpenRouter) to handle payment-related queries such as processing payments, checking status, issuing refunds, and listing recent transactions.  
> ⚠️ **Current implementation uses stub functions** – it’s ready for integration with real payment gateways, databases, or RAG systems.

---

## ✨ Features

- **Process payments** – Accept amount, currency, payment method, and user ID (stub).
- **Check payment status** – Retrieve simulated status for a given payment ID.
- **Issue refunds** – Refund a payment with an optional reason.
- **List recent payments** – Placeholder returning an empty list.
- **LLM‑powered understanding** – Strictly focused on payment topics via a system prompt.
- **Multi‑turn tool use** – LLM can call payment functions sequentially.
- **A2A compliant** – Runs as an A2A agent server with task management and streaming support.

---

## 🛠️ Tech Stack

| Component               | Technology                         | Description                                                                                   |
|-------------------------|------------------------------------|-----------------------------------------------------------------------------------------------|
| **Agent Framework**     | A2A (Agent-to-Agent)               | Google’s open protocol for agent communication; provides task management, event queues, etc. |
| **LLM Integration**     | OpenRouter API                     | Unified API for multiple LLMs; used here with `AsyncOpenAI` client.                          |
| **LLM Model**           | Meta-Llama 3.1 8B (default)        | Lightweight instruct model for tool calling and payment conversations.                        |
| **Server Framework**    | Starlette + Uvicorn                 | ASGI web server to host A2A endpoints.                                                        |
| **Data Validation**     | Pydantic                           | Used by A2A for type-safe message and task structures.                                       |
| **Tool Schemas**        | Python `inspect` + JSON            | Dynamic generation of OpenAI-compatible function schemas from `PaymentTools` methods.        |
| **Configuration**       | Environment variables + `os.getenv`| API keys and model selection via `.env` or shell.                                             |
| **Logging**             | Python `logging`                   | Debug and error logging for the agent executor.                                               |
| **HTTP Client**         | `httpx` (via `AsyncOpenAI`)        | Async HTTP requests to OpenRouter.                                                            |
| **Serialization**       | `json`                             | Parsing tool arguments and returning results.                                                 |

---

## 📋 Prerequisites

- Python 3.9+
- An [OpenRouter](https://openrouter.ai/) API key (or any OpenAI‑compatible endpoint)

---

## 📦 Installation

1. **Clone the repository**  
   ```bash
   git clone https://github.com/your-repo/payment-agent.git
   cd payment-agent
   ```

2. **Create and activate a virtual environment**  
   ```bash
   python -m venv venv
   source venv/bin/activate   # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**  
   ```bash
   pip install a2a openai httpx uvicorn starlette pydantic
   ```

---

## ⚙️ Configuration

Set the following environment variables (e.g., in a `.env` file or shell):

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENROUTER_API_KEY` | Your OpenRouter API key | **(required)** |
| `PAYMENT_MODEL` | The LLM model to use | `meta-llama/llama-3.1-8b-instruct` |

Example (Linux/macOS):
```bash
export OPENROUTER_API_KEY="your-key-here"
export PAYMENT_MODEL="openai/gpt-4o"          # optional
```

---

## 🚀 Usage

Start the A2A agent server:

```bash
python payment_agent.py
```

By default the server runs on `http://localhost:8075`.  
The agent card is registered with the A2A runtime, so any A2A client can discover and interact with it.

### Example interactions (via an A2A client):

- *“Pay $50 for order #12345 using my card”*
- *“What's the status of payment pay_abc123?”*
- *“Refund payment pay_xyz789 because the item was damaged”*
- *“Show my last 5 payments”*

The agent will respond using the LLM, invoking the appropriate stub functions and returning a natural language answer.

---

## 🔍 How It Works (Deep Dive)

### System Flow

```
┌────────────┐     ┌─────────────────┐     ┌─────────────────────┐     ┌─────────────┐
│ A2A Client │────▶│ A2A Server       │────▶│ PaymentAgentExecutor│────▶│ OpenRouter  │
│ (any)      │     │ (Starlette app)  │     │                     │     │   LLM       │
└────────────┘     └─────────────────┘     └─────────────────────┘     └─────────────┘
                                                      │
                                                      ▼
                                             ┌─────────────────┐
                                             │  PaymentTools   │
                                             │ (stub functions)│
                                             └─────────────────┘
```

1. **Client sends a task** (e.g., “Refund payment pay_123”) to the A2A endpoint `/tasks/send`.
2. **A2A request handler** (`DefaultRequestHandler`) validates the message, creates or retrieves a task, and invokes the `PaymentAgentExecutor`.
3. **Executor initializes**:
   - Creates an `AsyncOpenAI` client pointing to OpenRouter.
   - Builds tool schemas from `PaymentTools` methods.
   - Sets a strict system prompt to limit domain.
4. **LLM conversation loop**:
   - The user message is appended to the message history.
   - The LLM is called with `tools` and `tool_choice="auto"`.
   - If the LLM returns tool calls, the executor executes the corresponding stub methods (e.g., `refund_payment`) and feeds the results back to the LLM.
   - This repeats until the LLM produces a final text response or the iteration limit is reached.
5. **Task updates** are sent via the A2A event queue (`TaskUpdater`) to keep the client informed of progress.
6. **Final response** is returned as an artifact with a `TextPart`, and the task is marked as completed.

### Application Flow (Detailed)

- **Initialization**  
  `PaymentAgentExecutor.__init__` sets up the LLM client, model, system prompt, and tool schemas by inspecting `PaymentTools` methods.

- **Request Handling**  
  `execute()` extracts the text from the incoming message parts, creates/retrieves a task, and starts the LLM loop via `_process_request()`.

- **LLM Loop**  
  `_process_request()`:
  1. Builds messages list (system + user).
  2. Calls OpenRouter chat completion with tools.
  3. If tool calls present:
     - Executes each tool (e.g., `process_payment`) with parsed arguments.
     - Appends tool results to messages.
     - Sends a “working” status update.
     - Loops to next LLM call.
  4. If no tool calls and `content` exists, adds final artifact and marks task complete.
  5. Handles errors and iteration limit.

- **Tool Execution**  
  Each tool method is a stub (e.g., returns a hardcoded JSON). In production, these would call external APIs or databases.

- **A2A Integration**  
  - `TaskUpdater` sends state changes (`submitted`, `working`, `completed`) and artifacts via the `EventQueue`.
  - The agent card (`create_payment_agent_card`) exposes the payment skill, making the agent discoverable.

---

## 🔌 Extending with Real Payment Logic

All payment functions are currently stubs – replace them with actual integrations:

- **`process_payment`** – Call a payment gateway (Stripe, PayPal, etc.) and store transaction details in a database.
- **`get_payment_status`** – Query the database or gateway for real status.
- **`refund_payment`** – Trigger a refund via the gateway.
- **`list_payments`** – Retrieve records from a database, optionally with filters.

You can also enhance the system by:
- Adding a **retrieval‑augmented generation (RAG)** component to answer questions about past transactions.
- Storing conversation history for context.
- Implementing authentication and user identification.

---

## 📁 Project Structure

```
payment_agent.py                # Main agent code
├── PaymentTools                # Stub functions (to be replaced)
├── PaymentAgentExecutor        # A2A executor with LLM orchestration
└── create_payment_agent_card() # Agent card definition for A2A
```

---

## 🧪 Testing

Test the agent using any A2A client or by sending HTTP requests to the A2A endpoints.  
For a quick manual test, use `curl`:

```bash
curl -X POST http://localhost:8075/tasks/send \
  -H "Content-Type: application/json" \
  -d '{"message": {"parts": [{"text": "Pay 25 euros"}]}}'
```

> ⚠️ The exact payload may vary; refer to the [A2A protocol documentation](https://github.com/google/A2A).

---

## 📄 License

This project is provided as‑is without a specific license. If you intend to use it, please add your own license.

---

## 🙌 Contributing

Contributions are welcome! Feel free to open issues or pull requests to improve the stub implementation, add real payment backends, or enhance the agent’s capabilities.

---

## 📚 References

- [A2A Framework](https://github.com/google/A2A)
- [OpenRouter Documentation](https://openrouter.ai/docs)
- [OpenAI Function Calling](https://platform.openai.com/docs/guides/function-calling)