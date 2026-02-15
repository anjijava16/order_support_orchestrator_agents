import asyncio
import logging
from typing import Any, Dict, List, Optional

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage
from autogen_agentchat.ui import Console
from autogen_core import CancellationToken
from autogen_ext.models.openai import OpenAIChatCompletionClient

# Optional: for structured output
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Response Format (optional but useful for structured replies)
# ----------------------------------------------------------------------
class DeliveryResponse(BaseModel):
    status: str  # "completed", "input_required", "error"
    message: str
    order_id: Optional[str] = None
    tracking_number: Optional[str] = None

# ----------------------------------------------------------------------
# Delivery Tools (async functions decorated as tools)
# ----------------------------------------------------------------------
async def get_delivery_status(order_id: str) -> str:
    """
    Get the current delivery status of an order.

    Args:
        order_id: The unique order identifier (e.g., ORD-12345).

    Returns:
        A string describing the delivery status.
    """
    # TODO: Replace with real API call
    await asyncio.sleep(0.5)  # simulate network delay
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
# Main Agent Definition
# ----------------------------------------------------------------------
async def run_delivery_agent() -> None:
    """Create and run a delivery assistant agent."""
    
    # Create the model client (using OpenAI-compatible endpoint)
    model_client = OpenAIChatCompletionClient(
        model="gpt-4o",  # or your preferred model
        #api_key="your-api-key",  # or use env variable        base_url="https://api.openai.com/v1",  # or OpenRouter etc.
    )

    # Define the delivery assistant agent with tools
    delivery_agent = AssistantAgent(
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
        # Optional: enable reflection for better tool usage
        reflect_on_tool_use=True,
    )

    # Example interaction 1: Check delivery status
    print("\n" + "="*50)
    print("User: What's the status of order ORD-12345?")
    print("="*50)
    
    result = await delivery_agent.run(
        task="What's the status of order ORD-12345?",
        cancellation_token=CancellationToken(),
    )
    
    print(f"Assistant: {result.messages[-1].content}\n")
    
    # Example interaction 2: Track a package
    print("="*50)
    print("User: Track package 1Z999AA10123456784")
    print("="*50)
    
    result = await delivery_agent.run(
        task="Track package 1Z999AA10123456784",
        cancellation_token=CancellationToken(),
    )
    
    print(f"Assistant: {result.messages[-1].content}\n")
    
    # Example interaction 3: Reschedule delivery
    print("="*50)
    print("User: I need to reschedule my order ORD-12345 to tomorrow between 2-4pm")
    print("="*50)
    
    result = await delivery_agent.run(
        task="I need to reschedule my order ORD-12345 to tomorrow between 2-4pm",
        cancellation_token=CancellationToken(),
    )
    
    print(f"Assistant: {result.messages[-1].content}\n")
    
    # Example interaction 4: Report issue
    print("="*50)
    print("User: My package for order ORD-67890 hasn't arrived. It's missing.")
    print("="*50)
    
    result = await delivery_agent.run(
        task="My package for order ORD-67890 hasn't arrived. It's missing.",
        cancellation_token=CancellationToken(),
    )
    
    print(f"Assistant: {result.messages[-1].content}\n")

# ----------------------------------------------------------------------
# For streaming responses (if you need incremental updates)
# ----------------------------------------------------------------------
async def run_delivery_agent_streaming() -> None:
    """Example of streaming the agent's response."""
    
    model_client = OpenAIChatCompletionClient(model="gpt-4o")
    
    delivery_agent = AssistantAgent(
        name="delivery_assistant",
        model_client=model_client,
        tools=[
            get_delivery_status,
            track_package,
            reschedule_delivery,
            report_delivery_issue,
        ],
        system_message="You are a helpful delivery assistant.",
    )

    # Run with streaming to see messages as they arrive
    print("\nStreaming response:")
    print("-" * 30)
    
    async for message in delivery_agent.run_stream(
        task="What's the status of order ORD-12345?",
        cancellation_token=CancellationToken(),
    ):
        if isinstance(message, TextMessage):
            print(f"[{message.source}]: {message.content}")
    
    print("-" * 30)

# ----------------------------------------------------------------------
# Run the examples
# ----------------------------------------------------------------------
async def main() -> None:
    """Run the delivery agent examples."""
    
    print("\n" + "🚚 DELIVERY AGENT DEMO (AutoGen 0.7.x)".center(60, "="))
    
    # Run basic examples
    from delivery_agent_simple import DeliveryAgent
    #await run_delivery_agent()
    ds= DeliveryAgent()
    async for chunk in ds.stream("What's the status...", 'session_id'):
        print(chunk["content"])
    
    # Uncomment to see streaming version
    # await run_delivery_agent_streaming()

if __name__ == "__main__":
    asyncio.run(main())


# from autogen_core import CancellationToken

# class DeliveryAgentExecutor(AgentExecutor):
#     def __init__(self):
#         self.model_client = OpenAIChatCompletionClient(
#             model="gpt-4o",
#             api_key=os.getenv("OPENROUTER_API_KEY"),
#             base_url="https://openrouter.ai/api/v1",
#         )
#         self.agent = AssistantAgent(
#             name="delivery_assistant",
#             model_client=self.model_client,
#             tools=[get_delivery_status, track_package, reschedule_delivery, report_delivery_issue],
#             system_message="You are a helpful delivery assistant.",
#         )
    
#     async def stream(self, query: str, session_id: str):
#         """Yields status messages and final response."""
#         yield {
#             "is_task_complete": False,
#             "require_user_input": False,
#             "content": "Processing your delivery request...",
#         }
        
#         result = await self.agent.run(
#             task=query,
#             cancellation_token=CancellationToken(),
#         )
        
#         final_message = result.messages[-1].content
#         yield {
#             "is_task_complete": True,
#             "require_user_input": False,
#             "content": final_message,
#         }