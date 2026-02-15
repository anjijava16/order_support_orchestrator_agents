# shipping_tools.py (or include in the same file)
import os
from collections.abc import AsyncIterable
from typing import Any, Optional

import httpx
from google.adk.agents.llm_agent import LlmAgent
from google.adk.artifacts import InMemoryArtifactService
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# ----------------------------------------------------------------------
# Shipping tools (plain async functions with docstrings)
# ----------------------------------------------------------------------

async def get_shipping_rates(
    origin_zip: str,
    destination_zip: str,
    weight_lbs: float,
    package_size: str = "medium"
) -> dict:
    """
    Get available shipping rates for a package.

    Args:
        origin_zip: ZIP code of the sender.
        destination_zip: ZIP code of the recipient.
        weight_lbs: Weight of the package in pounds.
        package_size: Size category: "small", "medium", or "large".

    Returns:
        A dictionary with carrier names and rates, or an error.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.example.com/shipping/rates",
                json={
                    "origin": origin_zip,
                    "destination": destination_zip,
                    "weight": weight_lbs,
                    "size": package_size,
                },
            )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": f"Failed to fetch rates: {e}"}


async def track_shipment(tracking_number: str) -> dict:
    """
    Track a shipment by its tracking number.

    Args:
        tracking_number: The carrier's tracking number.

    Returns:
        Current status and location of the shipment.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.example.com/shipping/track/{tracking_number}"
            )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": f"Tracking failed: {e}"}


async def create_shipment(
    origin_address: str,
    destination_address: str,
    weight_lbs: float,
    carrier: str = "fedex"
) -> dict:
    """
    Create a new shipment and obtain a tracking number.

    Args:
        origin_address: Full address of the sender.
        destination_address: Full address of the recipient.
        weight_lbs: Package weight in pounds.
        carrier: Preferred carrier (e.g., "fedex", "ups", "usps").

    Returns:
        Shipment details including tracking number and label URL.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.example.com/shipping/shipments",
                json={
                    "origin": origin_address,
                    "destination": destination_address,
                    "weight": weight_lbs,
                    "carrier": carrier,
                },
            )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": f"Shipment creation failed: {e}"}


# ----------------------------------------------------------------------
# Shipping Agent – built with ADK LlmAgent
# ----------------------------------------------------------------------

SHIPPING_INSTRUCTIONS = """
You are a specialised assistant for shipping and logistics. Your sole purpose is to help users with tasks such as:

- Getting shipping rates between two addresses.
- Tracking an existing shipment.
- Creating a new shipment.

