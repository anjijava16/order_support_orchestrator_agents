import json
import os
import sys

from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

host = "localhost"
port = "9090"


class TravelPlannerAgent:
    """travel planner Agent."""

    def __init__(self):
        """Initialize the travel dialogue model"""
        try:
            self.model = ChatOpenAI(
                model="gpt-4o",
                temperature=0.7,  # Control the generation randomness (0-2, higher values indicate greater randomness)
            )
        except FileNotFoundError:
            print("Error: The configuration file config.json cannot be found.")
            sys.exit()
        except KeyError as e:
            print(f"The configuration file is missing required fields: {e}")
            sys.exit()

    async def stream(self, query: str) -> AsyncGenerator[dict[str, Any], None]:
        """Stream the response of the large model back to the client."""
        try:
            # Initialize the conversation history (system messages can be added)
            messages = [
                SystemMessage(
                    content="""
                You are an expert travel assistant specializing in trip planning, destination information, 
                and travel recommendations. Your goal is to help users plan enjoyable, safe, and 
                realistic trips based on their preferences and constraints.
                
                When providing information:
                - Be specific and practical with your advice
                - Consider seasonality, budget constraints, and travel logistics
                - Highlight cultural experiences and authentic local activities
                - Include practical travel tips relevant to the destination
                - Format information clearly with headings and bullet points when appropriate
                
                For itineraries:
                - Create realistic day-by-day plans that account for travel time between attractions
                - Balance popular tourist sites with off-the-beaten-path experiences
                - Include approximate timing and practical logistics
                - Suggest meal options highlighting local cuisine
                - Consider weather, local events, and opening hours in your planning
                
                Always maintain a helpful, enthusiastic but realistic tone and acknowledge 
                any limitations in your knowledge when appropriate.
                """
                )
            ]

            # Add the user message to the history.
            messages.append(HumanMessage(content=query))

            # Invoke the model in streaming mode to generate a response.
            async for chunk in self.model.astream(messages):
                # Return the text content block.
                if hasattr(chunk, "content") and chunk.content:
                    yield {"content": chunk.content, "done": False}
            yield {"content": "", "done": True}

        except Exception as e:
            print(f"error：{e!s}")
            yield {
                "content": "Sorry, an error occurred while processing your request.",
                "done": True,
            }


from typing import override

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from a2a.utils import new_text_artifact


class TravelPlannerAgentExecutor(AgentExecutor):
    """travel planner AgentExecutor Example."""

    def __init__(self):
        self.agent = TravelPlannerAgent()

    @override
    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        query = context.get_user_input()
        if not context.message:
            raise Exception("No message provided")

        async for event in self.agent.stream(query):
            message = TaskArtifactUpdateEvent(
                context_id=context.context_id,  # type: ignore
                task_id=context.task_id,  # type: ignore
                artifact=new_text_artifact(
                    name="current_result",
                    text=event["content"],
                ),
            )
            await event_queue.enqueue_event(message)
            if event["done"]:
                break

        status = TaskStatusUpdateEvent(
            context_id=context.context_id,  # type: ignore
            task_id=context.task_id,  # type: ignore
            status=TaskStatus(state=TaskState.completed),
            final=True,
        )
        await event_queue.enqueue_event(status)

    @override
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise Exception("cancel not supported")


from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)


if __name__ == "__main__":
    skill = AgentSkill(
        id="travel_planner",
        name="travel planner agent",
        description="travel planner",
        tags=["travel planner"],
        examples=["hello", "nice to meet you!"],
    )

    agent_card = AgentCard(
        name="travel planner Agent",
        description="travel planner",
        url=f"http://{localhost}:{port}/",
        version="1.0.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],
    )

    request_handler = DefaultRequestHandler(
        agent_executor=TravelPlannerAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    server = A2AStarletteApplication(
        agent_card=agent_card, http_handler=request_handler
    )
    import uvicorn

    uvicorn.run(server.build(), host=host, port=port)
