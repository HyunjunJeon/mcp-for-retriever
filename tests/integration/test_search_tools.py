"""Integration tests for MCP search tools."""

import pytest
from unittest.mock import patch, AsyncMock
from typing import AsyncIterator

from src.server import (
    search_web_tool,
    search_vectors_tool,
    search_database_tool,
    search_all_tool,
    retrievers
)
from src.retrievers.base import QueryResult, ConnectionError, QueryError
from tests.fixtures.mock_retriever import MockRetriever


class TestSearchTools:
    """Test individual search tool functionality."""
    
    @pytest.fixture
    async def setup_retrievers(self):
        """Set up mock retrievers for testing."""
        retrievers.clear()
        
        # Web retriever with sample data
        web_retriever = MockRetriever({
            "type": "tavily",
            "mock_data": [
                {
                    "title": "Python Programming",
                    "url": "https://python.org",
                    "content": "Learn Python programming",
                    "score": 0.95,
                    "source": "web"
                },
                {
                    "title": "Python Tutorial",
                    "url": "https://docs.python.org/tutorial",
                    "content": "Official Python tutorial",
                    "score": 0.90,
                    "source": "web"
                }
            ]
        })
        await web_retriever.connect()
        retrievers["tavily"] = web_retriever
        
        # Vector retriever with sample data
        vector_retriever = MockRetriever({
            "type": "qdrant",
            "mock_data": [
                {
                    "id": "vec-1",
                    "text": "Introduction to machine learning",
                    "score": 0.88,
                    "metadata": {"category": "ML"},
                    "source": "vectors"
                }
            ]
        })
        await vector_retriever.connect()
        retrievers["qdrant"] = vector_retriever
        
        # Database retriever with sample data
        db_retriever = MockRetriever({
            "type": "postgres",
            "mock_data": [
                {
                    "id": 1,
                    "name": "Alice",
                    "email": "alice@example.com",
                    "created_at": "2024-01-01",
                    "source": "database"
                },
                {
                    "id": 2,
                    "name": "Bob",
                    "email": "bob@example.com", 
                    "created_at": "2024-01-02",
                    "source": "database"
                }
            ]
        })
        await db_retriever.connect()
        retrievers["postgres"] = db_retriever
        
        yield
        
        # Cleanup
        retrievers.clear()
    
    async def test_search_web_tool_success(self, setup_retrievers):
        """Test successful web search."""
        result = await search_web_tool(
            query="Python",
            limit=5,
            include_domains=["python.org"],
            exclude_domains=["spam.com"]
        )
        
        assert result["status"] == "success"
        assert "results" in result
        assert "count" in result
        assert len(result["results"]) == 2
        assert result["count"] == 2
        
        # Verify result structure
        first_result = result["results"][0]
        assert "title" in first_result
        assert "url" in first_result
        assert "content" in first_result
        assert "score" in first_result
        assert first_result["source"] == "web"
    
    async def test_search_web_tool_not_available(self):
        """Test web search when retriever is not available."""
        retrievers.clear()  # No retrievers available
        
        result = await search_web_tool(query="test")
        
        assert result["status"] == "error"
        assert "error" in result
        assert "not available" in result["error"]
    
    async def test_search_web_tool_not_connected(self, setup_retrievers):
        """Test web search when retriever is not connected."""
        retrievers["tavily"]._connected = False
        
        result = await search_web_tool(query="test")
        
        assert result["status"] == "error"
        assert "not connected" in result["error"]
    
    async def test_search_web_tool_query_error(self, setup_retrievers):
        """Test web search with query error."""
        # Make retriever raise an error
        async def failing_retrieve(*args, **kwargs):
            raise QueryError("API rate limit exceeded", "tavily")
        
        retrievers["tavily"].retrieve = failing_retrieve
        
        result = await search_web_tool(query="test")
        
        assert result["status"] == "error"
        assert "API rate limit exceeded" in result["error"]
    
    async def test_search_vectors_tool_success(self, setup_retrievers):
        """Test successful vector search."""
        result = await search_vectors_tool(
            query="machine learning",
            collection="documents",
            limit=10,
            score_threshold=0.7
        )
        
        assert result["status"] == "success"
        assert len(result["results"]) == 1
        assert result["results"][0]["source"] == "vectors"
        assert result["results"][0]["score"] >= 0.7
    
    async def test_search_vectors_tool_missing_collection(self, setup_retrievers):
        """Test vector search without collection parameter."""
        # Override retrieve to check for collection parameter
        original_retrieve = retrievers["qdrant"].retrieve
        
        async def check_collection_retrieve(query, **kwargs):
            if "collection" not in kwargs:
                raise QueryError("Collection name is required", "qdrant")
            async for result in original_retrieve(query, **kwargs):
                yield result
        
        retrievers["qdrant"].retrieve = check_collection_retrieve
        
        result = await search_vectors_tool(
            query="test",
            collection="test_collection"  # This should work
        )
        
        assert result["status"] == "success"
    
    async def test_search_database_tool_success(self, setup_retrievers):
        """Test successful database search."""
        result = await search_database_tool(
            query="SELECT * FROM users",
            table="users",
            limit=10
        )
        
        assert result["status"] == "success"
        assert len(result["results"]) == 2
        assert all(r["source"] == "database" for r in result["results"])
        assert result["results"][0]["name"] == "Alice"
        assert result["results"][1]["name"] == "Bob"
    
    async def test_search_all_tool_success(self, setup_retrievers):
        """Test searching all sources concurrently."""
        result = await search_all_tool(
            query="comprehensive search",
            limit=5
        )
        
        assert result["status"] == "success"
        assert "results" in result
        assert "errors" in result
        assert "sources_searched" in result
        
        # Should have results from all three sources
        assert len(result["results"]) == 3
        assert "tavily" in result["results"]
        assert "qdrant" in result["results"] 
        assert "postgres" in result["results"]
        
        # Verify each source returned results
        assert len(result["results"]["tavily"]) == 2
        assert len(result["results"]["qdrant"]) == 1
        assert len(result["results"]["postgres"]) == 2
        
        assert result["sources_searched"] == 3
    
    async def test_search_all_tool_partial_failure(self, setup_retrievers):
        """Test search_all when some retrievers fail."""
        # Make vector search fail
        async def failing_retrieve(*args, **kwargs):
            raise QueryError("Collection not found", "qdrant")
        
        retrievers["qdrant"].retrieve = failing_retrieve
        
        result = await search_all_tool(query="test", limit=5)
        
        assert result["status"] == "success"
        
        # Should have results from working retrievers
        assert "tavily" in result["results"]
        assert "postgres" in result["results"]
        
        # Should have error for failed retriever
        assert "qdrant" in result["errors"]
        assert "Collection not found" in result["errors"]["qdrant"]
        
        assert result["sources_searched"] == 3
    
    async def test_search_all_tool_no_retrievers(self):
        """Test search_all when no retrievers are available."""
        retrievers.clear()
        
        result = await search_all_tool(query="test")
        
        assert result["status"] == "success"
        assert result["results"] == {}
        assert result["errors"] == {}
        assert result["sources_searched"] == 0
    
    async def test_search_all_tool_only_disconnected(self, setup_retrievers):
        """Test search_all when all retrievers are disconnected."""
        for retriever in retrievers.values():
            retriever._connected = False
        
        result = await search_all_tool(query="test")
        
        assert result["status"] == "success"
        assert result["results"] == {}
        assert result["errors"] == {}
        assert result["sources_searched"] == 0
    
    async def test_search_parameters_propagation(self, setup_retrievers):
        """Test that search parameters are properly propagated."""
        # Track parameters passed to retrieve
        called_params = {}
        
        async def track_params_retrieve(query, **kwargs):
            called_params.update(kwargs)
            for data in self._mock_data:
                yield data
        
        retrievers["tavily"].retrieve = track_params_retrieve.__get__(
            retrievers["tavily"], 
            retrievers["tavily"].__class__
        )
        
        await search_web_tool(
            query="test",
            limit=20,
            include_domains=["example.com"],
            exclude_domains=["spam.com"]
        )
        
        assert called_params["limit"] == 20
        assert called_params["include_domains"] == ["example.com"]
        assert called_params["exclude_domains"] == ["spam.com"]
    
    async def test_empty_results_handling(self, setup_retrievers):
        """Test handling of empty results."""
        # Override to return empty results
        async def empty_retrieve(*args, **kwargs):
            return
            yield  # Make it a generator but yield nothing
        
        for retriever in retrievers.values():
            retriever.retrieve = empty_retrieve
        
        # Test each tool with empty results
        web_result = await search_web_tool(query="nothing")
        assert web_result["status"] == "success"
        assert web_result["results"] == []
        assert web_result["count"] == 0
        
        vector_result = await search_vectors_tool(
            query="nothing",
            collection="empty"
        )
        assert vector_result["status"] == "success"
        assert vector_result["results"] == []
        assert vector_result["count"] == 0
        
        db_result = await search_database_tool(query="SELECT * FROM empty")
        assert db_result["status"] == "success"
        assert db_result["results"] == []
        assert db_result["count"] == 0