"""Unit tests for Qdrant vector database retriever."""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from qdrant_client.models import Distance, VectorParams, PointStruct
import numpy as np

from src.retrievers.qdrant import QdrantRetriever
from src.retrievers.base import (
    RetrieverHealth,
    ConnectionError,
    QueryError,
)


@pytest.fixture
def qdrant_config():
    """Fixture for QdrantRetriever configuration."""
    return {
        "host": "localhost",
        "port": 6333,
        "api_key": "test-api-key",
        "timeout": 30,
        "embedding_model": "text-embedding-ada-002",
        "embedding_dim": 1536,
    }


@pytest.fixture
def mock_qdrant_client():
    """Mock Qdrant client."""
    client = AsyncMock()
    client.get_collections = AsyncMock()
    client.create_collection = AsyncMock()
    client.search = AsyncMock()
    client.upsert = AsyncMock()
    client.delete = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_embeddings():
    """Mock embeddings function."""
    async def _mock_embed(text: str) -> list[float]:
        # Return a fixed embedding vector
        return [0.1] * 1536
    
    return _mock_embed


class TestQdrantRetrieverConfiguration:
    """Test QdrantRetriever configuration and initialization."""
    
    def test_initialization_with_config(self, qdrant_config):
        """Test retriever initialization with configuration."""
        retriever = QdrantRetriever(qdrant_config)
        
        assert retriever.config == qdrant_config
        assert retriever.host == "localhost"
        assert retriever.port == 6333
        assert retriever.api_key == "test-api-key"
        assert retriever.timeout == 30
        assert retriever.embedding_model == "text-embedding-ada-002"
        assert retriever.embedding_dim == 1536
        assert not retriever.connected
    
    def test_initialization_without_host(self):
        """Test retriever initialization fails without host."""
        with pytest.raises(ValueError, match="host is required"):
            QdrantRetriever({})
    
    def test_initialization_with_defaults(self):
        """Test retriever initialization with default values."""
        config = {"host": "localhost"}
        retriever = QdrantRetriever(config)
        
        assert retriever.host == "localhost"
        assert retriever.port == 6333  # default
        assert retriever.api_key is None  # optional
        assert retriever.timeout == 30  # default
        assert retriever.embedding_model == "text-embedding-ada-002"  # default
        assert retriever.embedding_dim == 1536  # default


