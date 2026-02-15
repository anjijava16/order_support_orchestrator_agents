import os
from collections.abc import AsyncIterable
from typing import Any, Literal

import httpx

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel


memory = MemorySaver()


# ----------------------------------------------------------------------
# Order‑related tools (stubs – replace with real API calls as needed)
# ----------------------------------------------------------------------

@tool
def create_order(item: str, quantity: int = 1, user_id: str = "guest"):
    """Create a new order for the given item and quantity.

    Args:
        item: Name of the item to order (e.g., "pizza", "laptop").
        quantity: Number of items to order. Defaults to 1.
        user_id: Identifier for the user placing the order. Defaults to "guest".

    Returns:
        A dictionary containing the order details (including an order ID) or an error.
    """
    # In a real implementation you would call your order service here.
    try:
        # Simulate API call
        response = httpx.post(
            "https://api.example.com/orders",
            json={"item": item, "quantity": quantity, "user_id": user_id},
        )
        response.raise_for_status()
        data = response.json()
        return data
    except httpx.HTTPError as e:
        return {"error": f"Order creation failed: {e}"}
    except Exception as e:
        return {"error": f"Unexpected error: {e}"}


@tool
def get_order_status(order_id: str):
    """Retrieve the current status of an order.

    Args:
        order_id: The unique identifier of the order.

    Returns:
        A dictionary with order status information or an error.
    """
    try:
        response = httpx.get(f"https://api.example.com/orders/{order_id}")
        response.raise_for_status()
        data = response.json()
        return data
    except httpx.HTTPError as e:
        return {"error": f"Failed to get order status: {e}"}
    except Exception as e:
        return {"error": f"Unexpected error: {e}"}


@tool
def cancel_order(order_id: str):
    """Cancel an existing order.

    Args:
        order_id: The unique identifier of the order to cancel.

    Returns:
        A confirmation message or error.
    """
    try:
        response = httpx.delete(f"https://api.example.com/orders/{order_id}")
        response.raise_for_status()
        return {"message": f"Order {order_id} cancelled successfully."}
    except httpx.HTTPError as e:
        return {"error": f"Cancellation failed: {e}"}
    except Exception as e:
        return {"error": f"Unexpected error: {e}"}


@tool
def list_orders(user_id: str = "guest"):
    """List all orders placed by a specific user.

    Args:
        user_id: Identifier for the user. Defaults to "guest".

    Returns:
        A list of orders or an error.
    """
    try:
        response = httpx.get("https://api.example.com/orders", params={"user_id": user_id})
        response.raise_for_status()
        data = response.json()
        return data
    except httpx.HTTPError as e:
        return {"error": f"Failed to list orders: {e}"}
    except Exception as e:
        return {"error": f"Unexpected error: {e}"}


# ----------------------------------------------------------------------
# Response format (identical to the original, can be reused)
# ----------------------------------------------------------------------

class OrderResponseFormat(BaseModel):
    """Respond to the user in this format."""

    status: Literal['input_required', 'completed', 'error'] = 'input_required'
    message: str


# ----------------------------------------------------------------------
# Order Agent – specialised assistant for order management
# ----------------------------------------------------------------------

class OrderAgent:
    """OrderAgent - a specialised assistant for handling customer orders."""

    SYSTEM_INSTRUCTION = (
        "You are a specialised assistant for order management. "
        "Your sole purpose is to help users with tasks such as creating orders, "
        "checking order status, cancelling orders, and listing their orders. "
        "Use the available tools (create_order, get_order_status, cancel_order, list_orders) "
        "to answer queries. "
        "If the user asks about anything unrelated to orders, politely state that you cannot "
        "help with that topic and can only assist with order‑related questions. "
        "Do not attempt to answer unrelated questions or use tools for other purposes."
    )

    FORMAT_INSTRUCTION = (
        "Set response status to input_required if the user needs to provide more information to complete the request. "
        "Set response status to error if there is an error while processing the request. "
        "Set response status to completed if the request is complete."
    )

    def __init__(self):
        model_source = os.getenv('model_source', 'google')
        # if model_source == 'google':
        #     self.model = ChatGoogleGenerativeAI(model='gemini-2.0-flash')
        # else:
        self.model = ChatOpenAI(
            model='gpt-4o',
            temperature=0,
        )
        self.tools = [create_order, get_order_status, cancel_order, list_orders]

        self.graph = create_react_agent(
            self.model,
            tools=self.tools,
            checkpointer=memory,
            prompt=self.SYSTEM_INSTRUCTION,
            response_format=(self.FORMAT_INSTRUCTION, OrderResponseFormat),
        )

    async def stream(self, query: str, context_id: str) -> AsyncIterable[dict[str, Any]]:
        inputs = {'messages': [('user', query)]}
        config = {'configurable': {'thread_id': context_id}}

        for item in self.graph.stream(inputs, config, stream_mode='values'):
            message = item['messages'][-1]
            if (
                isinstance(message, AIMessage)
                and message.tool_calls
                and len(message.tool_calls) > 0
            ):
                yield {
                    'is_task_complete': False,
                    'require_user_input': False,
                    'content': 'Processing your order request...',
                }
            elif isinstance(message, ToolMessage):
                yield {
                    'is_task_complete': False,
                    'require_user_input': False,
                    'content': 'Handling your order...',
                }

        yield self.get_agent_response(config)

    def get_agent_response(self, config):
        current_state = self.graph.get_state(config)
        structured_response = current_state.values.get('structured_response')
        if structured_response and isinstance(
            structured_response, OrderResponseFormat
        ):
            if structured_response.status == 'input_required':
                return {
                    'is_task_complete': False,
                    'require_user_input': True,
                    'content': structured_response.message,
                }
            if structured_response.status == 'error':
                return {
                    'is_task_complete': False,
                    'require_user_input': True,
                    'content': structured_response.message,
                }
            if structured_response.status == 'completed':
                return {
                    'is_task_complete': True,
                    'require_user_input': False,
                    'content': structured_response.message,
                }

        return {
            'is_task_complete': False,
            'require_user_input': True,
            'content': (
                'We are unable to process your request at the moment. '
                'Please try again.'
            ),
        }

    SUPPORTED_CONTENT_TYPES = ['text', 'text/plain']


