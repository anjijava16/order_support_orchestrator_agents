from langchain_core.tools import tool
from datetime import datetime
import random

# Example tools
@tool
def current_time() -> str:
    """Returns the current time as a string."""
    return datetime.now().isoformat()

@tool
def random_number() -> str:
    """Returns a random number between 1 and 100."""
    return str(random.randint(1, 100))

@tool
def reverse_text(text: str) -> str:
    """Reverses the input text."""
    return text[::-1]

@tool
def check_order_status(order_id: str) -> str:
    """Simulates checking the status of an order."""
    return f"Order {order_id} is currently in transit."

@tool
def process_refund(order_id: str, amount: float) -> str:
    """Simulates processing a refund for an order."""
    return f"Refund of ${amount} for order {order_id} processed successfully."
