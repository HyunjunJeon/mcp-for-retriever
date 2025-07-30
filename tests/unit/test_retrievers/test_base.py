"""Unit tests for base retriever interface."""

import pytest
from datetime import datetime

from src.retrievers.base import (
    Retriever,
    RetrieverHealth,
    RetrieverError,
    ConnectionError,
    QueryError,
)
from tests.fixtures.mock_retriever import MockRetriever


class TestRetrieverHealth:
    """Test RetrieverHealth model."""
    
    def test_health_model_creation(self):
        """Test creating a health status model."""
        health = RetrieverHealth(
            healthy=True,
            service_name="test_service"
        )
        
        assert health.healthy is True
        assert health.service_name == "test_service"
        assert health.details is None
        assert health.error is None
        assert isinstance(health.checked_at, datetime)
    
    def test_health_model_with_details(self):
        """Test health model with additional details."""
        details = {"connections": 5, "latency_ms": 23}
        health = RetrieverHealth(
            healthy=True,
            service_name="test_service",
            details=details
        )
        
        assert health.details == details
    
    def test_unhealthy_status_with_error(self):
        """Test unhealthy status with error message."""
        health = RetrieverHealth(
            healthy=False,
            service_name="test_service",
            error="Connection timeout"
        )
        
        assert health.healthy is False
        assert health.error == "Connection timeout"


class TestRetrieverErrors:
    """Test custom exception classes."""
    
    def test_retriever_error_basic(self):
        """Test basic RetrieverError creation."""
        error = RetrieverError("Test error", "TestRetriever")
        
        assert str(error) == "Test error"
        assert error.retriever_name == "TestRetriever"
        assert error.details == {}
    
    def test_retriever_error_with_details(self):
        """Test RetrieverError with details."""
        details = {"code": 500, "context": "server error"}
        error = RetrieverError("Test error", "TestRetriever", details)
        
        assert error.details == details
    
    def test_connection_error(self):
        """Test ConnectionError subclass."""
        error = ConnectionError("Failed to connect", "TestRetriever")
        
        assert isinstance(error, RetrieverError)
        assert str(error) == "Failed to connect"
    
    def test_query_error(self):
        """Test QueryError subclass."""
        error = QueryError("Invalid query", "TestRetriever")
        
        assert isinstance(error, RetrieverError)
        assert str(error) == "Invalid query"


class TestRetrieverAbstractClass:
    """Test Retriever abstract base class behavior."""
    
    def test_cannot_instantiate_abstract_class(self):
        """Test that Retriever ABC cannot be instantiated directly."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            Retriever({})
    
    def test_subclass_must_implement_all_methods(self):
        """Test that subclasses must implement all abstract methods."""
        
        class IncompleteRetriever(Retriever):
            """Retriever missing some implementations."""
            async def connect(self): pass
            async def disconnect(self): pass
            # Missing retrieve() and health_check()
        
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteRetriever({})


@pytest.mark.asyncio
class TestMockRetrieverImplementation:
    """Test the mock retriever implementation."""
    
    async def test_basic_initialization(self):
        """Test basic retriever initialization."""
        config = {"test": "value"}
        retriever = MockRetriever(config)
        
        assert retriever.config == config
        assert retriever.connected is False
        assert retriever.connect_called is False
        assert retriever.disconnect_called is False
    
    async def test_connect_disconnect(self):
        """Test connection and disconnection."""
        retriever = MockRetriever({})
        
        # Initially not connected
        assert retriever.connected is False
        
        # Connect
        await retriever.connect()
        assert retriever.connected is True
        assert retriever.connect_called is True
        
        # Disconnect
        await retriever.disconnect()
        assert retriever.connected is False
        assert retriever.disconnect_called is True
    
    async def test_context_manager(self):
        """Test async context manager functionality."""
        retriever = MockRetriever({})
        
        async with retriever as r:
            assert r is retriever
            assert r.connected is True
            assert r.connect_called is True
        
        # After exiting context, should be disconnected
        assert retriever.connected is False
        assert retriever.disconnect_called is True
    
    async def test_retrieve_when_not_connected(self):
        """Test retrieve raises error when not connected."""
        retriever = MockRetriever({})
        
        with pytest.raises(ConnectionError, match="Not connected"):
            async for _ in retriever.retrieve("test query"):
                pass
    
    async def test_retrieve_with_mock_data(self):
        """Test retrieve returns mock data."""
        mock_data = [
            {"id": 1, "content": "Result 1"},
            {"id": 2, "content": "Result 2"},
            {"id": 3, "content": "Result 3"}
        ]
        
        retriever = MockRetriever({"mock_data": mock_data})
        await retriever.connect()
        
        results = []
        async for result in retriever.retrieve("test query", limit=2):
            results.append(result)
        
        assert len(results) == 2
        assert results[0] == mock_data[0]
        assert results[1] == mock_data[1]
    
    async def test_health_check(self):
        """Test health check functionality."""
        retriever = MockRetriever({})
        
        # Check when disconnected
        health = await retriever.health_check()
        assert health.healthy is False
        assert health.service_name == "MockRetriever"
        
        # Check when connected
        await retriever.connect()
        health = await retriever.health_check()
        assert health.healthy is True
        assert health.details == {"mock": True}
    
    async def test_connection_failure(self):
        """Test handling connection failures."""
        retriever = MockRetriever({"fail_connection": True})
        
        with pytest.raises(ConnectionError, match="Mock connection failed"):
            await retriever.connect()
        
        assert retriever.connected is False
    
    async def test_query_failure(self):
        """Test handling query failures."""
        retriever = MockRetriever({"fail_query": True})
        await retriever.connect()
        
        with pytest.raises(QueryError, match="Mock query failed"):
            async for _ in retriever.retrieve("test query"):
                pass
    
    async def test_context_manager_with_exception(self):
        """Test context manager handles exceptions properly."""
        retriever = MockRetriever({"fail_query": True})
        
        with pytest.raises(QueryError):
            async with retriever as r:
                async for _ in r.retrieve("test query"):
                    pass
        
        # Should still disconnect even if exception occurred
        assert retriever.disconnect_called is True
        assert retriever.connected is False