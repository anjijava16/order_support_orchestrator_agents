from langgraph.graph import StateGraph, START, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages.ai import AIMessage
from typing import Literal
from langchain_core.tools import tool
from pydantic import BaseModel
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, interrupt
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt import InjectedState
from langchain_core.messages.tool import ToolMessage
from collections.abc import Iterable
from random import randint

import os
#from dotenv import load_dotenv

#load_dotenv()
#GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

#llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", api_key = GOOGLE_API_KEY)
llm = ChatOpenAI()
class OrderState(TypedDict):
    """State representing the customer's order conversation."""

    messages: Annotated[list, add_messages]

    order: list[str]

    finished: bool

BARISTABOT_SYSINT = (
    "system", 
    "You are a BaristaBot, an interactive cafe ordering system. A human will talk to you about the "
    "available products you have and you will answer any questions about menu items (and only about "
    "menu items - no off-topic discussion, but you can chat about the products and their history). "
    "The customer will place an order for 1 or more items from the menu, which you will structure "
    "and send to the ordering system after confirming the order with the human. "
    "\n\n"
    "Add items to the customer's order with add_to_order, and reset the order with clear_order. "
    "To see the contents of the order so far, call get_order (this is shown to you, not the user) "
    "Always confirm_order with the user (double-check) before calling place_order. Calling confirm_order will "
    "display the order items to the user and returns their response to seeing the list. Their response may contain modifications. "
    "Always verify and respond with drink and modifier names from the MENU before adding them to the order. "
    "If you are unsure a drink or modifier matches those on the MENU, ask a question to clarify or redirect. "
    "You only have the modifiers listed on the menu. "
    "Once the customer has finished ordering items, Call confirm_order to ensure it is correct then make "
    "any necessary updates and then call place_order. Once place_order has returned, thank the user and "
    "say goodbye!",
)

WELCOME_MSG = "Welcome to the BaristaBot cafe. Type `q` to quit. How may I serve you today?"

def human_node(state: OrderState) -> OrderState:
    """Display the last model message to the user, and receive the user's input."""
    
    last_msg = state["messages"][-1]
    print("Model:", last_msg.content)

    user_input = interrupt("Give me your reply")
    print()
    print("user_input")
    print(user_input)
    print()

    if user_input in {"q", "quit", "exit", "goodbye"}:
        state["finished"] = True

    return state | {"messages": [("user", user_input)]}



def maybe_exit_human_node(state: OrderState) -> Literal["chatbot", "__end__"]:
    """Route to the chatbot, unless it looks like the user is exiting."""
    if state.get("finished", False):
        return END
    else:
        return "chatbot"
    

@tool
def get_menu() -> str:
    """Provide the latest up-to-date menu."""
    # Note that this is just hard-coded text, but you could connect this to a live stock
    # database, or you could use Gemini's multi-modal capabilities and take live photos of
    # your cafe's chalk menu or the products on the counter and assmble them into an input.

    return """
    MENU:
    Coffee Drinks:
    Espresso
    Americano
    Cold Brew

    Coffee Drinks with Milk:
    Latte
    Cappuccino
    Cortado
    Macchiato
    Mocha
    Flat White

    Tea Drinks:
    English Breakfast Tea
    Green Tea
    Earl Grey

    Tea Drinks with Milk:
    Chai Latte
    Matcha Latte
    London Fog

    Other Drinks:
    Steamer
    Hot Chocolate

    Modifiers:
    Milk options: Whole, 2%, Oat, Almond, 2% Lactose Free; Default option: whole
    Espresso shots: Single, Double, Triple, Quadruple; default: Double
    Caffeine: Decaf, Regular; default: Regular
    Hot-Iced: Hot, Iced; Default: Hot
    Sweeteners (option to add one or more): vanilla sweetener, hazelnut sweetener, caramel sauce, chocolate sauce, sugar free vanilla sweetener
    Special requests: any reasonable modification that does not involve items not on the menu, for example: 'extra hot', 'one pump', 'half caff', 'extra foam', etc.

    "dirty" means add a shot of espresso to a drink that doesn't usually have it, like "Dirty Chai Latte".
    "Regular milk" is the same as 'whole milk'.
    "Sweetened" means add some regular sugar, not a sweetener.

    Soy milk has run out of stock today, so soy is not available.
  """

@tool
def add_to_order(drink: str, modifiers: Iterable[str]) -> str:
    """Adds the specified drink to the customer's order, including any modifiers.

    Returns:
      The updated order in progress.
    """


@tool
def confirm_order() -> str:
    """Asks the customer if the order is correct.

    Returns:
      The user's free-text response.
    """


@tool
def get_order() -> str:
    """Returns the users order so far. One item per line."""


@tool
def clear_order():
    """Removes all items from the user's order."""


@tool
def place_order() -> int:
    """Sends the order to the barista for fulfillment.

    Returns:
      The estimated number of minutes until the order is ready.
    """