Use the available tools (get_shipping_rates, track_shipment, create_shipment) to answer queries.
If the user asks about anything unrelated to shipping, politely state that you cannot help with that topic and can only assist with shipping‑related questions.
Do not attempt to answer unrelated questions or use tools for other purposes.
"""

class ShippingAgent:
    """Shipping Agent built with Google ADK."""

    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self):
        self._agent = self._build_agent()
        self._user_id = "shipping_user"          # can be overridden per session
        self._runner = Runner(
            app_name=self._agent.name,
            agent=self._agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            # memory_service can be added if needed
        )

    def get_processing_message(self) -> str:
        """Return a status message for ongoing processing."""
        return "Processing your shipping request..."

    def _build_agent(self) -> LlmAgent:
        """Build the ADK agent with tools and instructions."""
        # Use environment variable for model, default to GPT-4o via LiteLLM
        model_name = os.getenv("SHIPPING_MODEL", "gpt-4o")
        return LlmAgent(
            model=LiteLlm(model=model_name),
            name="shipping_agent",
            description="Handles shipping inquiries: rates, tracking, and shipment creation.",
            instruction=SHIPPING_INSTRUCTIONS,
            tools=[
                get_shipping_rates,
                track_shipment,
                create_shipment,
            ],
        )

    async def stream(self, query: str, context_id: str) -> AsyncIterable[dict[str, Any]]:
        """
        Stream agent responses for a given query and session ID (context_id).
        Yields dictionaries with keys: is_task_complete, require_user_input, content.
        """
        # Retrieve or create a session using context_id as the session ID
        session_service = self._runner.session_service
        session = await session_service.get_session(
            app_name=self._agent.name,
            user_id=self._user_id,
            session_id=context_id,
        )
        if session is None:
            session = await session_service.create_session(
                app_name=self._agent.name,
                user_id=self._user_id,
                session_id=context_id,
            )

        # Wrap the query in a GenAI Content object
        content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=query)]
        )

        # Run the agent and process events
        async for event in self._runner.run_async(
            user_id=self._user_id,
            session_id=session.id,
            new_message=content,
        ):
            if event.is_final_response():
                # Final answer – extract text from the event content
                response_text = ""
                if event.content and event.content.parts:
                    # Concatenate all text parts (ignore non‑text parts)
                    texts = [p.text for p in event.content.parts if p.text]
                    response_text = "\n".join(texts)

                    # If no text but there is a function response, dump it as JSON
                    if not response_text:
                        for part in event.content.parts:
                            if part.function_response:
                                response_text = str(part.function_response.model_dump())
                                break

                yield {
                    "is_task_complete": True,
                    "require_user_input": False,
                    "content": response_text,
                }
                break
            else:
                # Intermediate event – yield a status update
                # You can customise the message based on event.type if desired
                yield {
                    "is_task_complete": False,
                    "require_user_input": False,
                    "content": self.get_processing_message(),
                }

import logging
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    InternalError,
    InvalidParamsError,
    Part,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils import new_agent_text_message, new_task
from a2a.utils.errors import ServerError


logger = logging.getLogger(__name__)


class ShippingAgentExecutor(AgentExecutor):
    """A2A Executor for the Shipping Agent."""

    def __init__(self):
        self.agent = ShippingAgent()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        error = self._validate_request(context)
        if error:
            raise ServerError(error=InvalidParamsError())

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
                        name="shipping_result",
                    )
                    await updater.complete()
                    break

        except Exception as e:
            logger.error(f"Error during streaming: {e}")
            raise ServerError(error=InternalError()) from e

    def _validate_request(self, context: RequestContext) -> bool:
        # Add any request validation if needed
        return False

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        raise ServerError(error=UnsupportedOperationError())
# main.py (excerpt)
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


# Define host and port
host = "localhost"
port = 8071



# --- Shipping Agent ---
shipping_skill = AgentSkill(
    id="shipping_management",
    name="Shipping Management Tool",
    description="Helps users get shipping rates, track shipments, and create new shipments.",
    tags=["shipping", "logistics"],
    examples=[
        "What's the shipping rate from 90210 to 10001 for a 5lb package?",
        "Track my package number 123456789",
        "Create a shipment from Boston to Seattle",
    ],
)
shipping_capabilities = AgentCapabilities(streaming=True, push_notifications=False)
shipping_agent_card = AgentCard(
    name="Shipping Agent",
    description="Specialised assistant for shipping and logistics.",
    url=f"http://{host}:{port}/",
    version="1.0.0",
    default_input_modes=["text", "text/plain"],
    default_output_modes=["text", "text/plain"],
    capabilities=shipping_capabilities,
    skills=[shipping_skill],
)

# --- Shared infrastructure for both agents ---
httpx_client = httpx.AsyncClient()
push_config_store = InMemoryPushNotificationConfigStore()
push_sender = BasePushNotificationSender(
    httpx_client=httpx_client, config_store=push_config_store
)
task_store = InMemoryTaskStore()

# Create  request handlers, each with its own executor and agent card


shipping_handler = DefaultRequestHandler(
    agent_executor=ShippingAgentExecutor(),
    task_store=task_store,
    push_config_store=push_config_store,
    push_sender=push_sender,
)

# Build separate A2A applications for each agent

shipping_app = A2AStarletteApplication(
    agent_card=shipping_agent_card, http_handler=shipping_handler
)


if __name__ == "__main__":
    uvicorn.run(shipping_app.build(), host=host, port=port)