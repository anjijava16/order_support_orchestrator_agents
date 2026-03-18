# main.py
from fastapi import FastAPI, HTTPException
from langchain_core.messages import HumanMessage
from graph import app, checkpointer
import pickle


api = FastAPI()

@api.post("/chat")
async def chat(msg: str, order_id: str = "", amount: float = 0, thread_id: str = ""):
    state_input = {
        "messages": [HumanMessage(content=msg)],
        "order_id": order_id,
        "amount": amount
    }
    result = app.invoke(
        state_input,
        config={
            "configurable": {
                "thread_id": thread_id  # pass unique ID per user/session
            }
        }
    )
    return result
# Human approval endpoint
@api.post("/approve_refund")
async def approve(thread_id: str):
    result = app.invoke(
        None,
        config={
            "configurable": {
                "thread_id": thread_id  # same ID used when paused
            },
            "resume": True,
            "value": True  # human approved
        }
    )
    return result

@api.get("/checkpoint/{thread_id}")
async def get_checkpoint(thread_id: str):
    """Retrieve checkpoint information for a given thread_id from the database."""
    try:
        with checkpointer._cursor() as cur:
            cur.execute(
                "SELECT checkpoint_id, parent_checkpoint_id, checkpoint, metadata "
                "FROM checkpoints WHERE thread_id=%s "
                "ORDER BY checkpoint_id DESC",
                (thread_id,)
            )
            rows = cur.fetchall()
            
            if not rows:
                raise HTTPException(status_code=404, detail=f"No checkpoints found for thread_id: {thread_id}")
            
            # Deserialize all checkpoints
            checkpoints = []
            for row in rows:
                # DictCursor returns dictionaries, not tuples
                checkpoint_id = row.get('checkpoint_id')
                parent_id = row.get('parent_checkpoint_id')
                checkpoint_data = row.get('checkpoint')
                metadata_data = row.get('metadata')
                
                try:
                    # Ensure checkpoint_data and metadata_data are bytes
                    if isinstance(checkpoint_data, str):
                        checkpoint_data = checkpoint_data.encode()
                    if isinstance(metadata_data, str):
                        metadata_data = metadata_data.encode()
                    
                    checkpoint = pickle.loads(checkpoint_data)
                    metadata = pickle.loads(metadata_data)
                    checkpoints.append({
                        "checkpoint_id": checkpoint_id,
                        "parent_checkpoint_id": parent_id,
                        "checkpoint": checkpoint,
                        "metadata": metadata
                    })
                except Exception as e:
                    checkpoints.append({
                        "checkpoint_id": checkpoint_id,
                        "parent_checkpoint_id": parent_id,
                        "error": f"Failed to deserialize: {str(e)}"
                    })
            
            return {
                "thread_id": thread_id,
                "count": len(checkpoints),
                "checkpoints": checkpoints
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(api, host="0.0.0.0", port=8203, reload=False)