def order_node(state: OrderState) -> OrderState:
    """The ordering node. This is where the order state is manipulated."""
    tool_msg = state.get("messages", [])[-1]
    order = state.get("order", [])
    outbound_msgs = []
    order_placed = False

    for tool_call in tool_msg.tool_calls:

        if tool_call["name"] == "add_to_order":

            modifiers = tool_call["args"]["modifiers"]
            modifier_str = ", ".join(modifiers) if modifiers else "no modifiers"

            order.append(f'{tool_call["args"]["drink"]} ({modifier_str})')
            response = "\n".join(order)

        elif tool_call["name"] == "confirm_order":

            print("Your order:")
            if not order:
                print("  (no items)")

            for drink in order:
                print(f"  {drink}")

            # response = input("Is this correct? ")
            response = "yes"

        elif tool_call["name"] == "get_order":

            response = "\n".join(order) if order else "(no order)"

        elif tool_call["name"] == "clear_order":

            order.clear()
            response = None

        elif tool_call["name"] == "place_order":

            order_text = "\n".join(order)
            print("Sending order to kitchen!")
            print(order_text)

            # TODO(you!): Implement cafe.
            order_placed = True
            response = randint(1, 5)  # ETA in minutes

        else:
            raise NotImplementedError(f'Unknown tool call: {tool_call["name"]}')

        # Record the tool results as tool messages.
        outbound_msgs.append(
            ToolMessage(
                content=response,
                name=tool_call["name"],
                tool_call_id=tool_call["id"],
            )
        )

    return {"messages": outbound_msgs, "order": order, "finished": order_placed}


def maybe_route_to_tools(state: OrderState) -> str:
    """Route between chat and tool nodes if a tool call is made."""
    if not (msgs := state.get("messages", [])):
        raise ValueError(f"No messages found when parsing state: {state}")

    msg = msgs[-1]

    if state.get("finished", False):
        # When an order is placed, exit the app. The system instruction indicates
        # that the chatbot should say thanks and goodbye at this point, so we can exit
        # cleanly.
        return END

    elif hasattr(msg, "tool_calls") and len(msg.tool_calls) > 0:
        # Route to `tools` node for any automated tool calls first.
        if any(
            tool["name"] in tool_node.tools_by_name.keys() for tool in msg.tool_calls
        ):
            return "tools"
        else:
            return "ordering"

    else:
        return "human"



auto_tools = [get_menu]
tool_node = ToolNode(auto_tools)

order_tools = [add_to_order, confirm_order, get_order, clear_order, place_order]

llm_with_tools = llm.bind_tools(auto_tools + order_tools)

def chatbot_with_tools(state: OrderState) -> OrderState:
    """The chatbot with tools. A simple wrapper around the model's own chat interface."""
    # defaults = {"order": [], "finished": False}

    if state["messages"]:
        new_output = llm_with_tools.invoke([BARISTABOT_SYSINT] + state["messages"])
        print("new output")
        print(new_output)
        print("*****************************************")
    else:
        new_output = AIMessage(content=WELCOME_MSG)

    # return defaults | state | {"messages": [new_output]}
    return {"messages": [new_output]}

def invoke(state: OrderState | Command, config: dict | None = None) -> OrderState:
    graph_builder = StateGraph(OrderState)

    graph_builder.add_node("chatbot", chatbot_with_tools)
    graph_builder.add_node("human", human_node)
    graph_builder.add_node("tools", tool_node)
    graph_builder.add_node("ordering", order_node)

    # Chatbot -> {ordering, tools, human, END}
    graph_builder.add_conditional_edges("chatbot", maybe_route_to_tools)
    # Human -> {chatbot, END}
    graph_builder.add_conditional_edges("human", maybe_exit_human_node)

    # Tools (both kinds) always route back to chat afterwards.
    graph_builder.add_edge("tools", "chatbot")
    graph_builder.add_edge("ordering", "chatbot")

    graph_builder.add_edge(START, "chatbot")

    checkpointer = MemorySaver()


    graph_with_menu = graph_builder.compile(
        checkpointer=checkpointer 
    )







from fastapi import FastAPI

from langgraph.types import Command
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.get("/")
def read_root():
    return {"message": "Welcome to your FastAPI backend!"}

@app.get("/chat_initiate")
def read_item(thread_id: str, response: str = None):
    thread_config = {"configurable": {"thread_id": thread_id}}    
    state = invoke(
        {"messages": [],
         "order": [],
         "finished": False}, 
        config=thread_config)

    return {
        "AIMessage": state["messages"][-1].content,
        "state": state
    }

@app.get("/chat-continue")
def continue_chat(thread_id: str, response: str):
    thread_config = {"configurable": {"thread_id": thread_id}}
    state = invoke(
        Command(resume = response), 
        config=thread_config)

    return {
        "AIMessage": state["messages"][-1].content,
        "state": state,
        "thread_id": thread_id
    }