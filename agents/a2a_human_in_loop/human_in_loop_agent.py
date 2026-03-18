# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Any

from google.adk import Agent
from google.adk.tools.long_running_tool import LongRunningFunctionTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types


def reimburse(purpose: str, amount: float) -> str:
  """Reimburse the amount of money to the employee."""
  return {
      'status': 'ok',
  }


def ask_for_approval(
    purpose: str, amount: float, tool_context: ToolContext
) -> dict[str, Any]:
  """Ask for approval for the reimbursement."""
  return {
      'status': 'pending',
      'amount': amount,
      'ticketId': 'reimbursement-ticket-001',
  }


# root_agent = Agent(
#     model='gemini-2.0-flash',
#     name='reimbursement_agent',
#     instruction="""
#       You are an agent whose job is to handle the reimbursement process for
#       the employees. If the amount is less than $100, you will automatically
#       approve the reimbursement.

#       If the amount is greater than $100, you will
#       ask for approval from the manager. If the manager approves, you will
#       call reimburse() to reimburse the amount to the employee. If the manager
#       rejects, you will inform the employee of the rejection.
# """,
#     tools=[reimburse, LongRunningFunctionTool(func=ask_for_approval)],
#     generate_content_config=types.GenerateContentConfig(temperature=0.1),
# )

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

    def _build_agent(self) -> Agent:
        """Build the ADK agent with tools and instructions."""
        # Use environment variable for model, default to GPT-4o via LiteLLM
        model_name = os.getenv("SHIPPING_MODEL", "gpt-4o")
        return Agent(
            model=LiteLlm(model=model_name),
            name='reimbursement_agent',
            instruction="""
            You are an agent whose job is to handle the reimbursement process for
            the employees. If the amount is less than $100, you will automatically
            approve the reimbursement.

            If the amount is greater than $100, you will
            ask for approval from the manager. If the manager approves, you will
            call reimburse() to reimburse the amount to the employee. If the manager
            rejects, you will inform the employee of the rejection.
        """,
            tools=[reimburse, LongRunningFunctionTool(func=ask_for_approval)],
            generate_content_config=types.GenerateContentConfig(temperature=0.1),
        )

        # return LlmAgent(
        #     model=LiteLlm(model=model_name),
        #     name="shipping_agent",
        #     description="Handles shipping inquiries: rates, tracking, and shipment creation.",
        #     instruction=SHIPPING_INSTRUCTIONS,
        #     tools=[
        #         get_shipping_rates,
        #         track_shipment,
        #         create_shipment,
        #     ],
        # )

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
port = 8040



# --- Shipping Agent ---
shipping_skill = AgentSkill(
    id="HuamnInLoopShippingSkill",
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
    name="Human Agent",
    description="Specialised assistant for Human In the Loop.",
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