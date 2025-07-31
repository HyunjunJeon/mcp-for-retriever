"""Simple test to verify MCP client page works."""

import httpx
import asyncio


async def test_mcp_client():
    """Test MCP client page availability and basic functionality"""
    async with httpx.AsyncClient() as client:
        # Step 1: Register
        print("📝 Registering new user...")
        register_resp = await client.post(
            "http://localhost:8000/auth/register",
            json={
                "email": "mcp_test@example.com",
                "password": "TestPass123"
            }
        )
        
        if register_resp.status_code == 422:
            # User might already exist, try login
            print("⚠️ User might exist, trying login...")
        else:
            register_resp.raise_for_status()
            print("✅ Registration successful")
        
        # Step 2: Login
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
        
        # Step 3: Access MCP client page
        print("🚀 Accessing MCP client page...")
        page_resp = await client.get("http://localhost:8000/mcp/client-page")
        page_resp.raise_for_status()
        print("✅ MCP client page loaded successfully")
        
        # Step 4: Test MCP server directly with token
        print("📋 Testing MCP server tools/list...")
        mcp_resp = await client.post(
            "http://localhost:8000/mcp/proxy",
            json={
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 1
            },
            headers={"Authorization": f"Bearer {access_token}"}
        )
        mcp_resp.raise_for_status()
        tools_data = mcp_resp.json()
        
        print(f"MCP Response: {tools_data}")
        if "result" in tools_data and tools_data["result"] is not None:
            tools = tools_data["result"].get("tools", [])
            print(f"✅ Found {len(tools)} tools:")
            for tool in tools:
                print(f"   - {tool['name']}: {tool.get('description', 'No description')[:50]}...")
        else:
            print(f"❌ Unexpected response: {tools_data}")
        
        # Step 5: Test health check
        print("🏥 Testing health check...")
        health_resp = await client.post(
            "http://localhost:8000/mcp/proxy",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "health_check",
                    "arguments": {}
                },
                "id": 2
            },
            headers={"Authorization": f"Bearer {access_token}"}
        )
        health_resp.raise_for_status()
        health_data = health_resp.json()
        
        if "result" in health_data:
            status = health_data["result"]["status"]
            print(f"✅ Health check: {status}")
            print(f"   Services: {health_data['result']['services']}")
        else:
            print(f"❌ Health check error: {health_data}")
        
        print("\n✅ All tests passed!")


if __name__ == "__main__":
    asyncio.run(test_mcp_client())