"""Unit tests for connection pool manager."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import time

from src.utils.connection_manager import (
    ConnectionManager,
    PostgreSQLPoolManager,
    QdrantClientManager,
    HTTPSessionManager,
    ConnectionPoolMetrics,
)


class TestConnectionPoolMetrics:
    """Test connection pool metrics tracking."""

    def test_metrics_initialization(self):
        """Test metrics are properly initialized."""
        metrics = ConnectionPoolMetrics()

        assert metrics.total_connections == 0
        assert metrics.active_connections == 0
        assert metrics.idle_connections == 0
        assert metrics.connection_errors == 0
        assert metrics.total_requests == 0
        assert metrics.pool_exhausted_count == 0
        assert metrics.connection_wait_time_ms == []
        assert metrics.reuse_rate == 0.0

    def test_record_connection_acquired(self):
        """Test recording connection acquisition."""
        metrics = ConnectionPoolMetrics()

        # Record acquisition with no wait
        metrics.record_connection_acquired(wait_time_ms=0)
        assert metrics.active_connections == 1
        assert metrics.total_requests == 1
        assert metrics.connection_wait_time_ms == [0]

        # Record acquisition with wait
        metrics.record_connection_acquired(wait_time_ms=50)
        assert metrics.active_connections == 2
        assert metrics.total_requests == 2
        assert metrics.connection_wait_time_ms == [0, 50]

    def test_record_connection_released(self):
        """Test recording connection release."""
        metrics = ConnectionPoolMetrics()

        # Setup initial state
        metrics.active_connections = 5
        metrics.total_connections = 10

        metrics.record_connection_released()
        assert metrics.active_connections == 4
        assert metrics.idle_connections == 6

    def test_calculate_reuse_rate(self):
        """Test connection reuse rate calculation."""
        metrics = ConnectionPoolMetrics()

        # No requests yet
        assert metrics.calculate_reuse_rate() == 0.0

        # 100 requests with 10 connections created
        metrics.total_requests = 100
        metrics.total_connections = 10
        assert metrics.calculate_reuse_rate() == 90.0  # 90% reuse rate

        # Edge case: more connections than requests
        metrics.total_connections = 150
        assert metrics.calculate_reuse_rate() == 0.0


class TestPostgreSQLPoolManager:
    """Test PostgreSQL connection pool manager."""

    @pytest.fixture
    def pool_config(self):
        """Default pool configuration."""
        return {
            "dsn": "postgresql://test:test@localhost:5432/test",
            "min_size": 10,
            "max_size": 50,
            "timeout": 30,
            "command_timeout": 10,
            "max_queries": 50000,
            "max_inactive_connection_lifetime": 300,
        }

    @pytest.mark.asyncio
    async def test_pool_creation(self, pool_config):
        """Test PostgreSQL pool creation with optimized settings."""
        manager = PostgreSQLPoolManager(pool_config)

        mock_pool = AsyncMock()
        mock_pool.get_size.return_value = 10
        mock_pool.get_idle_size.return_value = 10

        with patch(
            "asyncpg.create_pool", AsyncMock(return_value=mock_pool)
        ) as mock_create:
            await manager.initialize()

            # Verify pool creation parameters
            mock_create.assert_called_once_with(
                pool_config["dsn"],
                min_size=10,
                max_size=50,
                timeout=30,
                command_timeout=10,
                max_queries=50000,
                max_inactive_connection_lifetime=300,
            )

            assert manager._pool == mock_pool
            assert manager.metrics.total_connections == 10

    @pytest.mark.asyncio
    async def test_dynamic_pool_adjustment(self, pool_config):
        """Test dynamic pool size adjustment based on load."""
        manager = PostgreSQLPoolManager(pool_config)

        mock_pool = AsyncMock()
        mock_pool.get_size.return_value = 10
        mock_pool.get_idle_size.return_value = 2
        mock_pool.set_pool_size = AsyncMock()

        manager._pool = mock_pool

        # Simulate high load (80% utilization)
        manager.metrics.active_connections = 8
        manager.metrics.total_connections = 10

        await manager.adjust_pool_size()

        # Should increase pool size
        mock_pool.set_pool_size.assert_called_with(min_size=15, max_size=50)

    @pytest.mark.asyncio
    async def test_connection_acquisition_with_metrics(self, pool_config):
        """Test connection acquisition with metric tracking."""
        manager = PostgreSQLPoolManager(pool_config)

        mock_conn = AsyncMock()
        mock_pool = AsyncMock()
        mock_pool.acquire = AsyncMock(return_value=mock_conn)
        mock_pool.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.__aexit__ = AsyncMock(return_value=None)

        manager._pool = mock_pool

        # Acquire connection
        time.time()
        async with manager.acquire() as conn:
            assert conn == mock_conn
            assert manager.metrics.active_connections == 1
            assert manager.metrics.total_requests == 1

        # After release
        assert manager.metrics.active_connections == 0
        assert len(manager.metrics.connection_wait_time_ms) == 1

    @pytest.mark.asyncio
    async def test_health_check(self, pool_config):
        """Test pool health check."""
        manager = PostgreSQLPoolManager(pool_config)

        mock_pool = AsyncMock()
        mock_pool.get_size.return_value = 25
        mock_pool.get_idle_size.return_value = 20

        manager._pool = mock_pool
        manager.metrics.total_requests = 1000
        manager.metrics.total_connections = 25
        manager.metrics.connection_errors = 2

        health = await manager.health_check()

        assert health["status"] == "healthy"
        assert health["pool_size"] == 25
        assert health["idle_connections"] == 20
        assert health["active_connections"] == 5
        assert health["reuse_rate"] == 97.5
        assert health["error_rate"] == 0.2


class TestQdrantClientManager:
    """Test Qdrant client singleton manager."""

    @pytest.fixture
    def client_config(self):
        """Default Qdrant client configuration."""
        return {
            "host": "localhost",
            "port": 6333,
            "grpc_port": 6334,
            "api_key": None,
            "timeout": 30,
            "prefer_grpc": True,
        }

    @pytest.mark.asyncio
    async def test_singleton_pattern(self, client_config):
        """Test that only one client instance is created."""
        manager = QdrantClientManager(client_config)

        mock_client = MagicMock()
        with patch(
            "qdrant_client.QdrantClient", return_value=mock_client
        ) as mock_qdrant:
            client1 = await manager.get_client()
            client2 = await manager.get_client()

            # Should only create one client
            mock_qdrant.assert_called_once()
            assert client1 is client2
            assert manager.metrics.total_connections == 1

    @pytest.mark.asyncio
    async def test_client_reconnection_on_error(self, client_config):
        """Test client reconnection when connection is lost."""
        manager = QdrantClientManager(client_config)

        # First client fails
        failing_client = MagicMock()
        failing_client.get_collections = MagicMock(
            side_effect=Exception("Connection lost")
        )

        # Second client succeeds
        working_client = MagicMock()
        working_client.get_collections = MagicMock(return_value={"collections": []})

        with patch(
            "qdrant_client.QdrantClient", side_effect=[failing_client, working_client]
        ):
            # First attempt should fail and trigger reconnection
            await manager.get_client()

            # Verify health check triggered reconnection
            health = await manager.health_check()
            assert health["status"] == "reconnected"
            assert manager.metrics.connection_errors == 1
            assert manager.metrics.total_connections == 2

    @pytest.mark.asyncio
    async def test_concurrent_access(self, client_config):
        """Test thread-safe concurrent access to singleton."""
        manager = QdrantClientManager(client_config)

        mock_client = MagicMock()
        with patch("qdrant_client.QdrantClient", return_value=mock_client):
            # Simulate concurrent access
            tasks = [manager.get_client() for _ in range(10)]
            clients = await asyncio.gather(*tasks)

            # All should be the same instance
            assert all(client is clients[0] for client in clients)
            assert manager.metrics.total_requests == 10
            assert manager.metrics.total_connections == 1


class TestHTTPSessionManager:
    """Test HTTP session pool manager."""

    @pytest.fixture
    def session_config(self):
        """Default HTTP session configuration."""
        return {
            "max_connections": 100,
            "max_keepalive_connections": 20,
            "keepalive_expiry": 30,
            "timeout": 30,
            "retries": 3,
        }

    @pytest.mark.asyncio
    async def test_session_pool_creation(self, session_config):
        """Test HTTP session pool creation."""
        manager = HTTPSessionManager(session_config)

        await manager.initialize()

        assert manager._client is not None
        assert manager._limits.max_connections == 100
        assert manager._limits.max_keepalive_connections == 20
        assert manager.metrics.total_connections == 1

    @pytest.mark.asyncio
    async def test_session_reuse(self, session_config):
        """Test HTTP session reuse across requests."""
        manager = HTTPSessionManager(session_config)
        await manager.initialize()

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = AsyncMock(return_value={"result": "success"})

        with patch.object(
            manager._client, "get", AsyncMock(return_value=mock_response)
        ) as mock_get:
            # Make multiple requests
            for _ in range(5):
                async with manager.session() as session:
                    response = await session.get("https://api.example.com")
                    assert response.status_code == 200

            # Should reuse the same session
            assert mock_get.call_count == 5
            assert manager.metrics.total_requests == 5
            assert manager.metrics.total_connections == 1
            assert manager.metrics.calculate_reuse_rate() == 80.0

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, session_config):
        """Test concurrent HTTP requests with connection limiting."""
        manager = HTTPSessionManager(session_config)
        await manager.initialize()

        # Track concurrent connections
        active_connections = []
        max_concurrent = 0

        async def make_request(delay: float):
            nonlocal max_concurrent
            active_connections.append(1)
            max_concurrent = max(max_concurrent, len(active_connections))

            async with manager.session():
                await asyncio.sleep(delay)  # Simulate request time

            active_connections.pop()

        # Launch 50 concurrent requests
        tasks = [make_request(0.1) for _ in range(50)]
        await asyncio.gather(*tasks)

        # Should handle all requests
        assert manager.metrics.total_requests == 50
        # Max concurrent should not exceed pool size
        assert max_concurrent <= session_config["max_connections"]

    @pytest.mark.asyncio
    async def test_retry_mechanism(self, session_config):
        """Test automatic retry on failure."""
        manager = HTTPSessionManager(session_config)
        await manager.initialize()

        # Mock responses: fail twice, then succeed
        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Connection error")

            response = AsyncMock()
            response.status_code = 200
            return response

        manager._client.get = mock_request

        async with manager.session() as session:
            response = await session.get("https://api.example.com")
            assert response.status_code == 200

        assert call_count == 3  # Two failures + one success
        assert manager.metrics.connection_errors == 2


class TestConnectionManager:
    """Test unified connection manager."""

    @pytest.fixture
    def full_config(self):
        """Full configuration for all connection types."""
        return {
            "postgresql": {
                "dsn": "postgresql://test:test@localhost:5432/test",
                "min_size": 10,
                "max_size": 50,
            },
            "qdrant": {"host": "localhost", "port": 6333},
            "http": {"max_connections": 100},
        }

    @pytest.mark.asyncio
    async def test_unified_initialization(self, full_config):
        """Test initialization of all connection managers."""
        manager = ConnectionManager(full_config)

        with patch("asyncpg.create_pool", AsyncMock()):
            with patch("qdrant_client.QdrantClient"):
                await manager.initialize_all()

                assert manager.postgresql is not None
                assert manager.qdrant is not None
                assert manager.http is not None

    @pytest.mark.asyncio
    async def test_get_all_metrics(self, full_config):
        """Test aggregated metrics collection."""
        manager = ConnectionManager(full_config)

        # Mock individual managers
        manager.postgresql = AsyncMock()
        manager.postgresql.metrics = ConnectionPoolMetrics()
        manager.postgresql.metrics.total_requests = 100

        manager.qdrant = AsyncMock()
        manager.qdrant.metrics = ConnectionPoolMetrics()
        manager.qdrant.metrics.total_requests = 50

        manager.http = AsyncMock()
        manager.http.metrics = ConnectionPoolMetrics()
        manager.http.metrics.total_requests = 200

        metrics = await manager.get_all_metrics()

        assert metrics["postgresql"]["total_requests"] == 100
        assert metrics["qdrant"]["total_requests"] == 50
        assert metrics["http"]["total_requests"] == 200
        assert metrics["total_requests"] == 350

    @pytest.mark.asyncio
    async def test_cleanup(self, full_config):
        """Test proper cleanup of all connections."""
        manager = ConnectionManager(full_config)

        # Mock managers
        manager.postgresql = AsyncMock()
        manager.qdrant = AsyncMock()
        manager.http = AsyncMock()

        await manager.cleanup_all()

        manager.postgresql.close.assert_called_once()
        manager.qdrant.close.assert_called_once()
        manager.http.close.assert_called_once()
