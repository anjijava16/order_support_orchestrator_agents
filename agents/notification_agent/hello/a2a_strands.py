import logging
from datetime import datetime
from typing import List, Optional

# strands‑agents imports
from strands import Agent
from strands.multiagent.a2a import A2AServer
# (If your strands installation uses a different path, adjust accordingly.)

# Optional A2A types – for explicit card definition (not required by A2AServer)
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

# ----------------------------------------------------------------------
# Notification Tools (plain functions with docstrings)
# ----------------------------------------------------------------------

# In‑memory storage for notifications (per user/session)
_notification_store = {}  # user_id -> list of notifications


def send_notification(user_id: str, message: str, priority: str = "normal") -> str:
    """
    Send a notification to a user.

    Args:
        user_id: Identifier of the recipient.
        message: The notification text.
        priority: Priority level – "low", "normal", or "high".

    Returns:
        Confirmation message with notification ID.
    """
    from uuid import uuid4
    notification = {
        "id": uuid4().hex,
        "user_id": user_id,
        "message": message,
        "priority": priority,
        "timestamp": datetime.now().isoformat(),
        "read": False,
    }
    if user_id not in _notification_store:
        _notification_store[user_id] = []
    _notification_store[user_id].append(notification)
    return f"Notification sent to {user_id} (ID: {notification['id']})"


def list_notifications(user_id: str, include_read: bool = False) -> str:
    """
    List all notifications for a user.

    Args:
        user_id: Identifier of the user.
        include_read: If True, include already read notifications.

    Returns:
        A formatted string listing notifications.
    """
    notifs = _notification_store.get(user_id, [])
    if not include_read:
        notifs = [n for n in notifs if not n["read"]]
    if not notifs:
        return f"No notifications for user {user_id}."
    lines = [f"Notifications for {user_id}:"]
    for n in notifs:
        status = "✓" if n["read"] else "●"
        lines.append(f"  {status} [{n['priority']}] {n['timestamp'][:19]}: {n['message']} (ID: {n['id']})")
    return "\n".join(lines)


def mark_notification_read(user_id: str, notification_id: str) -> str:
    """
    Mark a specific notification as read.

    Args:
        user_id: Identifier of the user.
        notification_id: ID of the notification to mark.

    Returns:
        Confirmation message.
    """
    notifs = _notification_store.get(user_id, [])
    for n in notifs:
        if n["id"] == notification_id:
            n["read"] = True
            return f"Notification {notification_id} marked as read."
    return f"Notification {notification_id} not found for user {user_id}."


# ----------------------------------------------------------------------
# Create the strands Agent
# ----------------------------------------------------------------------

notification_agent = Agent(
    name="Notification Agent",
    description="Handles sending, listing, and managing notifications for users.",
    tools=[send_notification, list_notifications, mark_notification_read],
    callback_handler=None,  # optional
)

# ----------------------------------------------------------------------
# (Optional) Explicit AgentCard for documentation / multi‑agent setups
# ----------------------------------------------------------------------

# Define a skill
notification_skill = AgentSkill(
    id="notification_management",
    name="Notification Management",
    description="Send, list, and mark notifications as read.",
    tags=["notifications", "alerts"],
    examples=[
        "Send a notification to user123 saying 'Your order has shipped'",
        "Show me my notifications",
        "Mark notification abc123 as read",
    ],
)

# Define capabilities (streaming is supported by strands' A2AServer)
capabilities = AgentCapabilities(streaming=True, push_notifications=False)

# Build the agent card
agent_card = AgentCard(
    name="Notification Agent",
    description="Specialised assistant for managing user notifications.",
    url="http://localhost:8072/",  # adjust host/port as needed
    version="1.0.0",
    default_input_modes=["text", "text/plain"],
    default_output_modes=["text", "text/plain"],
    capabilities=capabilities,
    skills=[notification_skill],
)

# ----------------------------------------------------------------------
# Start the A2A server (strands' built‑in server)
# ----------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Create the A2A server, passing the strands agent.
    # The server automatically generates an agent card from the agent's metadata
    # and exposes the A2A endpoints (including /.well-known/agent-card.json).
    a2a_server = A2AServer(
        agent=notification_agent,
        # You can override the host/port if needed:
        host="localhost",
        port=8073,
    )

    # Start the server (by default on localhost:8000, but you can change it)
    # The serve() method runs Uvicorn internally.
    a2a_server.serve()