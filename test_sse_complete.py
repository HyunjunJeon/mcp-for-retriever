"""Complete SSE proxy test with tools/list and tools/call."""

import httpx
import asyncio
import json
from httpx_sse import aconnect_sse


async def send_sse_request(client, token, request_data):
    """Send SSE request and collect response"""
    headers = {
        "authorization": f"Bearer {token}",
        "accept": "application/json, text/event-stream",
        "content-type": "application/json"
    }
    
    responses = []
    all_events = []
    
    async with aconnect_sse(
        client,
        "POST",
        "http://localhost:8000/mcp/sse",
        json=request_data,
        headers=headers,
    ) as event_source:
        async for sse in event_source.aiter_sse():
            # Debug: print all events
            event_info = {
                "event": sse.event,
                "data": sse.data,
                "id": sse.id
            }
            all_events.append(event_info)
            
            if sse.data:
                # Parse nested SSE events
                lines = sse.data.strip().split('\n')
                current_event = {}
                
                for line in lines:
                    if line.startswith("event: "):
                        current_event["event"] = line[7:]
                    elif line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            if "result" in data or "error" in data:
                                responses.append(data)
                                # If we got a complete response, break
                                if data.get("id") == request_data.get("id"):
                                    return responses
                        except json.JSONDecodeError:
                            pass
    
    # Debug output
    if not responses:
        print(f"DEBUG: No responses found. All events: {json.dumps(all_events, indent=2)}")
    
    return responses


async def test_complete_sse_flow():
    """Test complete SSE flow with initialize, tools/list, and tools/call"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Register/Login
        print("🔐 Authentication...")
        try:
            await client.post(
                "http://localhost:8000/auth/register",
                json={"email": "sse_test@example.com", "password": "TestPass123"}
            )
        except:
            pass
        
        login_resp = await client.post(
            "http://localhost:8000/auth/login",
            json={"email": "sse_test@example.com", "password": "TestPass123"}
        )
        login_resp.raise_for_status()
        access_token = login_resp.json()["access_token"]
        print("✅ Authenticated")
        
        # Test 1: Initialize
        print("\n1️⃣ Testing initialize...")
        init_request = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "id": 1,
            "params": {
                "protocolVersion": "1.0.0",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"}
            }
        }
        
        responses = await send_sse_request(client, access_token, init_request)
        if responses:
            print("✅ Initialize response:")
            print(json.dumps(responses[-1], indent=2))
        
        # Test 2: List tools
        print("\n2️⃣ Testing tools/list...")
        list_request = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "id": 2
        }
        
        responses = await send_sse_request(client, access_token, list_request)
        if responses:
            result = responses[-1].get("result", {})
            tools = result.get("tools", [])
            print(f"✅ Found {len(tools)} tools:")
            for tool in tools:
                print(f"   - {tool['name']}: {tool.get('description', 'No description')[:60]}...")
        
        # Test 3: Call health_check tool
        print("\n3️⃣ Testing tools/call (health_check)...")
        call_request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 3,
            "params": {
                "name": "health_check",
                "arguments": {}
            }
        }
        
        responses = await send_sse_request(client, access_token, call_request)
        if responses:
            print("✅ Health check response:")
            print(json.dumps(responses[-1], indent=2))
        
        # Test 4: Search web (will fail with test API key)
        print("\n4️⃣ Testing tools/call (search_web)...")
        search_request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 4,
            "params": {
                "name": "search_web",
                "arguments": {
                    "query": "FastMCP tutorial",
                    "limit": 3
                }
            }
        }
        
        responses = await send_sse_request(client, access_token, search_request)
        if responses:
            result = responses[-1]
            if "error" in result:
                print(f"⚠️ Expected error (test API key): {result['error']['message']}")
            else:
                print("✅ Search response:")
                print(json.dumps(result, indent=2))
        
        print("\n✅ All SSE tests completed!")


if __name__ == "__main__":
    asyncio.run(test_complete_sse_flow())