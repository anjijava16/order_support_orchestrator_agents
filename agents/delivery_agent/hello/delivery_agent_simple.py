import asyncio
import logging
import os
from collections.abc import AsyncIterable
from typing import Any, Dict, List

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.base import TaskResult
from autogen_agentchat.messages import ChatMessage, TextMessage
from autogen_core import CancellationToken
from autogen_ext.models.openai import OpenAIChatCompletionClient

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    InternalError,
    InvalidParamsError,
    Part,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils import new_agent_text_message, new_task
from a2a.utils.errors import ServerError

host = "localhost"
port = 8076   # or any available port

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Delivery Tools (async functions)
# ----------------------------------------------------------------------

async def get_delivery_status(order_id: str) -> str:
    """
    Get the current delivery status of an order.

    Args:
        order_id: The unique order identifier (e.g., ORD-12345).

    Returns:
        A string describing the delivery status.
    """
    await asyncio.sleep(0.5)
    return f"Order {order_id} is currently 'Out for delivery' and expected today."


async def track_package(tracking_number: str) -> str:
    """
    Track a package using its tracking number.

    Args:
        tracking_number: The carrier tracking number (e.g., 1Z999AA10123456784).

    Returns:
        A string with tracking details.
    """
    await asyncio.sleep(0.5)
    return f"Package {tracking_number} is in transit, last seen at Chicago sorting facility."


async def reschedule_delivery(order_id: str, new_date: str, time_window: str = "any") -> str:
    """
    Reschedule a delivery to a new date and optional time window.

    Args:
        order_id: The order ID.
        new_date: Preferred new delivery date (e.g., '2025-03-20').
        time_window: Preferred time window (e.g., '10AM-2PM').

    Returns:
        Confirmation message.
    """
    await asyncio.sleep(0.5)
    return f"Delivery for order {order_id} rescheduled to {new_date} ({time_window}). Confirmation sent."


async def report_delivery_issue(order_id: str, issue_type: str, description: str) -> str:
    """
    Report a problem with a delivery (missing, damaged, delayed).

    Args:
        order_id: The order ID.
        issue_type: Type of issue (missing, damaged, delayed, etc.).
        description: Detailed description.

    Returns:
        Confirmation that the issue was reported.
    """
    await asyncio.sleep(0.5)
    return f"Issue reported for order {order_id}: '{issue_type}' – {description}. Support will contact you."


# ----------------------------------------------------------------------
# Delivery Agent (AutoGen-based, with per-session history)
# ----------------------------------------------------------------------

class DeliveryAgent:
    """AutoGen-based agent for delivery inquiries, maintaining per-session message history."""

    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self):
        # Configure the model client (adjust model and base_url as needed)
        # self.model_client = OpenAIChatCompletionClient(
        #     model=os.getenv("DELIVERY_MODEL", "gpt-4o"),
        # )
        # self.model_client = OpenAIChatCompletionClient(
        #    model="gpt-4o",  # or your preferred model
        #     #api_key="your-api-key",  # or use env variable        base_url="https://api.openai.com/v1",  # or OpenRouter etc.
        # )
        model_client = OpenAIChatCompletionClient(model="gpt-4o")

        # Create the AssistantAgent with tools
        self.agent = AssistantAgent(
            name="delivery_assistant",
            model_client=model_client,
            tools=[
                get_delivery_status,
                track_package,
                reschedule_delivery,
                report_delivery_issue,
            ],
            system_message=(
                "You are a specialised assistant for order delivery management. "
                "Your tasks include:\n"
                "- Providing the current delivery status of an order.\n"
                "- Tracking a package using a tracking number.\n"
                "- Rescheduling a delivery to a new date/time.\n"
                "- Reporting issues with a delivery (missing, damaged, etc.).\n\n"
                "Use the available tools to answer queries accurately. "
                "If the user asks about anything unrelated to deliveries, politely explain that you can only assist with delivery‑related questions. "
                "Always ask for missing information if the query is incomplete (e.g., order ID, tracking number).\n"
                "Keep your responses concise and helpful."
            ),
           # reflect_on_tool_use=True,
        )

        # Store conversation history per session
        self._session_histories: Dict[str, List[ChatMessage]] = {}

    # async def stream(self, query: str, session_id: str) -> AsyncIterable[Dict[str, Any]]:
    #     """
    #     Stream the agent's response for a given query and session.
    #     Yields dictionaries with keys: is_task_complete, require_user_input, content.
    #     """
    #     # Retrieve or initialize history for this session
    #     if session_id not in self._session_histories:
    #         self._session_histories[session_id] = []

    #     # Create a user message for the new query
    #     user_message = TextMessage(content=query, source="user")

    #     # Append it to the session history
    #     self._session_histories[session_id].append(user_message)

    #     # Yield a "working" status immediately
    #     yield {
    #         "is_task_complete": False,
    #         "require_user_input": False,
    #         "content": "Processing your delivery request...",
    #     }

    #     # Run the agent with the full conversation history
    #     final_text_parts: List[str] = []
    #     async for event in self.agent.run_stream(
    #         task=self._session_histories[session_id],  # pass the whole history
    #         cancellation_token=CancellationToken(),
    #     ):
    #         # `event` can be various message types (TextMessage, ToolCallMessage, etc.)
    #         # We need to store all events to keep history correct.
    #         self._session_histories[session_id].append(event)

    #         # If it's a text message, accumulate it for the final output
    #         if isinstance(event, TextMessage):
    #             final_text_parts.append(event.content)

    #     # The loop ends when the agent finishes. The final assistant message(s) are now in history.
    #     final_content = " ".join(final_text_parts).strip()
    #     if not final_content:
    #         # Fallback: try to get the last message content
    #         last_msg = self._session_histories[session_id][-1]
    #         final_content = getattr(last_msg, "content", "")

    #     # Yield the final response
    #     yield {
    #         "is_task_complete": True,
    #         "require_user_input": False,
    #         "content": final_content,
    #     }
    async def stream(self, query: str, session_id: str) -> AsyncIterable[Dict[str, Any]]:
        if session_id not in self._session_histories:
            self._session_histories[session_id] = []
        print("Initialized history for session:", session_id)
        user_message = TextMessage(content=query, source="user")
        print(f"Received query for session {session_id}: {query} and user message: {user_message}")
        self._session_histories[session_id].append(user_message)

        yield {
            "is_task_complete": False,
            "require_user_input": False,
            "content": "Processing your delivery request...",
        }

        # Run the agent with the full conversation history
        async for event in self.agent.run_stream(
            task=self._session_histories[session_id],
            cancellation_token=CancellationToken(),
        ):
            
            # Store every event
            self._session_histories[session_id].append(event)

            # (Optional) yield intermediate status for tool calls
            # if isinstance(event, ToolCallMessage):
            #     yield {...}

        # After streaming, find the last assistant TextMessage
        final_content = ""
        for msg in reversed(self._session_histories[session_id]):
            if isinstance(msg, TextMessage) and msg.source == "assistant":
                final_content = msg.content
                print(f"Final assistant message for session {session_id}: {final_content}")
                break

        if not final_content:
            final_content = "Sorry, I couldn't generate a response."

        yield {
            "is_task_complete": True,
            "require_user_input": False,
            "content": final_content,
        }


