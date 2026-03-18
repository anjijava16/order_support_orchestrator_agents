import asyncio
from typing import Sequence, Mapping
from opensearchpy import AsyncOpenSearch

# Google ADK imports
from google.adk.memory import BaseMemoryService, SearchMemoryResponse, MemoryEntry
from google.adk.sessions import Session, Event
from google.adk.agents import LlmAgent
from google.adk.runner import Runner

class OpenSearchMemoryService(BaseMemoryService):
    """Custom ADK Memory Service backed by OpenSearch."""
    
    def __init__(self, host: str, port: int, index_name: str):
        # Initialize async OpenSearch client
        self.client = AsyncOpenSearch(
            hosts=[{'host': host, 'port': port}],
            use_ssl=False,     # Set to True for production environments
            verify_certs=False # Set to True for production environments
        )
        self.index_name = index_name

    async def _ensure_index(self):
        """Helper to create the index if it doesn't exist."""
        exists = await self.client.indices.exists(index=self.index_name)
        if not exists:
            # Note: In a production app, you would define your k-NN vector mappings here
            await self.client.indices.create(index=self.index_name)

    async def add_session_to_memory(self, session: Session) -> None:
        """Required Method 1: Ingests a completed session into OpenSearch."""
        await self._ensure_index()
        
        # Combine the events into a single memory block. 
        # (Tip: You could use a summarization prompt here to extract key facts first)
        conversation_text = "\n".join([f"{e.role}: {e.text}" for e in session.events if e.text])
        
        doc = {
            "session_id": session.id,
            "user_id": session.user_id,
            "content": conversation_text
        }
        
        await self.client.index(
            index=self.index_name,
            body=doc,
            refresh=True # Forces a refresh so it's searchable immediately
        )

    async def add_events_to_memory(
        self, 
        *, 
        app_name: str, 
        user_id: str, 
        events: Sequence[Event], 
        session_id: str | None = None, 
        custom_metadata: Mapping[str, object] | None = None
    ) -> None:
        """Required Method 2: Appends an explicit list of event deltas to memory."""
        await self._ensure_index()
        
        delta_text = "\n".join([f"{e.role}: {e.text}" for e in events if e.text])
        doc = {
            "session_id": session_id or "unknown",
            "user_id": user_id,
            "app_name": app_name,
            "content": delta_text,
            "metadata": custom_metadata or {}
        }
        
        await self.client.index(index=self.index_name, body=doc, refresh=True)

    async def search_memory(self, *, app_name: str, user_id: str, query: str) -> SearchMemoryResponse:
        """Required Method 3: Searches OpenSearch for relevant past context."""
        await self._ensure_index()
        
        # Using a basic BM25 Lexical search for this example.
        # To make this smarter, replace this with a k-NN vector search!
        search_body = {
            "query": {
                "bool": {
                    "must": [{"match": {"content": query}}],
                    "filter": [{"term": {"user_id": user_id}}] # Ensure users only search their own data
                }
            },
            "size": 3
        }
        
        response = await self.client.search(index=self.index_name, body=search_body)
        
        # Convert OpenSearch hits back into ADK MemoryEntry objects
        memories = []
        for hit in response["hits"]["hits"]:
            text_content = hit["_source"]["content"]
            # ADK expects memory records wrapped in the MemoryEntry class
            memories.append(MemoryEntry(content=text_content))
            
        return SearchMemoryResponse(memories=memories)


# --- Application Execution ---

async def main():
    print("Initializing OpenSearch memory service...")
    # 1. Instantiate your custom memory service
    memory_service = OpenSearchMemoryService(
        host="localhost", 
        port=9200, 
        index_name="adk_agent_memories"
    )

    # 2. Define the ADK Agent
    agent = LlmAgent(
        model="gemini-2.5-flash", # Feel free to swap models
        name="MemoryBot",
        instruction="You are a highly capable assistant with perfect memory. Always refer to past context if available."
    )

    # 3. Create the Runner and attach the custom memory
    runner = Runner(
        agent=agent,
        memory_service=memory_service
    )

    # 4. Create a session for the user
    user_id = "user_123"
    session = await runner.async_create_session(user_id=user_id)
    
    print("\nAgent is ready! (Type 'quit' to exit)")
    print("-" * 40)
    
    while True:
        user_input = input("You: ")
        if user_input.lower() in ['quit', 'exit']:
            break

        print("Agent: ", end="")
        
        # Stream the query. Under the hood, if the agent uses a memory tool, 
        # it will hit your OpenSearch cluster automatically.
        async for event in runner.async_stream_query(
            user_id=user_id,
            session_id=session.id,
            message=user_input
        ):
            print(event.text, end="")
        print("\n")
        
    # 5. Save the session to OpenSearch on exit
    print("\nSaving session history to OpenSearch...")
    await runner.async_add_session_to_memory(session=session)
    
    # Let's cleanly close the OpenSearch connection
    await memory_service.client.close()
    print("Done! See you next time.")

if __name__ == "__main__":
    # Ensure a clean async event loop execution
    asyncio.run(main())