# ----------------------------------------------------------------------
# A2A Server Executor for the Order Agent
# ----------------------------------------------------------------------

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
from a2a.utils import (
    new_agent_text_message,
    new_task,
)
from a2a.utils.errors import ServerError

# from app.agent import OrderAgent   # if the agent is defined elsewhere

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OrderAgentExecutor(AgentExecutor):
    """Order Agent Executor for A2A server."""

    def __init__(self):
        self.agent = OrderAgent()

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
            task = new_task(context.message)  # type: ignore
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        try:
            async for item in self.agent.stream(query, task.context_id):
                is_task_complete = item['is_task_complete']
                require_user_input = item['require_user_input']

                if not is_task_complete and not require_user_input:
                    await updater.update_status(
                        TaskState.working,
                        new_agent_text_message(
                            item['content'],
                            task.context_id,
                            task.id,
                        ),
                    )
                elif require_user_input:
                    await updater.update_status(
                        TaskState.input_required,
                        new_agent_text_message(
                            item['content'],
                            task.context_id,
                            task.id,
                        ),
                        final=True,
                    )
                    break
                else:
                    await updater.add_artifact(
                        [Part(root=TextPart(text=item['content']))],
                        name='order_result',
                    )
                    await updater.complete()
                    break

        except Exception as e:
            logger.error(f'An error occurred while streaming the response: {e}')
            raise ServerError(error=InternalError()) from e

    def _validate_request(self, context: RequestContext) -> bool:
        # Add any request validation logic here (e.g., check required fields)
        return False

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        raise ServerError(error=UnsupportedOperationError())
    
class MissingAPIKeyError(Exception):
    """Exception for missing API key."""
import logging
import os
import sys

import click
import httpx
import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import (
    BasePushNotificationSender,
    InMemoryPushNotificationConfigStore,
    InMemoryTaskStore,
)
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
def main():
    """Starts the Currency Agent server."""
    try:
        host="localhost"
        port=8070
        capabilities = AgentCapabilities(streaming=True, push_notifications=True)
        # Define the skill that the OrderAgent provides
        skill = AgentSkill(
            id="order_management",
            name="Order Management Tool",
            description=(
                "Helps customers create new orders, check order status, "
                "cancel existing orders, and list their past orders."
            ),
            tags=["order management", "e-commerce", "shopping"],
            examples=[
                "I'd like to order a pizza",
                "What's the status of my order #12345?",
                "Cancel my order #67890",
                "Show me all my orders",
            ],
        )

        # Define agent capabilities (customise as needed)
        capabilities = AgentCapabilities(
            streaming=True,          # supports streaming responses
            push_notifications=False  # no push notifications (optional)
        )

        # Build the agent card (used to advertise the agent to A2A clients)
        agent_card = AgentCard(
            name="Order Agent",
            description="Specialised assistant for handling customer orders and inquiries.",
            url=f"http://{host}:{port}/",   # host and port must be defined in your server
            version="1.0.0",
            default_input_modes=OrderAgent.SUPPORTED_CONTENT_TYPES,
            default_output_modes=OrderAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
        )


        # --8<-- [start:DefaultRequestHandler]
        httpx_client = httpx.AsyncClient()
        push_config_store = InMemoryPushNotificationConfigStore()
        push_sender = BasePushNotificationSender(httpx_client=httpx_client,
                        config_store=push_config_store)
        request_handler = DefaultRequestHandler(
            agent_executor=OrderAgentExecutor(),
            task_store=InMemoryTaskStore(),
            push_config_store=push_config_store,
            push_sender= push_sender
        )
        server = A2AStarletteApplication(
            agent_card=agent_card, http_handler=request_handler
        )
        # .build()
        # from starlette.applications import Starlette
        # from starlette.routing import Mount
        # prefix = "/order"  # change this to your desired prefix
        # app = Starlette(routes=[
        #     Mount(prefix, app=server),
        # ])
        # agent_card.url = f"http://{host}:{port}{prefix}/"  # update agent card URL with prefix

        uvicorn.run(server.build(), host=host, port=port)
        # --8<-- [end:DefaultRequestHandler]

    except MissingAPIKeyError as e:
        logger.error(f'Error: {e}')
        sys.exit(1)
    except Exception as e:
        logger.error(f'An error occurred during server startup: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()