# ----------------------------------------------------------------------
# Delivery Agent Executor (A2A)
# ----------------------------------------------------------------------

class DeliveryAgentExecutor(AgentExecutor):
    """A2A Executor for the Delivery Agent."""

    def __init__(self):
        self.agent = DeliveryAgent()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        if not context.message or not context.message.parts:
            raise ServerError(error=InvalidParamsError("No message provided"))

        query = context.get_user_input()
        task = context.current_task
        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.context_id)

        try:
            async for item in self.agent.stream(query, task.context_id):
                is_task_complete = item["is_task_complete"]
                require_user_input = item["require_user_input"]

                if not is_task_complete and not require_user_input:
                    await updater.update_status(
                        TaskState.working,
                        new_agent_text_message(
                            item["content"],
                            task.context_id,
                            task.id,
                        ),
                    )
                elif require_user_input:
                    await updater.update_status(
                        TaskState.input_required,
                        new_agent_text_message(
                            item["content"],
                            task.context_id,
                            task.id,
                        ),
                        final=True,
                    )
                    break
                else:
                    await updater.add_artifact(
                        [Part(root=TextPart(text=item["content"]))],
                        name="delivery_result",
                    )
                    await updater.complete()
                    break

        except Exception as e:
            logger.error(f"Error during streaming: {e}")
            raise ServerError(error=InternalError()) from e

    def _validate_request(self, context: RequestContext) -> bool:
        return False

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise ServerError(error=UnsupportedOperationError())


# ----------------------------------------------------------------------
# Agent Card and Server Setup
# ----------------------------------------------------------------------

def create_delivery_agent_card() -> AgentCard:
    skill = AgentSkill(
        id="delivery_management",
        name="Delivery Management Tool",
        description="Handles delivery inquiries: status, tracking, rescheduling, and issue reporting.",
        tags=["delivery", "shipping", "tracking"],
        examples=[
            "What's the delivery status of order ORD-12345?",
            "Track package 1Z999AA10123456784",
            "Reschedule my delivery to tomorrow",
            "Report a missing package",
        ],
    )
    capabilities = AgentCapabilities(streaming=True, push_notifications=False)
    return AgentCard(
        name="Delivery Agent",
        description="Specialised assistant for order delivery management.",
        url=f"http://{host}:{port}/",
        version="1.0.0",
        default_input_modes=["text", "text/plain"], 
        default_output_modes=["text", "text/plain"],
        capabilities=capabilities,
        skills=[skill],
    )


# ----------------------------------------------------------------------
# Standalone Server Runner
# ----------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    from a2a.server.apps import A2AStarletteApplication
    from a2a.server.request_handlers import DefaultRequestHandler
    from a2a.server.tasks import InMemoryTaskStore

    agent_card = create_delivery_agent_card()
    executor = DeliveryAgentExecutor()
    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
    )
    app = A2AStarletteApplication(agent_card=agent_card, http_handler=handler).build()

    print(f"Starting Delivery Agent on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)