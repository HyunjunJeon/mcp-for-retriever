"""Integration tests using FastMCP Client for proper MCP protocol testing."""

import pytest
from unittest.mock import patch, AsyncMock
from fastmcp import Client
from fastapi.testclient import TestClient

from src.server import create_server, retrievers
from src.auth.server import app as auth_app
from tests.fixtures.mock_retriever import MockRetriever


class TestMCPClientIntegration:
    """Test MCP protocol compliance using FastMCP's Client."""

    @pytest.fixture
    def mcp_server(self):
        """Create MCP server instance for testing."""
        # Create server without running lifespan to avoid real connections
        from fastmcp import FastMCP
        
        server = FastMCP(
            name="mcp-retriever"
        )
        
        # Register tools directly
        from src.server import (
            search_web_tool,
            search_vectors_tool,
            search_database_tool,
            search_all_tool
        )
        
        server.tool(search_web_tool)
        server.tool(search_vectors_tool)
        server.tool(search_database_tool)
        server.tool(search_all_tool)
        
        return server
    
    @pytest.fixture
    def auth_app_instance(self):
        """Get auth app instance."""
        return auth_app
    
    @pytest.fixture
    def auth_client(self, auth_app_instance):
        """Create auth test client."""
        return TestClient(auth_app_instance)
    
    @pytest.fixture
    async def setup_mock_retrievers(self):
        """Set up mock retrievers for testing."""
        retrievers.clear()
        
        # Create mock retrievers with test data
        web_retriever = MockRetriever({
            "type": "tavily",
            "mock_data": [
                {
                    "title": "Python Documentation",
                    "url": "https://docs.python.org",
                    "content": "Official Python documentation",
                    "score": 0.95,
                    "source": "web"
                },
                {
                    "title": "Python Tutorial",
                    "url": "https://realpython.com",
                    "content": "Comprehensive Python tutorial",
                    "score": 0.88,
                    "source": "web"
                }
            ]
        })
        await web_retriever.connect()
        retrievers["tavily"] = web_retriever
        
        vector_retriever = MockRetriever({
            "type": "qdrant",
            "mock_data": [
                {
                    "id": "vec-001",
                    "text": "Machine learning fundamentals",
                    "score": 0.91,
                    "metadata": {"topic": "ML"},
                    "source": "vectors"
                }
            ]
        })
        await vector_retriever.connect()
        retrievers["qdrant"] = vector_retriever
        
        db_retriever = MockRetriever({
            "type": "postgres",
            "mock_data": [
                {
                    "id": 1,
                    "title": "Database Design Patterns",
                    "author": "Martin Fowler",
                    "year": 2024,
                    "source": "database"
                }
            ]
        })
        await db_retriever.connect()
        retrievers["postgres"] = db_retriever
        
        yield
        
        # Cleanup
        for retriever in retrievers.values():
            await retriever.disconnect()
        retrievers.clear()
    
    async def test_mcp_client_tool_discovery(self, mcp_server, setup_mock_retrievers):
        """Test MCP client tool discovery using FastMCP Client."""
        # Use FastMCP's Client to test our server in-memory
        async with Client(mcp_server) as client:
            # List available tools
            tools = await client.list_tools()
            
            # Verify all expected tools are available
            tool_names = [tool.name for tool in tools]
            assert "search_web_tool" in tool_names
            assert "search_vectors_tool" in tool_names
            assert "search_database_tool" in tool_names
            assert "search_all_tool" in tool_names
            
            # Verify tool metadata
            web_tool = next(t for t in tools if t.name == "search_web_tool")
            assert web_tool.description
            assert "query" in web_tool.inputSchema.get("properties", {})
            assert web_tool.inputSchema["properties"]["query"]["type"] == "string"
    
    async def test_mcp_client_single_tool_execution(self, mcp_server, setup_mock_retrievers):
        """Test executing a single tool through MCP client."""
        async with Client(mcp_server) as client:
            # Execute web search tool
            result = await client.call_tool(
                "search_web_tool",
                {
                    "query": "Python documentation",
                    "limit": 5
                }
            )
            
            # Verify result structure
            assert result.data["status"] == "success"
            assert "results" in result.data
            assert "count" in result.data
            assert len(result.data["results"]) == 2
            
            # Verify result content
            first_result = result.data["results"][0]
            assert first_result["source"] == "web"
            assert "Python" in first_result["title"]
    
    async def test_mcp_client_vector_search(self, mcp_server, setup_mock_retrievers):
        """Test vector search tool through MCP client."""
        async with Client(mcp_server) as client:
            # Execute vector search
            result = await client.call_tool(
                "search_vectors_tool",
                {
                    "query": "machine learning",
                    "collection": "documents",
                    "limit": 10,
                    "score_threshold": 0.7
                }
            )
            
            assert result.data["status"] == "success"
            assert len(result.data["results"]) == 1
            assert result.data["results"][0]["source"] == "vectors"
            assert result.data["results"][0]["score"] >= 0.7
    
    async def test_mcp_client_database_search(self, mcp_server, setup_mock_retrievers):
        """Test database search tool through MCP client."""
        async with Client(mcp_server) as client:
            # Execute database search
            result = await client.call_tool(
                "search_database_tool",
                {
                    "query": "SELECT * FROM books",
                    "limit": 10
                }
            )
            
            assert result.data["status"] == "success"
            assert len(result.data["results"]) == 1
            assert result.data["results"][0]["source"] == "database"
            assert result.data["results"][0]["author"] == "Martin Fowler"
    
    async def test_mcp_client_search_all(self, mcp_server, setup_mock_retrievers):
        """Test searching all sources concurrently through MCP client."""
        async with Client(mcp_server) as client:
            # Execute search across all sources
            result = await client.call_tool(
                "search_all_tool",
                {
                    "query": "comprehensive search",
                    "limit": 5
                }
            )
            
            assert result.data["status"] == "success"
            assert "results" in result.data
            assert len(result.data["results"]) == 3  # All three sources
            
            # Verify each source returned results
            assert "tavily" in result.data["results"]
            assert "qdrant" in result.data["results"]
            assert "postgres" in result.data["results"]
            
            assert len(result.data["results"]["tavily"]) == 2
            assert len(result.data["results"]["qdrant"]) == 1
            assert len(result.data["results"]["postgres"]) == 1
    
    async def test_mcp_client_error_handling(self, mcp_server):
        """Test error handling through MCP client."""
        retrievers.clear()  # No retrievers available
        
        async with Client(mcp_server) as client:
            # Try to search without any retrievers
            result = await client.call_tool(
                "search_web_tool",
                {"query": "test"}
            )
            
            assert result.data["status"] == "error"
            assert "not available" in result.data["error"]
    
    async def test_mcp_client_missing_parameters(self, mcp_server, setup_mock_retrievers):
        """Test handling missing required parameters."""
        async with Client(mcp_server) as client:
            # Try vector search without required collection parameter
            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "search_vectors_tool",
                    {"query": "test"}  # Missing collection
                )
            
            # FastMCP should validate parameters
            assert "collection" in str(exc_info.value) or "required" in str(exc_info.value)
    
    async def test_mcp_client_concurrent_requests(self, mcp_server, setup_mock_retrievers):
        """Test handling concurrent requests through MCP client."""
        import asyncio
        
        async with Client(mcp_server) as client:
            # Create multiple concurrent tasks
            tasks = []
            for i in range(5):
                task = client.call_tool(
                    "search_web_tool",
                    {"query": f"concurrent query {i}", "limit": 3}
                )
                tasks.append(task)
            
            # Execute all tasks concurrently
            results = await asyncio.gather(*tasks)
            
            # Verify all requests succeeded
            assert len(results) == 5
            for result in results:
                assert result.data["status"] == "success"
                assert len(result.data["results"]) == 2  # Mock data has 2 items
    
    async def test_mcp_client_with_authentication_proxy(self, mcp_server, auth_client, setup_mock_retrievers):
        """Test MCP client through authentication proxy."""
        # This tests the integration between auth gateway and MCP server
        # First, register and login a user
        auth_client.post(
            "/api/v1/auth/register",
            json={
                "email": "mcp.test@example.com",
                "password": "MCPTest123!",
                "name": "MCP Test User"
            }
        )
        
        login_response = auth_client.post(
            "/api/v1/auth/token",
            data={
                "username": "mcp.test@example.com",
                "password": "MCPTest123!"
            }
        )
        
        token = login_response.json()["access_token"]
        
        # Mock the MCP proxy to forward to our in-memory server
        with patch('src.auth.server.mcp_proxy.execute_request') as mock_proxy:
            async def forward_to_mcp(request, user):
                # Use the MCP client to execute the request
                async with Client(mcp_server) as client:
                    result = await client.call_tool(
                        request["method"],
                        request.get("params", {})
                    )
                    return {
                        "jsonrpc": "2.0",
                        "result": result.data,
                        "id": request.get("id", 1)
                    }
            
            mock_proxy.side_effect = forward_to_mcp
            
            # Make request through auth gateway
            mcp_request = {
                "jsonrpc": "2.0",
                "method": "search_web_tool",
                "params": {"query": "authenticated search", "limit": 5},
                "id": 1
            }
            
            response = auth_client.post(
                "/api/v1/mcp/execute",
                json=mcp_request,
                headers={"Authorization": f"Bearer {token}"}
            )
            
            assert response.status_code == 200
            result = response.json()
            assert result["jsonrpc"] == "2.0"
            assert result["result"]["status"] == "success"
            assert len(result["result"]["results"]) == 2
    
    async def test_mcp_protocol_compliance(self, mcp_server, setup_mock_retrievers):
        """Test that our server follows MCP protocol specifications."""
        async with Client(mcp_server) as client:
            # Test 1: Tool listing
            tools = await client.list_tools()
            assert len(tools) == 4
            tool_names = [t.name for t in tools]
            assert all(name in tool_names for name in [
                "search_web_tool", 
                "search_vectors_tool",
                "search_database_tool",
                "search_all_tool"
            ])
            
            # Test 2: Tool execution with proper result format
            result = await client.call_tool(
                "search_web_tool",
                {"query": "MCP test", "limit": 1}
            )
            
            # Verify MCP compliant response
            assert hasattr(result, 'data')
            assert isinstance(result.data, dict)
            assert result.data["status"] in ["success", "error"]
            
            # Test 3: Invalid tool name should raise appropriate error
            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "non_existent_tool",
                    {"param": "value"}
                )
            
            assert "unknown tool" in str(exc_info.value).lower() or "not found" in str(exc_info.value).lower()
    
    async def test_mcp_client_partial_failure_handling(self, mcp_server, setup_mock_retrievers):
        """Test handling partial failures in search_all."""
        # Make one retriever fail
        retrievers["qdrant"]._connected = False
        
        async with Client(mcp_server) as client:
            result = await client.call_tool(
                "search_all_tool",
                {"query": "partial failure test", "limit": 5}
            )
            
            assert result.data["status"] == "success"
            
            # Should have results from working retrievers
            assert "tavily" in result.data["results"]
            assert "postgres" in result.data["results"]
            
            # Should have error for disconnected retriever
            assert "qdrant" in result.data["errors"]
            assert "not connected" in result.data["errors"]["qdrant"]