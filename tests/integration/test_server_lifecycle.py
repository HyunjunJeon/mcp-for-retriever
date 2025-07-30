"""Integration tests for MCP server lifecycle management."""

import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
import pytest

from src.server import create_server, startup, shutdown, retrievers
from src.retrievers.base import RetrieverConfig, ConnectionError
from tests.fixtures.mock_retriever import MockRetriever


class TestServerLifecycle:
    """Test server startup and shutdown processes."""
    
    @pytest.fixture
    def mock_factory(self):
        """Create mock factory with retrievers."""
        factory = MagicMock()
        
        # Create mock retrievers
        tavily_mock = MockRetriever({"type": "tavily"})
        postgres_mock = MockRetriever({"type": "postgres"})
        qdrant_mock = MockRetriever({"type": "qdrant"})
        
        def create_mock(config: RetrieverConfig):
            retriever_type = config.get("type")
            if retriever_type == "tavily":
                return tavily_mock
            elif retriever_type == "postgres":
                return postgres_mock
            elif retriever_type == "qdrant":
                return qdrant_mock
            raise ValueError(f"Unknown type: {retriever_type}")
        
        factory.create.side_effect = create_mock
        return factory
    
    async def test_server_startup_success(self, mock_factory):
        """Test successful server startup with all retrievers."""
        retrievers.clear()  # Clear any existing retrievers
        
        with patch('src.server.factory', mock_factory):
            with patch.dict('os.environ', {
                'TAVILY_API_KEY': 'test-key',
                'POSTGRES_DSN': 'postgresql://test:pass@localhost/db',
                'QDRANT_HOST': 'localhost'
            }):
                await startup()
                
                # Verify all retrievers were initialized
                assert len(retrievers) == 3
                assert "tavily" in retrievers
                assert "postgres" in retrievers
                assert "qdrant" in retrievers
                
                # Verify all are connected
                assert all(r.connected for r in retrievers.values())
    
    async def test_server_startup_partial_failure(self, mock_factory):
        """Test server startup when some retrievers fail to connect."""
        retrievers.clear()
        
        # Make postgres fail to connect
        postgres_mock = MockRetriever({
            "type": "postgres",
            "fail_on_connect": True
        })
        
        def create_mock(config: RetrieverConfig):
            retriever_type = config.get("type")
            if retriever_type == "postgres":
                return postgres_mock
            return MockRetriever(config)
        
        mock_factory.create.side_effect = create_mock
        
        with patch('src.server.factory', mock_factory):
            await startup()
            
            # Only tavily and qdrant should be initialized
            assert len(retrievers) == 2
            assert "tavily" in retrievers
            assert "qdrant" in retrievers
            assert "postgres" not in retrievers
    
    async def test_server_shutdown(self, mock_factory):
        """Test server shutdown process."""
        retrievers.clear()
        
        # Setup retrievers
        with patch('src.server.factory', mock_factory):
            await startup()
            initial_count = len(retrievers)
            assert initial_count > 0
            
            # All should be connected
            assert all(r.connected for r in retrievers.values())
            
            # Shutdown
            await shutdown()
            
            # All retrievers should be disconnected and cleared
            assert len(retrievers) == 0
    
    async def test_server_shutdown_with_errors(self, mock_factory):
        """Test server shutdown when disconnection fails."""
        retrievers.clear()
        
        # Create a retriever that fails on disconnect
        failing_mock = MockRetriever({"type": "failing"})
        failing_mock.disconnect = AsyncMock(side_effect=Exception("Disconnect failed"))
        
        retrievers["failing"] = failing_mock
        retrievers["normal"] = MockRetriever({"type": "normal"})
        
        # Ensure both are connected
        await retrievers["failing"].connect()
        await retrievers["normal"].connect()
        
        # Shutdown should handle errors gracefully
        await shutdown()
        
        # Retrievers should still be cleared
        assert len(retrievers) == 0
    
    async def test_lifespan_context_manager(self, mock_factory):
        """Test the lifespan context manager."""
        from src.server import lifespan
        
        retrievers.clear()
        server = create_server()
        
        with patch('src.server.factory', mock_factory):
            async with lifespan(server):
                # Retrievers should be initialized
                assert len(retrievers) > 0
                assert all(r.connected for r in retrievers.values())
            
            # After exiting, retrievers should be cleaned up
            assert len(retrievers) == 0
    
    async def test_server_creation(self):
        """Test server creation and tool registration."""
        server = create_server()
        
        # Verify server properties
        assert server.name == "mcp-retriever"
        
        # Verify tools are registered
        # Note: FastMCP doesn't expose registered tools directly,
        # so we'll test by checking the tool functions are callable
        from src.server import (
            search_web_tool,
            search_vectors_tool, 
            search_database_tool,
            search_all_tool
        )
        
        assert callable(search_web_tool)
        assert callable(search_vectors_tool)
        assert callable(search_database_tool)
        assert callable(search_all_tool)
    
    async def test_health_check_after_startup(self, mock_factory):
        """Test health checks work after startup."""
        retrievers.clear()
        
        with patch('src.server.factory', mock_factory):
            await startup()
            
            # Check health of each retriever
            for name, retriever in retrievers.items():
                health = await retriever.health_check()
                assert health.healthy
                assert health.service_name in ["MockRetriever", name]
    
    async def test_concurrent_startup_requests(self, mock_factory):
        """Test handling concurrent startup attempts."""
        retrievers.clear()
        
        with patch('src.server.factory', mock_factory):
            # Start multiple startup tasks concurrently
            tasks = [startup() for _ in range(5)]
            await asyncio.gather(*tasks)
            
            # Should still only have 3 retrievers (no duplicates)
            assert len(retrievers) == 3
            assert set(retrievers.keys()) == {"tavily", "postgres", "qdrant"}