@pytest.mark.asyncio
class TestQdrantRetrieverConnection:
    """Test QdrantRetriever connection management."""
    
    async def test_connect_success(self, qdrant_config, mock_qdrant_client):
        """Test successful connection to Qdrant."""
        retriever = QdrantRetriever(qdrant_config)
        
        with patch('src.retrievers.qdrant.QdrantClient', return_value=mock_qdrant_client):
            await retriever.connect()
            
            assert retriever.connected
            mock_qdrant_client.get_collections.assert_called_once()
    
    async def test_connect_failure(self, qdrant_config):
        """Test connection failure handling."""
        retriever = QdrantRetriever(qdrant_config)
        
        with patch('src.retrievers.qdrant.QdrantClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get_collections.side_effect = Exception("Connection failed")
            mock_client_class.return_value = mock_client
            
            with pytest.raises(ConnectionError, match="Failed to connect to Qdrant"):
                await retriever.connect()
            
            assert not retriever.connected
    
    async def test_disconnect(self, qdrant_config, mock_qdrant_client):
        """Test disconnection from Qdrant."""
        retriever = QdrantRetriever(qdrant_config)
        retriever._client = mock_qdrant_client
        retriever._connected = True
        
        await retriever.disconnect()
        
        assert not retriever.connected
        assert retriever._client is None
        mock_qdrant_client.close.assert_called_once()


@pytest.mark.asyncio
class TestQdrantRetrieverSearch:
    """Test QdrantRetriever search functionality."""
    
    async def test_retrieve_when_not_connected(self, qdrant_config):
        """Test retrieve raises error when not connected."""
        retriever = QdrantRetriever(qdrant_config)
        
        with pytest.raises(ConnectionError, match="Not connected to Qdrant"):
            async for _ in retriever.retrieve("test query"):
                pass
    
    async def test_retrieve_vector_search(self, qdrant_config, mock_qdrant_client, mock_embeddings):
        """Test vector similarity search."""
        retriever = QdrantRetriever(qdrant_config)
        retriever._client = mock_qdrant_client
        retriever._connected = True
        retriever._embed_text = mock_embeddings
        
        # Mock search results
        mock_results = [
            Mock(
                id=1,
                score=0.95,
                payload={
                    "text": "Python programming guide",
                    "title": "Python Guide",
                    "metadata": {"author": "John Doe"}
                }
            ),
            Mock(
                id=2,
                score=0.87,
                payload={
                    "text": "Python tutorial for beginners",
                    "title": "Python Tutorial",
                    "metadata": {"author": "Jane Smith"}
                }
            )
        ]
        mock_qdrant_client.search.return_value = mock_results
        
        results = []
        async for result in retriever.retrieve(
            "Python programming",
            collection="documents",
            limit=5
        ):
            results.append(result)
        
        assert len(results) == 2
        assert results[0]["title"] == "Python Guide"
        assert results[0]["score"] == 0.95
        assert results[1]["title"] == "Python Tutorial"
        
        # Verify search was called with correct parameters
        mock_qdrant_client.search.assert_called_once()
        call_args = mock_qdrant_client.search.call_args
        assert call_args.kwargs["collection_name"] == "documents"
        assert call_args.kwargs["limit"] == 5
    
    async def test_retrieve_with_score_threshold(self, qdrant_config, mock_qdrant_client, mock_embeddings):
        """Test search with score threshold filtering."""
        retriever = QdrantRetriever(qdrant_config)
        retriever._client = mock_qdrant_client
        retriever._connected = True
        retriever._embed_text = mock_embeddings
        
        # Mock results with varying scores
        mock_results = [
            Mock(id=1, score=0.95, payload={"text": "High score"}),
            Mock(id=2, score=0.65, payload={"text": "Low score"}),
            Mock(id=3, score=0.85, payload={"text": "Medium score"})
        ]
        mock_qdrant_client.search.return_value = mock_results
        
        results = []
        async for result in retriever.retrieve(
            "test query",
            collection="test",
            score_threshold=0.8
        ):
            results.append(result)
        
        # Should only return results with score >= 0.8
        assert len(results) == 2
        assert all(r["score"] >= 0.8 for r in results)
    
    async def test_retrieve_empty_results(self, qdrant_config, mock_qdrant_client, mock_embeddings):
        """Test handling of empty search results."""
        retriever = QdrantRetriever(qdrant_config)
        retriever._client = mock_qdrant_client
        retriever._connected = True
        retriever._embed_text = mock_embeddings
        
        mock_qdrant_client.search.return_value = []
        
        results = []
        async for result in retriever.retrieve("no matches", collection="test"):
            results.append(result)
        
        assert len(results) == 0
    
    async def test_retrieve_query_error(self, qdrant_config, mock_qdrant_client, mock_embeddings):
        """Test handling of search errors."""
        retriever = QdrantRetriever(qdrant_config)
        retriever._client = mock_qdrant_client
        retriever._connected = True
        retriever._embed_text = mock_embeddings
        
        mock_qdrant_client.search.side_effect = Exception("Search failed")
        
        with pytest.raises(QueryError, match="Search failed"):
            async for _ in retriever.retrieve("test", collection="test"):
                pass


@pytest.mark.asyncio
class TestQdrantRetrieverHealthCheck:
    """Test QdrantRetriever health check functionality."""
    
    async def test_health_check_when_connected(self, qdrant_config, mock_qdrant_client):
        """Test health check when connected."""
        retriever = QdrantRetriever(qdrant_config)
        retriever._client = mock_qdrant_client
        retriever._connected = True
        
        # Mock collections info
        mock_collections = Mock()
        mock_collections.collections = [
            Mock(name="collection1"),
            Mock(name="collection2")
        ]
        mock_qdrant_client.get_collections.return_value = mock_collections
        
        health = await retriever.health_check()
        
        assert health.healthy
        assert health.service_name == "QdrantRetriever"
        assert health.details["connected"] is True
        assert health.details["collections_count"] == 2
        assert health.error is None
    
    async def test_health_check_when_disconnected(self, qdrant_config):
        """Test health check when disconnected."""
        retriever = QdrantRetriever(qdrant_config)
        retriever._connected = False
        
        health = await retriever.health_check()
        
        assert not health.healthy
        assert health.service_name == "QdrantRetriever"
        assert health.details["connected"] is False
        assert health.error == "Not connected"
    
    async def test_health_check_with_error(self, qdrant_config, mock_qdrant_client):
        """Test health check when query fails."""
        retriever = QdrantRetriever(qdrant_config)
        retriever._client = mock_qdrant_client
        retriever._connected = True
        
        mock_qdrant_client.get_collections.side_effect = Exception("Connection lost")
        
        health = await retriever.health_check()
        
        assert not health.healthy
        assert health.service_name == "QdrantRetriever"
        assert "Connection lost" in health.error


@pytest.mark.asyncio
class TestQdrantRetrieverOperations:
    """Test additional Qdrant operations."""
    
    async def test_create_collection(self, qdrant_config, mock_qdrant_client):
        """Test creating a new collection."""
        retriever = QdrantRetriever(qdrant_config)
        retriever._client = mock_qdrant_client
        retriever._connected = True
        
        await retriever.create_collection(
            "new_collection",
            vector_size=768,
            distance=Distance.COSINE
        )
        
        mock_qdrant_client.create_collection.assert_called_once()
        call_args = mock_qdrant_client.create_collection.call_args
        assert call_args.kwargs["collection_name"] == "new_collection"
        assert call_args.kwargs["vectors_config"].size == 768
        assert call_args.kwargs["vectors_config"].distance == Distance.COSINE
    
    async def test_upsert_vectors(self, qdrant_config, mock_qdrant_client, mock_embeddings):
        """Test inserting/updating vectors."""
        retriever = QdrantRetriever(qdrant_config)
        retriever._client = mock_qdrant_client
        retriever._connected = True
        retriever._embed_text = mock_embeddings
        
        documents = [
            {"id": "1", "text": "Document 1", "metadata": {"type": "article"}},
            {"id": "2", "text": "Document 2", "metadata": {"type": "blog"}}
        ]
        
        await retriever.upsert(
            collection="documents",
            documents=documents
        )
        
        mock_qdrant_client.upsert.assert_called_once()
        call_args = mock_qdrant_client.upsert.call_args
        assert call_args.kwargs["collection_name"] == "documents"
        assert len(call_args.kwargs["points"]) == 2
    
    async def test_delete_vectors(self, qdrant_config, mock_qdrant_client):
        """Test deleting vectors."""
        retriever = QdrantRetriever(qdrant_config)
        retriever._client = mock_qdrant_client
        retriever._connected = True
        
        await retriever.delete(
            collection="documents",
            ids=["1", "2", "3"]
        )
        
        mock_qdrant_client.delete.assert_called_once_with(
            collection_name="documents",
            points_selector=["1", "2", "3"]
        )
    
    async def test_context_manager_usage(self, qdrant_config, mock_qdrant_client):
        """Test using retriever as async context manager."""
        with patch('src.retrievers.qdrant.QdrantClient', return_value=mock_qdrant_client):
            async with QdrantRetriever(qdrant_config) as retriever:
                assert retriever.connected
            
            # After exiting context, should be disconnected
            assert not retriever.connected