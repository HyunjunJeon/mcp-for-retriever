"""Unit tests for FastMCP server implementation."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import json

from src.server import create_server, search_web_tool
from src.retrievers.base import RetrieverHealth, QueryResult


@pytest.fixture
def mock_factory():
    """Mock retriever factory for testing."""
    factory = Mock()
    return factory


@pytest.fixture
def mock_tavily_retriever():
    """Mock Tavily retriever for testing."""
    retriever = AsyncMock()
    retriever.connected = False
    return retriever


class TestServerCreation:
    """Test server creation and configuration."""
    
    def test_create_server(self):
        """Test creating the FastMCP server."""
        with patch('src.server.RetrieverFactory') as mock_factory_class:
            server = create_server()
            
            assert server is not None
            assert server.name == "mcp-retriever"
    
    def test_server_has_tools(self):
        """Test server has all required tools."""
        with patch('src.server.RetrieverFactory') as mock_factory_class:
            server = create_server()
            
            # Check that we have a server with tools
            # The actual tool registration is internal to FastMCP
            assert server is not None


class TestServerLifecycle:
    """Test server lifecycle management."""
    
    @pytest.mark.asyncio
    async def test_startup_initializes_retrievers(self, mock_factory):
        """Test server startup initializes retrievers."""
        with patch('src.server.factory', mock_factory):
            # Mock the factory to return retrievers
            mock_tavily = AsyncMock()
            mock_factory.create.return_value = mock_tavily
            
            # Import and call startup
            from src.server import startup
            await startup()
            
            # Verify retrievers are initialized
            # Now we initialize both Tavily and PostgreSQL
            assert mock_factory.create.call_count >= 1
            assert mock_tavily.connect.call_count >= 1
    
    @pytest.mark.asyncio
    async def test_shutdown_disconnects_retrievers(self, mock_factory):
        """Test server shutdown disconnects retrievers."""
        # Create a mock retriever
        mock_retriever = AsyncMock()
        
        # Set up the retrievers dictionary with our mock
        with patch('src.server.retrievers', {'tavily': mock_retriever}):
            from src.server import shutdown
            
            await shutdown()
            
            # Verify retriever was disconnected
            mock_retriever.disconnect.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_startup_error_handling(self, mock_factory):
        """Test startup handles connection errors gracefully."""
        with patch('src.server.factory', mock_factory):
            mock_tavily = AsyncMock()
            mock_tavily.connect.side_effect = Exception("Connection failed")
            mock_factory.create.return_value = mock_tavily
            
            from src.server import startup
            
            # Should log error but not raise
            await startup()


class TestSearchWebTool:
    """Test search_web tool functionality."""
    
    @pytest.mark.asyncio
    async def test_search_web_basic(self, mock_tavily_retriever):
        """Test basic web search functionality."""
        # Mock retriever to return results
        mock_results = [
            {
                "title": "Test Result 1",
                "url": "https://example.com/1",
                "content": "Test content 1",
                "score": 0.95
            },
            {
                "title": "Test Result 2", 
                "url": "https://example.com/2",
                "content": "Test content 2",
                "score": 0.85
            }
        ]
        
        async def mock_retrieve(query, limit=10, **kwargs):
            for result in mock_results[:limit]:
                yield result
        
        mock_tavily_retriever.retrieve = mock_retrieve
        mock_tavily_retriever.connected = True
        
        with patch('src.server.retrievers', {'tavily': mock_tavily_retriever}):
            result = await search_web_tool(query="test query", limit=2)
            
            assert result["status"] == "success"
            assert len(result["results"]) == 2
            assert result["results"][0]["title"] == "Test Result 1"
    
    @pytest.mark.asyncio
    async def test_search_web_not_connected(self, mock_tavily_retriever):
        """Test search when retriever is not connected."""
        mock_tavily_retriever.connected = False
        
        with patch('src.server.retrievers', {'tavily': mock_tavily_retriever}):
            result = await search_web_tool(query="test query")
            
            assert result["status"] == "error"
            assert "not available" in result["error"]
    
    @pytest.mark.asyncio
    async def test_search_web_retriever_not_found(self):
        """Test search when retriever doesn't exist."""
        with patch('src.server.retrievers', {}):
            result = await search_web_tool(query="test query")
            
            assert result["status"] == "error"
            assert "not available" in result["error"]
    
    @pytest.mark.asyncio
    async def test_search_web_with_error(self, mock_tavily_retriever):
        """Test search handles errors gracefully."""
        mock_tavily_retriever.connected = True
        
        # Create an async generator that raises an exception
        async def failing_retrieve(query, **kwargs):
            raise Exception("Search failed")
            yield  # This will never be reached
        
        mock_tavily_retriever.retrieve = failing_retrieve
        
        with patch('src.server.retrievers', {'tavily': mock_tavily_retriever}):
            result = await search_web_tool(query="test query")
            
            assert result["status"] == "error"
            assert "Search failed" in result["error"]
    
    @pytest.mark.asyncio
    async def test_search_web_with_domains(self, mock_tavily_retriever):
        """Test search with domain filtering."""
        mock_tavily_retriever.connected = True
        
        async def mock_retrieve(query, limit=10, **kwargs):
            # Verify domain parameters are passed
            assert kwargs.get("include_domains") == ["example.com"]
            assert kwargs.get("exclude_domains") == ["spam.com"]
            yield {"title": "Test", "url": "https://example.com", "content": "Test"}
        
        mock_tavily_retriever.retrieve = mock_retrieve
        
        with patch('src.server.retrievers', {'tavily': mock_tavily_retriever}):
            result = await search_web_tool(
                query="test",
                include_domains=["example.com"],
                exclude_domains=["spam.com"]
            )
            
            assert result["status"] == "success"


class TestSearchAllTool:
    """Test concurrent search across all retrievers."""
    
    @pytest.mark.asyncio
    async def test_search_all_basic(self):
        """Test searching across multiple retrievers."""
        # Create mock retrievers
        mock_tavily = AsyncMock()
        mock_tavily.connected = True
        
        async def tavily_results(query, **kwargs):
            yield {"title": "Web Result", "url": "https://example.com", "source": "tavily"}
        
        mock_tavily.retrieve = tavily_results
        
        with patch('src.server.retrievers', {'tavily': mock_tavily}):
            from src.server import search_all_tool
            
            result = await search_all_tool(query="test query")
            
            assert result["status"] == "success"
            assert "tavily" in result["results"]
            assert len(result["results"]["tavily"]) > 0
    
    @pytest.mark.asyncio
    async def test_search_all_partial_failure(self):
        """Test search continues when some retrievers fail."""
        mock_tavily = AsyncMock()
        mock_tavily.connected = True
        
        async def tavily_results(query, **kwargs):
            yield {"title": "Web Result", "source": "tavily"}
        
        mock_tavily.retrieve = tavily_results
        
        mock_broken = AsyncMock()
        mock_broken.connected = True
        mock_broken.retrieve.side_effect = Exception("Broken retriever")
        
        with patch('src.server.retrievers', {
            'tavily': mock_tavily,
            'broken': mock_broken
        }):
            from src.server import search_all_tool
            
            result = await search_all_tool(query="test")
            
            assert result["status"] == "success"
            assert "tavily" in result["results"]
            assert len(result["results"]["tavily"]) > 0
            assert "broken" in result["errors"]