"""Test SSE proxy functionality."""

import httpx
import asyncio
import json
from httpx_sse import aconnect_sse


async def test_sse_proxy():
    """Test SSE proxy through Auth Gateway"""
    async with httpx.AsyncClient() as client:
        # Try to register first
        print("📝 Trying to register...")
        try:
            register_resp = await client.post(
                "http://localhost:8000/auth/register",
                json={
                    "email": "mcp_test@example.com",
                    "password": "TestPass123"
                }
            )
            if register_resp.status_code == 201:
                print("✅ Registration successful")
            elif register_resp.status_code == 422:
                print("⚠️ User already exists")
        except Exception as e:
            print(f"Registration error: {e}")
        
        # Step 1: Login
        print("🔐 Logging in...")
        login_resp = await client.post(
            "http://localhost:8000/auth/login",
            json={
                "email": "mcp_test@example.com",
                "password": "TestPass123"
            }
        )
        login_resp.raise_for_status()
        tokens = login_resp.json()
        access_token = tokens["access_token"]
        print(f"✅ Got access token: {access_token[:20]}...")
        
        # Step 2: Test SSE endpoint
        print("\n🔄 Testing SSE proxy...")
        
        # Initialize MCP session
        init_request = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "id": 1,
            "params": {
                "protocolVersion": "1.0.0",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                }
            }
        }
        
        headers = {
            "authorization": f"Bearer {access_token}",
            "accept": "application/json, text/event-stream",
            "content-type": "application/json"
        }
        
        print("📡 Connecting to SSE endpoint...")
        
        try:
            async with aconnect_sse(
                client,
                "POST",
                "http://localhost:8000/mcp/sse",
                json=init_request,
                headers=headers,
            ) as event_source:
                print("✅ Connected to SSE stream")
                
                # Read first few events
                event_count = 0
                async for sse in event_source.aiter_sse():
                    event_count += 1
                    print(f"\nEvent {event_count}:")
                    if sse.event:
                        print(f"  Type: {sse.event}")
                    if sse.data:
                        print(f"  Data: {sse.data}")
                    
                    # Parse and check if it's the initialize response
                    if sse.data:
                        try:
                            data = json.loads(sse.data)
                            if data.get("method") == "initialize" or data.get("result"):
                                print("\n✅ Received initialize response!")
                                print(f"   Response: {json.dumps(data, indent=2)}")
                                break
                        except json.JSONDecodeError:
                            pass
                    
                    if event_count > 10:
                        print("\n⚠️ Too many events without initialize response")
                        break
                        
        except Exception as e:
            print(f"❌ SSE Error: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_sse_proxy())