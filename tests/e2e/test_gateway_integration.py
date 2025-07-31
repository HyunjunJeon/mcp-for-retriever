"""E2E test for Auth Gateway and MCP Server integration."""

import pytest
import httpx
import asyncio
import json
from typing import Optional


class TestUser:
    """Test user with role and permissions"""
    def __init__(self, email: str, password: str, roles: list[str]):
        self.email = email
        self.password = password
        self.roles = roles
        self.access_token: Optional[str] = None


class GatewayTestClient:
    """Test client for Auth Gateway"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    async def register_user(self, user: TestUser) -> bool:
        """Register a test user"""
        try:
            response = await self.client.post(
                f"{self.base_url}/auth/register",
                json={
                    "email": user.email,
                    "password": user.password,
                    "roles": user.roles
                }
            )
            return response.status_code == 201
        except httpx.HTTPStatusError:
            return False
    
    async def login_user(self, user: TestUser) -> bool:
        """Login and get access token"""
        response = await self.client.post(
            f"{self.base_url}/auth/login",
            json={
                "email": user.email,
                "password": user.password
            }
        )
        if response.status_code == 200:
            data = response.json()
            user.access_token = data["access_token"]
            return True
        return False
    
    async def call_mcp_tool(self, tool_name: str, args: dict, token: str) -> dict:
        """Call MCP tool through gateway using SSE"""
        from httpx_sse import aconnect_sse
        
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": args
            }
        }
        
        headers = {
            "authorization": f"Bearer {token}",
            "accept": "application/json, text/event-stream",
            "content-type": "application/json"
        }
        
        result = None
        
        # Use SSE endpoint
        async with aconnect_sse(
            self.client,
            "POST",
            f"{self.base_url}/mcp/sse",
            json=request,
            headers=headers,
        ) as event_source:
            async for sse in event_source.aiter_sse():
                if sse.data:
                    # Parse nested SSE events
                    lines = sse.data.strip().split('\n')
                    for line in lines:
                        if line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                                if data.get("id") == request["id"]:
                                    result = data
                                    break
                            except json.JSONDecodeError:
                                pass
                if result:
                    break
        
        return result or {"error": {"code": -32603, "message": "No response received"}}


@pytest.mark.asyncio
class TestGatewayIntegration:
    """Test Auth Gateway and MCP Server integration"""
    
    @pytest.fixture
    async def gateway_client(self):
        """Create gateway test client"""
        async with GatewayTestClient() as client:
            yield client
    
    @pytest.fixture
    async def test_users(self):
        """Create test users with different roles"""
        return {
            "guest": TestUser("guest@test.com", "GuestPass123", ["guest"]),
            "user": TestUser("user@test.com", "UserPass123", ["user"]),
            "power_user": TestUser("power@test.com", "PowerPass123", ["power_user"]),
            "admin": TestUser("admin@test.com", "AdminPass123", ["admin"])
        }
    
    async def test_unauthenticated_access_blocked(self, gateway_client):
        """Test that unauthenticated access is blocked"""
        # Try to call tool without token
        response = await gateway_client.client.post(
            f"{gateway_client.base_url}/mcp/proxy",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list"
            }
        )
        
        assert response.status_code == 401
        assert "detail" in response.json()
    
    async def test_guest_role_permissions(self, gateway_client, test_users):
        """Test guest role can only access health_check"""
        guest = test_users["guest"]
        
        # Register and login
        await gateway_client.register_user(guest)
        assert await gateway_client.login_user(guest)
        
        # Test health_check (should succeed)
        result = await gateway_client.call_mcp_tool(
            "health_check", {}, guest.access_token
        )
        assert "result" in result or "error" not in result
        
        # Test search_web (should fail)
        result = await gateway_client.call_mcp_tool(
            "search_web", {"query": "test"}, guest.access_token
        )
        assert "error" in result
        assert "권한" in result["error"]["message"]
    
    async def test_user_role_permissions(self, gateway_client, test_users):
        """Test user role can access web and vector search"""
        user = test_users["user"]
        
        # Register and login
        await gateway_client.register_user(user)
        assert await gateway_client.login_user(user)
        
        # Test health_check (should succeed)
        result = await gateway_client.call_mcp_tool(
            "health_check", {}, user.access_token
        )
        assert "error" not in result
        
        # Test search_web (should succeed but may fail with test API key)
        result = await gateway_client.call_mcp_tool(
            "search_web", {"query": "test", "limit": 1}, user.access_token
        )
        # Either success or API key error is acceptable
        if "error" in result:
            assert "API" in result["error"]["message"] or "Tavily" in result["error"]["message"]
        
        # Test search_database (should fail - need power_user)
        result = await gateway_client.call_mcp_tool(
            "search_database", {"query": "SELECT 1"}, user.access_token
        )
        assert "error" in result
        assert "권한" in result["error"]["message"]
    
    async def test_admin_role_full_access(self, gateway_client, test_users):
        """Test admin role has full access"""
        admin = test_users["admin"]
        
        # Register and login
        await gateway_client.register_user(admin)
        assert await gateway_client.login_user(admin)
        
        # List all tools using SSE
        from httpx_sse import aconnect_sse
        
        list_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list"
        }
        
        headers = {
            "authorization": f"Bearer {admin.access_token}",
            "accept": "application/json, text/event-stream",
            "content-type": "application/json"
        }
        
        result = None
        
        async with aconnect_sse(
            gateway_client.client,
            "POST",
            f"{gateway_client.base_url}/mcp/sse",
            json=list_request,
            headers=headers,
        ) as event_source:
            async for sse in event_source.aiter_sse():
                if sse.data:
                    lines = sse.data.strip().split('\n')
                    for line in lines:
                        if line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                                if data.get("id") == list_request["id"]:
                                    result = data
                                    break
                            except json.JSONDecodeError:
                                pass
                if result:
                    break
        if "result" in result:
            tools = result["result"]["tools"]
            tool_names = [tool["name"] for tool in tools]
            
            # Admin should see all tools
            assert "health_check" in tool_names
            assert "search_web" in tool_names
            assert "search_vectors" in tool_names
            assert "search_database" in tool_names
            assert "search_all" in tool_names
    
    async def test_gateway_mcp_server_separation(self, gateway_client):
        """Test that MCP server cannot be accessed directly"""
        # Try to access MCP server directly (should fail)
        try:
            response = await gateway_client.client.post(
                "http://localhost:8001/mcp/",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list"
                },
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream"
                }
            )
            # If accessible, it should require session
            assert response.status_code in [400, 406]  # Bad Request or Not Acceptable
        except httpx.ConnectError:
            # Server might not be exposing this endpoint
            pass


@pytest.mark.asyncio
async def test_complete_gateway_flow():
    """Run complete gateway integration test"""
    async with GatewayTestClient() as client:
        # Create test users
        users = {
            "guest": TestUser("flow_guest@test.com", "GuestPass123", ["guest"]),
            "user": TestUser("flow_user@test.com", "UserPass123", ["user"]),
            "admin": TestUser("flow_admin@test.com", "AdminPass123", ["admin"])
        }
        
        print("\n🔐 Testing Auth Gateway Integration...\n")
        
        # Test each user
        for role, user in users.items():
            print(f"Testing {role} role:")
            
            # Register
            if await client.register_user(user):
                print(f"  ✅ Registered {user.email}")
            else:
                print(f"  ⚠️  User {user.email} already exists")
            
            # Login
            if await client.login_user(user):
                print(f"  ✅ Logged in successfully")
            else:
                print(f"  ❌ Login failed")
                continue
            
            # Test health_check (all roles should succeed)
            result = await client.call_mcp_tool("health_check", {}, user.access_token)
            if "error" not in result:
                print(f"  ✅ health_check: Success")
            else:
                print(f"  ❌ health_check: {result['error']['message']}")
            
            # Test search_web (guest should fail)
            result = await client.call_mcp_tool(
                "search_web", 
                {"query": "test", "limit": 1}, 
                user.access_token
            )
            if "error" in result:
                if "권한" in result["error"]["message"]:
                    print(f"  ✅ search_web: Correctly blocked (no permission)")
                else:
                    print(f"  ⚠️  search_web: {result['error']['message']}")
            else:
                print(f"  ✅ search_web: Access granted")
            
            print()
        
        print("✅ Gateway integration test complete!")


if __name__ == "__main__":
    asyncio.run(test_complete_gateway_flow())