from typing import Optional

from pydantic import BaseModel


class OrderState(BaseModel):
    # Customer info
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    shipping_address: Optional[str] = None

    # Order content
    items: list[dict[str, any]] = []  # e.g., [{"sku": "123", "qty": 2, "price": 10.0}]
    total_amount: Optional[float] = None

    # Process status
    validation_status: Optional[str] = None  # "pending", "valid", "invalid"
    inventory_check: Optional[str] = None
    payment_status: Optional[str] = None  # "pending", "authorized", "failed"
    order_confirmed: bool = False
    error_messages: list[str] = []

    # Conversation / context
    messages: list[dict[str, str]] = []  # for chat history
    current_step: str = "start"
