from google.adk.agents.llm_agent import Agent
from google.adk.agents.remote_a2a_agent import AGENT_CARD_WELL_KNOWN_PATH
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.genai import types
from google.adk.models.lite_llm import LiteLlm
import os


def reimburse(purpose: str, amount: float) -> str:
    """Reimburse the amount of money to the employee."""
    return {
        "status": "ok",
    }


approval_agent = RemoteA2aAgent(
    name="approval_agent",
    description="Help approve the reimburse if the amount is greater than 100.",
    agent_card=(f"http://localhost:8040{AGENT_CARD_WELL_KNOWN_PATH}"),
)

model_name = os.getenv("SHIPPING_MODEL", "gpt-4o")
model = LiteLlm(model=model_name)
root_agent = Agent(
    model=model,
    name="reimbursement_agent",
    instruction="""
      You are an agent whose job is to handle the reimbursement process for
      the employees. If the amount is less than $100, you will automatically
      approve the reimbursement. And call reimburse() to reimburse the amount to the employee.

      If the amount is greater than $100. You will hand over the request to
      approval_agent to handle the reimburse.
""",
    # tools=[reimburse],
    sub_agents=[approval_agent],
    generate_content_config=types.GenerateContentConfig(temperature=0.1),
)

import asyncio
import os

from google.genai import types
from google.adk.agents.llm_agent import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts.in_memory_artifact_service import (
    InMemoryArtifactService,
)  # Optional
from google.adk.planners import BasePlanner, BuiltInPlanner, PlanReActPlanner
from google.adk.models import LlmRequest

from google.genai.types import ThinkingConfig
from google.genai.types import GenerateContentConfig

import datetime
from zoneinfo import ZoneInfo

APP_NAME = "weather_app"
USER_ID = "1234"
SESSION_ID = "session1234"


async def call_agent(query) -> None:
    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=SESSION_ID
    )

    runner = Runner(
        agent=root_agent,
        app_name=APP_NAME,
        session_service=session_service
    )

    content = types.Content(role="user", parts=[types.Part(text=query)])

    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=SESSION_ID,
        new_message=content
    ):
        print(f"\nDEBUG EVENT: {event}\n")

        if event.is_final_response() and event.content:
            final_answer = event.content.parts[0].text.strip()
            print("\n🟢 FINAL ANSWER\n", final_answer, "\n")
# async def call_agent(query) -> None:
#     # Session and Runner
#     session_service = InMemorySessionService()
#     await session_service.create_session(
#         app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
#     )
#     runner = Runner(
#         agent=root_agent, app_name=APP_NAME, session_service=session_service
#     )
#     # Agent Interaction
#     content = types.Content(role="user", parts=[types.Part(text=query)])
#     events = await runner.run_async(user_id=USER_ID, session_id=SESSION_ID, new_message=content)
#     for event in events:
#         print(f"\nDEBUG EVENT: {event}\n")
#         if event.is_final_response() and event.content:
#             final_answer = event.content.parts[0].text.strip()
#             print("\n🟢 FINAL ANSWER\n", final_answer, "\n")


import asyncio

asyncio.run(call_agent("Please reimburse $200 for conference travel"))
