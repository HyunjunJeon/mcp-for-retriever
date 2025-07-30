"""Unit tests for Tavily web search retriever."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import httpx

from src.retrievers.tavily import TavilyRetriever
from src.retrievers.base import (
    RetrieverHealth,
    ConnectionError,
    QueryError,
)


@pytest.fixture
def tavily_config():
    """Fixture for TavilyRetriever configuration."""
    return {
        "api_key": "test-api-key",
        "max_results": 10,
        "search_depth": "basic",
        "timeout": 30,
    }


@pytest.fixture
def mock_tavily_response():
    """Fixture for mock Tavily API response."""
    return {
        "query": "test query",
        "results": [
            {
                "title": "Test Result 1",
                "url": "https://example.com/1",
                "content": "This is test content 1",
                "score": 0.95,
                "published_date": "2024-01-01"
            },
            {
                "title": "Test Result 2",
                "url": "https://example.com/2",
                "content": "This is test content 2",
                "score": 0.87,
                "published_date": "2024-01-02"
            }
        ]
    }


class TestTavilyRetrieverConfiguration:
    """Test TavilyRetriever configuration and initialization."""
    
    def test_initialization_with_api_key(self, tavily_config):
        """Test retriever initialization with API key."""
        retriever = TavilyRetriever(tavily_config)
        
        assert retriever.config == tavily_config
        assert retriever.api_key == "test-api-key"
        assert retriever.max_results == 10
        assert retriever.search_depth == "basic"
        assert retriever.timeout == 30
        assert not retriever.connected
    
    def test_initialization_without_api_key(self):
        """Test retriever initialization fails without API key."""
        with pytest.raises(ValueError, match="api_key is required"):
            TavilyRetriever({})
    
    def test_initialization_with_defaults(self):
        """Test retriever initialization with default values."""
        config = {"api_key": "test-key"}
        retriever = TavilyRetriever(config)
        
        assert retriever.api_key == "test-key"
        assert retriever.max_results == 10  # default
        assert retriever.search_depth == "basic"  # default
        assert retriever.timeout == 30  # default


@pytest.mark.asyncio
class TestTavilyRetrieverConnection:
    """Test TavilyRetriever connection management."""
    
    async def test_connect_success(self, tavily_config):
        """Test successful connection to Tavily API."""
        retriever = TavilyRetriever(tavily_config)
        
        with patch.object(retriever, '_test_connection', new_callable=AsyncMock) as mock_test:
            mock_test.return_value = True
            
            await retriever.connect()
            
            assert retriever.connected
            mock_test.assert_called_once()
    
    async def test_connect_failure(self, tavily_config):
        """Test connection failure handling."""
        retriever = TavilyRetriever(tavily_config)
        
        with patch.object(retriever, '_test_connection', new_callable=AsyncMock) as mock_test:
            mock_test.side_effect = httpx.HTTPError("Connection failed")
            
            with pytest.raises(ConnectionError, match="Failed to connect to Tavily API"):
                await retriever.connect()
            
            assert not retriever.connected
    
    async def test_disconnect(self, tavily_config):
        """Test disconnection from Tavily API."""
        retriever = TavilyRetriever(tavily_config)
        retriever._connected = True
        
        # Create an AsyncMock for the client
        mock_client = AsyncMock()
        retriever._client = mock_client
        
        await retriever.disconnect()
        
        assert not retriever.connected
        assert retriever._client is None
        mock_client.aclose.assert_called_once()


@pytest.mark.asyncio
class TestTavilyRetrieverSearch:
    """Test TavilyRetriever search functionality."""
    
    async def test_retrieve_when_not_connected(self, tavily_config):
        """Test retrieve raises error when not connected."""
        retriever = TavilyRetriever(tavily_config)
        
        with pytest.raises(ConnectionError, match="Not connected to Tavily API"):
            async for _ in retriever.retrieve("test query"):
                pass
    
    async def test_retrieve_success(self, tavily_config, mock_tavily_response):
        """Test successful search retrieval."""
        retriever = TavilyRetriever(tavily_config)
        retriever._connected = True
        
        with patch.object(retriever, '_search', new_callable=AsyncMock) as mock_search:
            mock_search.return_value = mock_tavily_response
            
            results = []
            async for result in retriever.retrieve("test query", limit=2):
                results.append(result)
            
            assert len(results) == 2
            assert results[0]["title"] == "Test Result 1"
            assert results[0]["url"] == "https://example.com/1"
            assert results[0]["content"] == "This is test content 1"
            assert results[0]["score"] == 0.95
            
            mock_search.assert_called_once_with("test query", 2)
    
    async def test_retrieve_empty_results(self, tavily_config):
        """Test handling of empty search results."""
        retriever = TavilyRetriever(tavily_config)
        retriever._connected = True
        
        with patch.object(retriever, '_search', new_callable=AsyncMock) as mock_search:
            mock_search.return_value = {"results": []}
            
            results = []
            async for result in retriever.retrieve("test query"):
                results.append(result)
            
            assert len(results) == 0
    
    async def test_retrieve_api_error(self, tavily_config):
        """Test handling of API errors during search."""
        retriever = TavilyRetriever(tavily_config)
        retriever._connected = True
        
        with patch.object(retriever, '_search', new_callable=AsyncMock) as mock_search:
            mock_search.side_effect = httpx.HTTPError("API Error")
            
            with pytest.raises(QueryError, match="Search failed"):
                async for _ in retriever.retrieve("test query"):
                    pass
    
    async def test_retrieve_with_custom_limit(self, tavily_config, mock_tavily_response):
        """Test retrieve with custom result limit."""
        retriever = TavilyRetriever(tavily_config)
        retriever._connected = True
        
        # Mock response with more results
        extended_response = mock_tavily_response.copy()
        extended_response["results"] = mock_tavily_response["results"] * 5  # 10 results
        
        with patch.object(retriever, '_search', new_callable=AsyncMock) as mock_search:
            mock_search.return_value = extended_response
            
            results = []
            async for result in retriever.retrieve("test query", limit=5):
                results.append(result)
            
            assert len(results) == 5
            mock_search.assert_called_once_with("test query", 5)


@pytest.mark.asyncio
class TestTavilyRetrieverHealthCheck:
    """Test TavilyRetriever health check functionality."""
    
    async def test_health_check_when_connected(self, tavily_config):
        """Test health check when connected."""
        retriever = TavilyRetriever(tavily_config)
        retriever._connected = True
        
        with patch.object(retriever, '_test_connection', new_callable=AsyncMock) as mock_test:
            mock_test.return_value = True
            
            health = await retriever.health_check()
            
            assert health.healthy
            assert health.service_name == "TavilyRetriever"
            assert health.details["connected"] is True
            assert health.error is None
    
    async def test_health_check_when_disconnected(self, tavily_config):
        """Test health check when disconnected."""
        retriever = TavilyRetriever(tavily_config)
        retriever._connected = False
        
        health = await retriever.health_check()
        
        assert not health.healthy
        assert health.service_name == "TavilyRetriever"
        assert health.details["connected"] is False
        assert health.error == "Not connected"
    
    async def test_health_check_with_api_error(self, tavily_config):
        """Test health check when API test fails."""
        retriever = TavilyRetriever(tavily_config)
        retriever._connected = True
        
        with patch.object(retriever, '_test_connection', new_callable=AsyncMock) as mock_test:
            mock_test.side_effect = Exception("API Error")
            
            health = await retriever.health_check()
            
            assert not health.healthy
            assert health.service_name == "TavilyRetriever"
            assert "API Error" in health.error


@pytest.mark.asyncio
class TestTavilyRetrieverIntegration:
    """Test TavilyRetriever integration scenarios."""
    
    async def test_context_manager_usage(self, tavily_config, mock_tavily_response):
        """Test using retriever as async context manager."""
        with patch('src.retrievers.tavily.TavilyRetriever._test_connection', new_callable=AsyncMock):
            with patch('src.retrievers.tavily.TavilyRetriever._search', new_callable=AsyncMock) as mock_search:
                mock_search.return_value = mock_tavily_response
                
                async with TavilyRetriever(tavily_config) as retriever:
                    assert retriever.connected
                    
                    results = []
                    async for result in retriever.retrieve("test query", limit=1):
                        results.append(result)
                    
                    assert len(results) == 1
                
                # After exiting context, should be disconnected
                assert not retriever.connected
    
    async def test_retry_on_rate_limit(self, tavily_config):
        """Test retry logic on rate limit errors."""
        retriever = TavilyRetriever(tavily_config)
        retriever._connected = True
        
        # Create a mock client
        mock_client = AsyncMock()
        retriever._client = mock_client
        
        # Mock rate limit response
        rate_limit_response = httpx.Response(
            status_code=429,
            headers={"Retry-After": "1"}
        )
        
        with patch.object(retriever._client, 'post', new_callable=AsyncMock) as mock_post:
            # First call returns rate limit, second succeeds
            mock_post.side_effect = [
                httpx.HTTPStatusError("Rate limited", request=Mock(), response=rate_limit_response),
                Mock(json=Mock(return_value={"results": [{"title": "Success"}]}))
            ]
            
            results = []
            async for result in retriever.retrieve("test query", limit=1):
                results.append(result)
            
            assert len(results) == 1
            assert results[0]["title"] == "Success"
            assert mock_post.call_count == 2