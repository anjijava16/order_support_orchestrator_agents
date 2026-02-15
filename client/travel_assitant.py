import logging
from uuid import uuid4
import httpx
import json
from datetime import datetime

async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    base_url = 'http://localhost:9090'
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        # 1. Fetch agent card
        logger.info("🔍 Fetching agent card...")
        card_response = await client.get(f'{base_url}/.well-known/agent.json')
        card_response.raise_for_status()
        agent_card = card_response.json()
        logger.info(f"✅ Agent: {agent_card.get('name')}\n")
        
        endpoint_url = agent_card.get('url', base_url).rstrip('/')
        
        # 2. Regular non-streaming message
        logger.info(f"{'='*60}")
        logger.info("📤 REGULAR MESSAGE (non-streaming)")
        logger.info(f"{'='*60}\n")
        
        regular_request = {
            "jsonrpc": "2.0",
            "method": "message/send",
            "id": str(uuid4()),
            "params": {
                "message": {
                    "role": "user",
                    "parts": [
                        {
                            "kind": "text",
                            "text": "What is my order status 123."
                        }
                    ],
                    "messageId": uuid4().hex
                }
            }
        }
        
        response = await client.post(
            endpoint_url,
            json=regular_request,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        result = response.json()
        
        agent_message = result.get("result", {}).get("artifacts", [{}])[0].get("parts", [{}])[0].get("text", "")
        logger.info(f"✅ Received complete response")
        logger.info(f"📝 Message preview: {agent_message[:150]}...\n")
        
        # 3. TRUE STREAMING MESSAGE
        logger.info(f"{'='*60}")
        logger.info("📤 STREAMING MESSAGE (incremental chunks)")
        logger.info(f"{'='*60}\n")
        
        streaming_start = datetime.now()
        chunk_count = 0
        
        streaming_request = {
            "jsonrpc": "2.0",
            "method": "message/send",
            "id": str(uuid4()),
            "params": {
                "message": {
                    "role": "user",
                    "parts": [
                        {
                            "kind": "text",
                            "text": "What is my order status 123.."
                        }
                    ],
                    "messageId": uuid4().hex
                }
            }
        }
        
        try:
            # Use httpx streaming with proper handling
            async with client.stream(
                'POST',
                endpoint_url,
                json=streaming_request,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                }
            ) as stream_response:
                stream_response.raise_for_status()
                
                logger.info("🌊 Streaming connection opened\n")
                
                # Read the response byte by byte to catch each JSON object
                buffer = ""
                async for chunk_bytes in stream_response.aiter_bytes():
                    buffer += chunk_bytes.decode('utf-8')
                    
                    # Try to parse complete JSON objects from buffer
                    while True:
                        try:
                            # Try to find a complete JSON object
                            obj, idx = json.JSONDecoder().raw_decode(buffer)
                            buffer = buffer[idx:].lstrip()
                            
                            # We got a complete JSON object!
                            chunk_count += 1
                            elapsed = (datetime.now() - streaming_start).total_seconds()
                            
                            result_data = obj.get('result', {})
                            kind = result_data.get('kind', 'unknown')
                            is_final = result_data.get('final', False)
                            
                            logger.info(f"🌊 Chunk #{chunk_count} @ {elapsed:.2f}s")
                            logger.info(f"   Kind: {kind}")
                            logger.info(f"   Final: {is_final}")
                            
                            # Check for artifact data
                            if 'artifact' in result_data:
                                artifact = result_data['artifact']
                                parts = artifact.get('parts', [])
                                if parts and 'text' in parts[0]:
                                    text_preview = parts[0]['text'][:100]
                                    logger.info(f"   Text: {text_preview}...")
                            
                            # Check for artifacts array
                            if 'artifacts' in result_data:
                                artifacts = result_data['artifacts']
                                if artifacts:
                                    parts = artifacts[0].get('parts', [])
                                    if parts and 'text' in parts[0]:
                                        text_preview = parts[0]['text'][:100]
                                        logger.info(f"   Text: {text_preview}...")
                            
                            # Print full chunk for debugging
                            print(f"\n--- Chunk #{chunk_count} ---")
                            print(json.dumps(obj, indent=2))
                            print()
                            
                            logger.info("")
                            
                        except json.JSONDecodeError:
                            # Not enough data for a complete JSON object yet
                            break
                
                # Handle any remaining data in buffer
                if buffer.strip():
                    logger.warning(f"⚠️  Leftover data in buffer: {buffer[:100]}")
                
                total_time = (datetime.now() - streaming_start).total_seconds()
                
                logger.info(f"\n{'='*60}")
                logger.info(f"✅ Streaming completed")
                logger.info(f"⏱️  Total duration: {total_time:.2f}s")
                logger.info(f"📦 Total chunks received: {chunk_count}")
                logger.info(f"{'='*60}\n")
                
                if chunk_count == 1:
                    logger.warning("⚠️  Only received 1 chunk - server may not be truly streaming")
                elif chunk_count > 1:
                    logger.info(f"✅ TRUE STREAMING confirmed with {chunk_count} incremental updates!")
                
        except Exception as e:
            logger.error(f"❌ Streaming error: {e}", exc_info=True)
        
        # 4. Multi-turn conversation example
        logger.info(f"\n{'='*60}")
        logger.info("📤 MULTI-TURN CONVERSATION")
        logger.info(f"{'='*60}\n")
        
        # First message
        first_message = {
            "jsonrpc": "2.0",
            "method": "message/send",
            "id": str(uuid4()),
            "params": {
                "message": {
                    "role": "user",
                    "parts": [
                        {
                            "kind": "text",
                            "text": "I need a gastroenterologist"
                        }
                    ],
                    "messageId": uuid4().hex
                }
            }
        }
        
        first_response = await client.post(endpoint_url, json=first_message, headers={"Content-Type": "application/json"})
        first_response.raise_for_status()
        first_result = first_response.json()
        
        task_id = first_result.get("result", {}).get("id")
        context_id = first_result.get("result", {}).get("contextId")
        
        logger.info(f"✅ First message sent")
        logger.info(f"📋 Task ID: {task_id}")
        logger.info(f"📋 Context ID: {context_id}\n")
        
        # Follow-up message
        followup_message = {
            "jsonrpc": "2.0",
            "method": "message/send",
            "id": str(uuid4()),
            "params": {
                "message": {
                    "role": "user",
                    "parts": [
                        {
                            "kind": "text",
                            "text": "What is my order status 123."
                        }
                    ],
                    "messageId": uuid4().hex,
                    "taskId": task_id,
                    "contextId": context_id
                }
            }
        }
        
        followup_response = await client.post(endpoint_url, json=followup_message, headers={"Content-Type": "application/json"})
        followup_response.raise_for_status()
        followup_result = followup_response.json()
        
        followup_text = followup_result.get("result", {}).get("artifacts", [{}])[0].get("parts", [{}])[0].get("text", "")
        logger.info(f"✅ Follow-up response received")
        logger.info(f"📝 Response: {followup_text[:200]}...\n")


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())