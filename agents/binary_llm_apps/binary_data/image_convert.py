import base64
import mimetypes
from pathlib import Path


def process_local_file(file_path: str) -> dict:
    """
    Process a local file and return it in the format required for Google Generative AI.

    Args:
        file_path (str): Path to the local file

    Returns:
        dict: A dictionary containing:
            - type: The content type ('image', 'video', 'audio', or 'file')
            - base64: Base64 encoded file content
            - mime_type: MIME type of the file

    Raises:
        FileNotFoundError: If the file doesn't exist
        ValueError: If the MIME type cannot be determined
    """
    # Verify file exists
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Determine MIME type
    mime_type = mimetypes.guess_type(file_path)[0]
    if mime_type is None:
        raise ValueError(f"Could not determine MIME type for: {file_path}")

    # Read and encode file
    with open(file_path, "rb") as file:
        file_bytes = file.read()
        file_base64 = base64.b64encode(file_bytes).decode("utf-8")

    # Determine content type based on MIME type
    if mime_type.startswith("image/"):
        content_type = "image"
    elif mime_type.startswith("video/"):
        content_type = "video"
    elif mime_type.startswith("audio/"):
        content_type = "audio"
    else:
        # Default to "file" for PDFs and other documents
        content_type = "file"

    return {
        "type": content_type,
        "base64": file_base64,
        "mime_type": mime_type
    }

response = process_local_file("agents.png")
print(response)


from langgraph.types import interrupt
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
import os

# llm = ChatOpenAI(model="gpt-4o", temperature=0)
from langchain_community.chat_models import ChatLiteLLM

    # Primary model with fallback regions
llm = ChatLiteLLM(
    model="bedrock/anthropic.claude-3-sonnet-20240229-v1:0",
    temperature=0.2,
)



# response = llm.invoke("Explain how Generative AI works in 1 line")
# print(response)

# # Create message with the processed file
# message = HumanMessage(
#     content=[
#         {"type": "text", "text": "What's in this image?"},
#         response  # Insert the processed file directly
#     ]
# )

# # Get response
# response = llm.invoke([message])

# print(response)


message = {
    "type": "input_image",
    "image_data": response['base64'],
    "mime_type": response['mime_type'],
    "caption": "What's in this image?"
}

from langchain_core.messages import HumanMessage

# Convert image to markdown text
image_text = f"![image](data:{response['mime_type']};base64,{response['base64']})"

message = HumanMessage(
    content=f"What's in this image?\n{image_text}"
)

response_text = llm.invoke([message])
print(response_text)