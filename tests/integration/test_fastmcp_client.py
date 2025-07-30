"""Integration tests using FastMCP Client for proper MCP protocol testing."""

import pytest
import asyncio
from unittest.mock import patch, AsyncMock
from fastmcp import Client
from fastapi.testclient import TestClient

from src.server import mcp, retrievers
from src.auth.server import app as auth_app
from tests.fixtures.mock_retriever import MockRetriever


class TestFastMCPClientIntegration:
    """Test MCP protocol compliance using FastMCP's Client with updated server."""

    @pytest.fixture
    def mcp_server(self):
        """Get the MCP server instance for testing."""
        # Return the actual server but we'll set up mock retrievers
        return mcp
    
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
        # Clear existing retrievers
        retrievers.clear()
        
        # Create mock retrievers with test data
        web_retriever = MockRetriever({
            "type": "tavily",
            "mock_data": [
                {
                    "title": "FastMCP Documentation",
                    "url": "https://gofastmcp.com",
                    "content": "Official FastMCP documentation and examples",
                    "score": 0.95,
                    "source": "web"
                },
                {
                    "title": "MCP Protocol Guide",
                    "url": "https://modelcontextprotocol.io",
                    "content": "Complete guide to Model Context Protocol",
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
                    "text": "Vector search capabilities with Qdrant",
                    "score": 0.91,
                    "metadata": {"topic": "vector_search", "category": "retrieval"},
                    "source": "vectors"
                },
                {
                    "id": "vec-002", 
                    "text": "Embedding and similarity search techniques",
                    "score": 0.85,
                    "metadata": {"topic": "embeddings", "category": "ml"},
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
                    "category": "software_engineering",
                    "source": "database"
                },
                {
                    "id": 2,
                    "title": "Advanced SQL Techniques",
                    "author": "Joe Celko",
                    "year": 2023,
                    "category": "database",
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
    
    async def test_mcp_tool_discovery(self, mcp_server, setup_mock_retrievers):
        """Test MCP client tool discovery using FastMCP Client."""
        async with Client(mcp_server) as client:
            # List available tools
            tools = await client.list_tools()
            
            # Verify all expected tools are available
            tool_names = [tool.name for tool in tools]
            expected_tools = [
                "search_web", 
                "search_vectors", 
                "search_database", 
                "search_all",
                "health_check"
            ]
            
            for expected_tool in expected_tools:
                assert expected_tool in tool_names, f"Tool {expected_tool} not found in {tool_names}"
            
            # Verify tool metadata
            web_tool = next(t for t in tools if t.name == "search_web")
            assert web_tool.description
            assert "query" in web_tool.inputSchema.get("properties", {})
            assert web_tool.inputSchema["properties"]["query"]["type"] == "string"
    
    async def test_mcp_web_search_tool(self, mcp_server, setup_mock_retrievers):
        """Test web search tool through MCP client."""
        async with Client(mcp_server) as client:
            # Execute web search tool
            result = await client.call_tool(
                "search_web",
                {
                    "query": "FastMCP documentation",
                    "limit": 5
                }
            )
            
            # Verify result structure - now returns list directly
            assert isinstance(result.data, list)
            assert len(result.data) == 2
            
            # Verify result content
            first_result = result.data[0]
            assert first_result["source"] == "web"
            assert "FastMCP" in first_result["title"]
            assert first_result["score"] > 0.8
    
    async def test_mcp_vector_search_tool(self, mcp_server, setup_mock_retrievers):
        """Test vector search tool through MCP client."""
        async with Client(mcp_server) as client:
            # Execute vector search
            result = await client.call_tool(
                "search_vectors",
                {
                    "query": "vector similarity search",
                    "collection": "documents",
                    "limit": 10,
                    "score_threshold": 0.7
                }
            )
            
            # Verify results
            assert isinstance(result.data, list)
            assert len(result.data) == 2
            
            for item in result.data:
                assert item["source"] == "vectors"
                assert item["score"] >= 0.7
                assert "metadata" in item
    
    async def test_mcp_database_search_tool(self, mcp_server, setup_mock_retrievers):
        """Test database search tool through MCP client."""
        async with Client(mcp_server) as client:
            # Execute database search with SQL query
            result = await client.call_tool(
                "search_database",
                {
                    "query": "SELECT * FROM books WHERE year >= 2023",
                    "limit": 10
                }
            )
            
            assert isinstance(result.data, list)
            assert len(result.data) == 2
            
            # Verify database results
            for item in result.data:
                assert item["source"] == "database"
                assert item["year"] >= 2023
                assert "author" in item
    
    async def test_mcp_search_all_tool(self, mcp_server, setup_mock_retrievers):
        """Test searching all sources concurrently through MCP client."""
        async with Client(mcp_server) as client:
            # Execute search across all sources
            result = await client.call_tool(
                "search_all",
                {
                    "query": "comprehensive search test",
                    "limit": 5
                }
            )
            
            # Verify result structure
            assert isinstance(result.data, dict)
            assert "results" in result.data
            assert "errors" in result.data
            assert "sources_searched" in result.data
            
            # Verify all sources returned results
            assert "tavily" in result.data["results"]
            assert "qdrant" in result.data["results"]
            assert "postgres" in result.data["results"]
            
            # Check individual results
            assert len(result.data["results"]["tavily"]) == 2
            assert len(result.data["results"]["qdrant"]) == 2
            assert len(result.data["results"]["postgres"]) == 2
            
            # Should have no errors with all retrievers connected
            assert len(result.data["errors"]) == 0
    
    async def test_mcp_health_check_tool(self, mcp_server, setup_mock_retrievers):
        """Test health check tool through MCP client."""
        async with Client(mcp_server) as client:
            # Execute health check
            result = await client.call_tool("health_check", {})
            
            # Verify health status structure
            assert isinstance(result.data, dict)
            assert result.data["service"] == "mcp-retriever"
            assert result.data["status"] == "healthy"
            assert "retrievers" in result.data
            
            # Check individual retriever health
            for name in ["tavily", "qdrant", "postgres"]:
                assert name in result.data["retrievers"]
                assert result.data["retrievers"][name]["connected"] is True
                assert "status" in result.data["retrievers"][name]
    
    async def test_mcp_error_handling(self, mcp_server):
        """Test error handling through MCP client."""
        retrievers.clear()  # No retrievers available
        
        async with Client(mcp_server) as client:
            # Try to search without any retrievers - should raise ToolError
            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "search_web",
                    {"query": "test"}
                )
            
            # FastMCP should convert ToolError to proper MCP error
            error_msg = str(exc_info.value).lower()
            assert "not available" in error_msg or "tool error" in error_msg
    
    async def test_mcp_missing_parameters(self, mcp_server, setup_mock_retrievers):
        """Test handling missing required parameters."""
        async with Client(mcp_server) as client:
            # Try vector search without required collection parameter
            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "search_vectors",
                    {"query": "test"}  # Missing collection
                )
            
            # Should indicate missing parameter
            error_msg = str(exc_info.value).lower()
            assert "collection" in error_msg or "required" in error_msg
    
    async def test_mcp_concurrent_requests(self, mcp_server, setup_mock_retrievers):
        """Test handling concurrent requests through MCP client."""
        async with Client(mcp_server) as client:
            # Create multiple concurrent tasks
            tasks = []
            for i in range(5):
                task = client.call_tool(
                    "search_web",
                    {"query": f"concurrent query {i}", "limit": 3}
                )
                tasks.append(task)
            
            # Execute all tasks concurrently
            results = await asyncio.gather(*tasks)
            
            # Verify all requests succeeded
            assert len(results) == 5
            for result in results:
                assert isinstance(result.data, list)
                assert len(result.data) == 2  # Mock data has 2 items
    
    async def test_mcp_partial_failure_handling(self, mcp_server, setup_mock_retrievers):
        """Test handling partial failures in search_all."""
        # Make one retriever fail by disconnecting it
        await retrievers["qdrant"].disconnect()
        retrievers["qdrant"]._connected = False
        
        async with Client(mcp_server) as client:
            result = await client.call_tool(
                "search_all",
                {"query": "partial failure test", "limit": 5}
            )
            
            # Should still return results structure
            assert isinstance(result.data, dict)
            assert "results" in result.data
            assert "errors" in result.data
            
            # Should have results from working retrievers
            assert "tavily" in result.data["results"]
            assert "postgres" in result.data["results"]
            
            # Should have error for disconnected retriever
            assert "qdrant" in result.data["errors"]
            assert len(result.data["errors"]) == 1
    
    async def test_mcp_context_functionality(self, mcp_server, setup_mock_retrievers):
        """Test that Context is working properly (through logging behavior)."""
        async with Client(mcp_server) as client:
            # Execute a search that should generate context logs
            result = await client.call_tool(
                "search_web",
                {"query": "context test", "limit": 1}
            )
            
            # If Context is working, the tool should execute successfully
            assert isinstance(result.data, list)
            assert len(result.data) == 2
            
            # Test progress reporting with larger search
            result = await client.call_tool(
                "search_all",
                {"query": "progress test", "limit": 10}
            )
            
            assert isinstance(result.data, dict)
            assert result.data["sources_searched"] == 3
    
    async def test_mcp_protocol_compliance(self, mcp_server, setup_mock_retrievers):
        """Test that our server follows MCP protocol specifications."""
        async with Client(mcp_server) as client:
            # Test 1: Tool listing
            tools = await client.list_tools()
            assert len(tools) >= 5  # At least our 5 core tools
            
            tool_names = [t.name for t in tools]
            expected_tools = [
                "search_web", 
                "search_vectors",
                "search_database",
                "search_all",
                "health_check"
            ]
            
            for expected in expected_tools:
                assert expected in tool_names
            
            # Test 2: Tool schema validation
            web_tool = next(t for t in tools if t.name == "search_web")
            assert web_tool.inputSchema
            assert "properties" in web_tool.inputSchema
            assert "query" in web_tool.inputSchema["properties"]
            
            # Test 3: Tool execution returns proper data
            result = await client.call_tool(
                "search_web",
                {"query": "MCP test", "limit": 1}
            )
            
            # Verify result is serializable and properly formatted
            assert hasattr(result, 'data')
            assert isinstance(result.data, (list, dict))
            
            # Test 4: Invalid tool name should raise appropriate error
            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "non_existent_tool",
                    {"param": "value"}
                )
            
            error_msg = str(exc_info.value).lower()
            assert "unknown tool" in error_msg or "not found" in error_msg or "tool" in error_msg
    
    async def test_mcp_with_different_parameters(self, mcp_server, setup_mock_retrievers):
        """Test tools with various parameter combinations."""
        async with Client(mcp_server) as client:
            # Web search with domain filtering
            result = await client.call_tool(
                "search_web",
                {
                    "query": "FastMCP",
                    "limit": 5,
                    "include_domains": ["gofastmcp.com"],
                    "exclude_domains": []
                }
            )
            assert isinstance(result.data, list)
            
            # Vector search with different threshold
            result = await client.call_tool(
                "search_vectors",
                {
                    "query": "machine learning",
                    "collection": "ml_docs",
                    "limit": 3,
                    "score_threshold": 0.9
                }
            )
            assert isinstance(result.data, list)
            
            # Database search with table specification
            result = await client.call_tool(
                "search_database",
                {
                    "query": "design patterns",
                    "table": "books",
                    "limit": 5
                }
            )
            assert isinstance(result.data, list)
    
    async def test_mcp_server_initialization(self, mcp_server):
        """Test server properties and initialization."""
        # Check server properties
        assert mcp_server.name == "mcp-retriever"
        assert mcp_server.instructions is not None
        assert len(mcp_server.instructions.strip()) > 0
        
        # Server should have lifespan
        assert mcp_server.lifespan is not None
        
        # Check that tools are properly registered
        tools = list(mcp_server._tools.values())
        assert len(tools) >= 5
    
    @pytest.mark.asyncio
    async def test_auth_integration_flow(self, auth_client):
        """Test the complete authentication flow for MCP integration."""
        # Test user registration
        register_response = auth_client.post(
            "/auth/register",
            json={
                "email": "mcp.integration@example.com",
                "password": "MCPTest123!"
            }
        )
        
        assert register_response.status_code == 200
        user_data = register_response.json()
        assert user_data["email"] == "mcp.integration@example.com"
        assert "id" in user_data
        
        # Test user login
        login_response = auth_client.post(
            "/auth/login",
            json={
                "email": "mcp.integration@example.com",
                "password": "MCPTest123!"
            }
        )
        
        assert login_response.status_code == 200
        token_data = login_response.json()
        assert "access_token" in token_data
        assert token_data["token_type"] == "Bearer"
        
        # Test token validation
        headers = {"Authorization": f"Bearer {token_data['access_token']}"}
        me_response = auth_client.get("/auth/me", headers=headers)
        
        assert me_response.status_code == 200
        user_info = me_response.json()
        assert user_info["email"] == "mcp.integration@example.com"
        
        return token_data["access_token"]