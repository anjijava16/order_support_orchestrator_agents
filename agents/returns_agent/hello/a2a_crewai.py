import asyncio
import logging
import os
import re
from collections.abc import AsyncIterable
from typing import Any, Dict, List, Optional
from uuid import uuid4

from crewai import Agent, Crew, LLM, Task
from crewai.process import Process
from crewai.tools import tool
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()
logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# In-memory storage for returns (per session)
# ----------------------------------------------------------------------
_return_store: Dict[str, Dict[str, Any]] = {}  # session_id -> {return_id: return_data}


class ReturnData(BaseModel):
    """Represents a return request."""

    return_id: str
    order_id: str
    reason: str
    item_ids: Optional[List[str]] = None
    status: str  # e.g., "pending", "approved", "rejected", "completed"
    created_at: str
    updated_at: str


# ----------------------------------------------------------------------
# Tools (must be decorated with @tool)
# ----------------------------------------------------------------------


@tool("CreateReturn")
def create_return(
    order_id: str, reason: str, session_id: str, item_ids: Optional[List[str]] = None
) -> str:
    """
    Create a new return request for a given order.

    Args:
        order_id: The ID of the order to return.
        reason: The reason for the return.
        session_id: The current session/user identifier.
        item_ids: Optional list of specific item IDs to return (if not all).

    Returns:
        The return ID if successful, or an error message.
    """
    # In a real implementation you would call your order/returns API.
    # For demo, we simulate a new return.
    return_id = f"ret_{uuid4().hex[:8]}"
    from datetime import datetime

    now = datetime.now().isoformat()
    return_data = ReturnData(
        return_id=return_id,
        order_id=order_id,
        reason=reason,
        item_ids=item_ids,
        status="pending",
        created_at=now,
        updated_at=now,
    )
    # Store under the session
    if session_id not in _return_store:
        _return_store[session_id] = {}
    _return_store[session_id][return_id] = return_data.model_dump()
    return f"Return request created successfully. Return ID: {return_id}"


@tool("GetReturnStatus")
def get_return_status(return_id: str, session_id: str) -> str:
    """
    Retrieve the current status of a return request.

    Args:
        return_id: The ID of the return.
        session_id: The current session/user identifier.

    Returns:
        A string with the status and details, or an error message.
    """
    session_returns = _return_store.get(session_id, {})
    ret = session_returns.get(return_id)
    if ret:
        return (
            f"Return {return_id} status: {ret['status']} (created: {ret['created_at']})"
        )
    else:
        return f"Return ID {return_id} not found in your session."


@tool("ListReturns")
def list_returns(session_id: str) -> str:
    """
    List all return requests for the current session/user.

    Args:
        session_id: The current session/user identifier.

    Returns:
        A formatted list of returns, or a message if none exist.
    """
    session_returns = _return_store.get(session_id, {})
    if not session_returns:
        return "You have no return requests."
    lines = ["Your return requests:"]
    for rid, data in session_returns.items():
        lines.append(f"  - {rid}: {data['status']} (order {data['order_id']})")
    return "\n".join(lines)


@tool("CancelReturn")
def cancel_return(return_id: str, session_id: str) -> str:
    """
    Cancel a pending return request.

    Args:
        return_id: The ID of the return to cancel.
        session_id: The current session/user identifier.

    Returns:
        Confirmation or error message.
    """
    session_returns = _return_store.get(session_id, {})
    ret = session_returns.get(return_id)
    if not ret:
        return f"Return {return_id} not found."
    if ret["status"] != "pending":
        return f"Cannot cancel return with status '{ret['status']}'."
    ret["status"] = "cancelled"
    from datetime import datetime

    ret["updated_at"] = datetime.now().isoformat()
    return f"Return {return_id} has been cancelled."


# ----------------------------------------------------------------------
# Returns Agent (CrewAI)
# ----------------------------------------------------------------------


