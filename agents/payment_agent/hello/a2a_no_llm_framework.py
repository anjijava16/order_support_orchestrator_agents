import json
import logging
import os
from typing import Any, Dict, List, Optional

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    Part,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils import new_task
from a2a.utils.errors import ServerError
from openai import AsyncOpenAI
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Payment Tools (no persistent storage – stubs for future implementation)
# ----------------------------------------------------------------------
class PaymentTools:
    """Collection of payment-related functions (stubs for now)."""

    def process_payment(
        self,
        amount: float,
        currency: str = "USD",
        payment_method: str = "card",
        user_id: str = "guest",
    ) -> Dict[str, Any]:
        """
        Process a payment.

        (Stub – replace with real logic later.)
        """
        # TODO: Integrate with payment gateway, database, or RAG.
        return {
            "message": f"Payment of {amount} {currency} via {payment_method} received (stub).",
            "payment_id": "stub_payment_id",
            "status": "simulated",
        }

    def get_payment_status(
        self, payment_id: str, user_id: str = "guest"
    ) -> Dict[str, Any]:
        """
        Get the status of a payment.

        (Stub – replace with real logic later.)
        """
        return {
            "message": f"Status for payment {payment_id} is simulated as 'completed'.",
            "payment_id": payment_id,
            "status": "simulated_completed",
        }

    def refund_payment(
        self, payment_id: str, reason: str = "", user_id: str = "guest"
    ) -> Dict[str, Any]:
        """
        Refund a previously processed payment.

        (Stub – replace with real logic later.)
        """
        return {
            "message": f"Refund for payment {payment_id} processed (stub). Reason: {reason}",
            "payment_id": payment_id,
            "status": "simulated_refunded",
        }

    def list_payments(
        self, user_id: str = "guest", limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        List recent payments for a user.

        (Stub – replace with real logic later.)
        """
        # Return an empty list as placeholder
        return []


# ----------------------------------------------------------------------
# Payment Agent Executor (A2A)
# ----------------------------------------------------------------------
class PaymentAgentExecutor(AgentExecutor):
    """A2A AgentExecutor for payment operations using an LLM and tools."""

    def __init__(self, api_key: Optional[str] = None):
        # Use environment variable or provided key
        self.client = AsyncOpenAI(
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "http://localhost:8075",
                "X-Title": "Payment Agent",
            },
        )
        self.model = os.getenv("PAYMENT_MODEL", "meta-llama/llama-3.1-8b-instruct")
        self.system_prompt = (
            "You are a specialised assistant for payment processing. "
            "Your tasks include processing payments, checking payment status, "
            "issuing refunds, and listing past payments. "
            "Use the provided tools to perform these actions. "
            "If the user asks about anything unrelated to payments, politely state "
            "that you cannot help with that topic and can only assist with payment‑related queries. "
            "Do not attempt to answer unrelated questions or use tools for other purposes."
        )

        # Instantiate the tools class
        self.tools = PaymentTools()

        # Build the function schemas for the LLM
        self.openai_tools = self._build_tools_schemas()

    def _build_tools_schemas(self):
        """Convert methods of PaymentTools into OpenAI function schemas."""
        schemas = []
        tool_names = [
            "process_payment",
            "get_payment_status",
            "refund_payment",
            "list_payments",
        ]
        for name in tool_names:
            method = getattr(self.tools, name)
            schema = self._extract_function_schema(method)
            schemas.append({"type": "function", "function": schema})
        return schemas

    def _extract_function_schema(self, func):
        """Extract OpenAI function schema from a Python function (copied from reference)."""
        import inspect

        sig = inspect.signature(func)
        docstring = inspect.getdoc(func) or ""
        lines = docstring.split("\n")
        description = lines[0] if lines else func.__name__

        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            param_type = "string"
            param_description = f"Parameter {param_name}"

            if param.annotation != inspect.Parameter.empty:
                if param.annotation in (int, float):
                    param_type = "number"
                elif param.annotation == bool:
                    param_type = "boolean"
                elif param.annotation == list:
                    param_type = "array"
                elif param.annotation == dict:
                    param_type = "object"

            if param.default == inspect.Parameter.empty:
                required.append(param_name)

            properties[param_name] = {
                "type": param_type,
                "description": param_description,
            }

        return {
            "name": func.__name__,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }

    async def _process_request(
        self,
        message_text: str,
        context: RequestContext,
        task_updater: TaskUpdater,
    ) -> None:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": message_text},
        ]

        max_iterations = 10
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=self.openai_tools,
                    tool_choice="auto",
                    temperature=0.1,
                    max_tokens=4000,
                )

                message = response.choices[0].message

                messages.append(
                    {
                        "role": "assistant",
                        "content": message.content,
                        "tool_calls": message.tool_calls,
                    }
                )

                if message.tool_calls:
                    # Execute each tool call
                    for tool_call in message.tool_calls:
                        function_name = tool_call.function.name
                        function_args = json.loads(tool_call.function.arguments)

                        logger.debug(
                            f"Calling function: {function_name} with args: {function_args}"
                        )

                        method = getattr(self.tools, function_name, None)
                        if method:
                            result = method(**function_args)
                        else:
                            result = {"error": f"Unknown tool {function_name}"}

                        # Serialize result
                        if hasattr(result, "model_dump"):
                            result_json = json.dumps(result.model_dump())
                        elif isinstance(result, dict):
                            result_json = json.dumps(result)
                        else:
                            result_json = str(result)

                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": result_json,
                            }
                        )

                    await task_updater.update_status(
                        TaskState.working,
                        message=task_updater.new_agent_message(
                            [TextPart(text="Processing payment request...")]
                        ),
                    )
                    continue

                # Final response
                if message.content:
                    parts = [TextPart(text=message.content)]
                    await task_updater.add_artifact(parts)
                    await task_updater.complete()
                break

            except Exception as e:
                logger.error(f"Error in LLM call: {e}")
                error_parts = [TextPart(text=f"An error occurred: {e!s}")]
                await task_updater.add_artifact(error_parts)
                await task_updater.complete()
                break

        if iteration >= max_iterations:
            error_parts = [
                TextPart(text="Maximum iterations exceeded. Please try again.")
            ]
            await task_updater.add_artifact(error_parts)
            await task_updater.complete()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        # Validate request
        if not context.message or not context.message.parts:
            raise ServerError(error="No message provided")

        # Get or create task
        task = context.current_task
        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.context_id)

        # Extract text from message parts
        message_text = ""
        for part in context.message.parts:
            if isinstance(part.root, TextPart):
                message_text += part.root.text

        if not message_text.strip():
            await updater.add_artifact(
                [TextPart(text="I didn't receive any text. Please ask a question.")]
            )
            await updater.complete()
            return

        await updater.submit()
        await updater.start_work()
        await self._process_request(message_text, context, updater)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise ServerError(error=UnsupportedOperationError())


# ----------------------------------------------------------------------
# Optional: Agent Card definition
# ----------------------------------------------------------------------
def create_payment_agent_card(host: str = "localhost", port: int = 8070) -> AgentCard:
    skill = AgentSkill(
        id="payment_management",
        name="Payment Management",
        description=(
            "Process payments, check payment status, issue refunds, "
            "and list recent payments. (Currently a stub – ready for RAG integration.)"
        ),
        tags=["payments", "transactions", "refunds"],
        examples=[
            "Pay $50 for order #12345 using my card",
            "What's the status of payment pay_abc123?",
            "Refund payment pay_xyz789 because the item was damaged",
            "Show my last 5 payments",
        ],
    )
    capabilities = AgentCapabilities(streaming=True, push_notifications=False)
    return AgentCard(
        name="Payment Agent",
        description="Specialised assistant for payment processing (stub implementation).",
        url=f"http://{host}:{port}/",
        version="1.0.0",
        default_input_modes=["text", "text/plain"],
        default_output_modes=["text", "text/plain"],
        capabilities=capabilities,
        skills=[skill],
    )


import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import (
    BasePushNotificationSender,
    InMemoryPushNotificationConfigStore,
    InMemoryTaskStore,
)
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

host = "localhost"
port = 8075
# Create handler and app
returns_handler = DefaultRequestHandler(
    agent_executor=PaymentAgentExecutor(),
    task_store=InMemoryTaskStore(),
)
returns_app = A2AStarletteApplication(
    agent_card=create_payment_agent_card(host, port), http_handler=returns_handler
).build()

import uvicorn

uvicorn.run(returns_app, host=host, port=port)
