
def init():
    import os
    import subprocess

    command = "source ~/.zprofile && env"
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        shell=True,
        executable="/bin/zsh"
    )

    for line in proc.stdout:
        key, _, value = line.decode().partition("=")
        os.environ[key] = value.strip()

def llm_factory():
    init()
    from langchain_community.chat_models import ChatLiteLLM

    # Primary model with fallback regions
    primary_model = ChatLiteLLM(
        model="bedrock/anthropic.claude-3-sonnet-20240229-v1:0",
        temperature=0.2,
    )

    # Fallback models for different regions
    fallback_models = [
        ChatLiteLLM(
            model="bedrock/anthropic.claude-3-sonnet-20240229-v1:0",
            temperature=0.2,
            aws_region_name="us-west-2",  # Fallback region 1
        ),
        ChatLiteLLM(
            model="bedrock/anthropic.claude-3-sonnet-20240229-v1:0",
            temperature=0.2,
            aws_region_name="eu-west-1",  # Fallback region 2
        ),
    ]

    # Create LLM with fallback chain
    llm = primary_model.with_fallbacks(fallback_models)
    return llm


llm=llm_factory()