class ReturnsAgent:
    """Agent that handles return requests using CrewAI."""

    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self):
        # Configure LLM (adjust model as needed)
        # if os.getenv("GOOGLE_GENAI_USE_VERTEXAI"):
        #     self.model = LLM(model="vertex_ai/gemini-2.0-flash")
        # elif os.getenv("GOOGLE_API_KEY"):
        #     self.model = LLM(
        #         model="gemini/gemini-2.0-flash",
        #         api_key=os.getenv("GOOGLE_API_KEY"),
        #     )
        # else:
            # Fallback to OpenAI via LiteLLM if needed
        self.model = LLM(model="gpt-4o")  # or use environment variables

        self.returns_agent = Agent(
            role="Returns Specialist",
            goal=(
                "Help users with return requests: create returns, check status, "
                "list returns, and cancel returns. Use the available tools to "
                "perform these actions accurately."
            ),
            backstory=(
                "You are a customer service agent specialised in handling returns. "
                "You have access to tools that can create return requests, check their "
                "status, list all returns for a user, and cancel pending returns. "
                "Always verify that the user provides necessary information (order ID, reason). "
                "If information is missing, ask the user politely for the missing details."
            ),
            verbose=False,
            allow_delegation=False,
            tools=[create_return, get_return_status, list_returns, cancel_return],
            llm=self.model,
        )

        self.return_task = Task(
            description=(
                "The user has sent a query: '{user_query}'. "
                "The current session identifier is '{session_id}'. "
                "Analyse the query and determine what the user wants to do with returns. "
                "Use the appropriate tool(s) to fulfill the request. "
                "If the query contains a return ID or order ID, use it. If not, ask the user "
                "for the missing information (but within this single turn, do your best). "
                "After using tools, provide a clear and helpful response to the user."
            ),
            expected_output="A helpful response to the user about their return request.",
            agent=self.returns_agent,
        )

        self.crew = Crew(
            agents=[self.returns_agent],
            tasks=[self.return_task],
            process=Process.sequential,
            verbose=False,
        )

    def invoke(self, user_query: str, session_id: str) -> str:
        """Run the CrewAI crew and return the final response."""
        inputs = {
            "user_query": user_query,
            "session_id": session_id,
        }
        logger.info(f"Invoking ReturnsAgent with inputs: {inputs}")
        result = self.crew.kickoff(inputs)
        # CrewAI returns a string; if it's an object, convert
        return str(result)

    async def stream(
        self, query: str, context_id: str
    ) -> AsyncIterable[Dict[str, Any]]:
        """
        Stream the agent's response. Since CrewAI is synchronous, we run invoke
        in a thread and yield the final result.
        """
        # Optionally yield a "working" message
        yield {
            "is_task_complete": False,
            "require_user_input": False,
            "content": "Processing your return request...",
        }

        # Run invoke in a thread to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self.invoke, query, context_id)

        yield {
            "is_task_complete": True,
            "require_user_input": False,
            "content": result,
        }


# returns_executor.py
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


class ReturnsAgentExecutor(AgentExecutor):
    """A2A Executor for the Returns Agent."""

    def __init__(self):
        self.agent = ReturnsAgent()

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
                        name="returns_result",
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


# In your main server setup (after Order and Shipping agents)
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
port = 8072
# --- Returns Agent ---
returns_skill = AgentSkill(
    id="returns_management",
    name="Returns Management Tool",
    description="Handles return requests: create returns, check status, list returns, and cancel returns.",
    tags=["returns", "refunds"],
    examples=[
        "I want to return my order #12345",
        "What's the status of return ret_abc123?",
        "Show my returns",
        "Cancel return ret_abc123",
    ],
)
returns_capabilities = AgentCapabilities(streaming=True, push_notifications=False)
returns_agent_card = AgentCard(
    name="Returns Agent",
    description="Specialised assistant for handling order returns.",
    url=f"http://{host}:{port}/",
    version="1.0.0",
    default_input_modes=["text", "text/plain"],
    default_output_modes=["text", "text/plain"],
    capabilities=returns_capabilities,
    skills=[returns_skill],
)

# Create handler and app
returns_handler = DefaultRequestHandler(
    agent_executor=ReturnsAgentExecutor(),
    task_store=InMemoryTaskStore(),
)
returns_app = A2AStarletteApplication(
    agent_card=returns_agent_card, http_handler=returns_handler
).build()

import uvicorn
uvicorn.run(returns_app, host=host, port=port)
