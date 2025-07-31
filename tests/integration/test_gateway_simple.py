"""Simple gateway integration test."""

import httpx
import asyncio
import json
from httpx_sse import aconnect_sse


async def sse_request(base_url: str, token: str, request_data: dict) -> dict:
    """Send SSE request and get response"""
    headers = {
        "authorization": f"Bearer {token}",
        "accept": "application/json, text/event-stream",
        "content-type": "application/json"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        async with aconnect_sse(
            client,
            "POST",
            f"{base_url}/mcp/sse",
            json=request_data,
            headers=headers,
        ) as event_source:
            async for sse in event_source.aiter_sse():
                if sse.data:
                    lines = sse.data.strip().split('\n')
                    for line in lines:
                        if line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                                if "result" in data or "error" in data:
                                    return data
                            except json.JSONDecodeError:
                                pass
    
    return {"error": {"code": -32603, "message": "No response"}}


async def test_gateway():
    """Test gateway integration"""
    base_url = "http://localhost:8000"
    
    async with httpx.AsyncClient() as client:
        # Create test users
        users = [
            {"email": "test_guest@test.com", "password": "GuestPass123", "roles": ["guest"]},
            {"email": "test_user@test.com", "password": "UserPass123", "roles": ["user"]},
            {"email": "test_admin@test.com", "password": "AdminPass123", "roles": ["admin"]},
        ]
        
        print("🔐 Testing Gateway Role-Based Access Control\n")
        
        for user_data in users:
            print(f"\n📧 Testing {user_data['email']} ({user_data['roles'][0]})")
            
            # Register
            try:
                await client.post(f"{base_url}/auth/register", json=user_data)
                print("  ✅ Registered")
            except:
                print("  ⚠️  Already registered")
            
            # Login
            login_resp = await client.post(
                f"{base_url}/auth/login",
                json={"email": user_data["email"], "password": user_data["password"]}
            )
            if login_resp.status_code != 200:
                print(f"  ❌ Login failed: {login_resp.status_code}")
                continue
            
            token = login_resp.json()["access_token"]
            print("  ✅ Logged in")
            
            # Initialize session
            init_resp = await sse_request(base_url, token, {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "1.0.0",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0.0"}
                }
            })
            
            if "result" in init_resp:
                print("  ✅ Session initialized")
            else:
                print(f"  ❌ Init failed: {init_resp.get('error', {}).get('message', 'Unknown')}")
            
            # Test tools based on role
            tools_to_test = ["health_check", "search_web"]
            
            for tool in tools_to_test:
                resp = await sse_request(base_url, token, {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": tool,
                        "arguments": {"query": "test"} if tool == "search_web" else {}
                    }
                })
                
                if "error" in resp:
                    error_msg = resp["error"]["message"]
                    if "권한" in error_msg:
                        print(f"  🚫 {tool}: Access denied (correct)")
                    else:
                        print(f"  ⚠️  {tool}: {error_msg}")
                else:
                    print(f"  ✅ {tool}: Access granted")
        
        print("\n\n📊 Expected Results:")
        print("  - guest: health_check ✅, search_web 🚫")
        print("  - user: health_check ✅, search_web ✅")
        print("  - admin: health_check ✅, search_web ✅")


if __name__ == "__main__":
    asyncio.run(test_gateway())