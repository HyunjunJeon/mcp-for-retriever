"""Unit tests for PostgreSQL database retriever."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import asyncpg

from src.retrievers.postgres import PostgresRetriever
from src.retrievers.base import (
    ConnectionError,
    QueryError,
)


@pytest.fixture
def postgres_config():
    """Fixture for PostgresRetriever configuration."""
    return {
        "dsn": "postgresql://user:pass@localhost:5432/testdb",
        "min_connections": 2,
        "max_connections": 10,
        "timeout": 30,
    }


@pytest.fixture
def mock_connection():
    """Mock PostgreSQL connection."""
    conn = AsyncMock()
    conn.fetchall = AsyncMock()
    conn.fetchrow = AsyncMock()
    conn.execute = AsyncMock()
    conn.close = AsyncMock()
    return conn


@pytest.fixture
def mock_pool(mock_connection):
    """Mock PostgreSQL connection pool."""
    pool = Mock()

    # Create a proper async context manager
    class AsyncContextManager:
        async def __aenter__(self):
            return mock_connection

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

    pool.acquire = Mock(return_value=AsyncContextManager())
    pool.close = AsyncMock()
    pool.get_size = Mock(return_value=5)
    pool.get_idle_size = Mock(return_value=3)

    return pool


class TestPostgresRetrieverConfiguration:
    """Test PostgresRetriever configuration and initialization."""

    def test_initialization_with_dsn(self, postgres_config):
        """Test retriever initialization with DSN."""
        retriever = PostgresRetriever(postgres_config)

        assert retriever.config == postgres_config
        assert retriever.dsn == "postgresql://user:pass@localhost:5432/testdb"
        assert retriever.min_connections == 2
        assert retriever.max_connections == 10
        assert retriever.timeout == 30
        assert not retriever.connected

    def test_initialization_without_dsn(self):
        """Test retriever initialization fails without DSN."""
        with pytest.raises(ValueError, match="dsn is required"):
            PostgresRetriever({})

    def test_initialization_with_defaults(self):
        """Test retriever initialization with default values."""
        config = {"dsn": "postgresql://localhost/db"}
        retriever = PostgresRetriever(config)

        assert retriever.dsn == "postgresql://localhost/db"
        assert retriever.min_connections == 1  # default
        assert retriever.max_connections == 10  # default
        assert retriever.timeout == 30  # default


@pytest.mark.asyncio
class TestPostgresRetrieverConnection:
    """Test PostgresRetriever connection management."""

    async def test_connect_success(self, postgres_config, mock_pool):
        """Test successful connection to PostgreSQL."""
        retriever = PostgresRetriever(postgres_config)

        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_create_pool.return_value = mock_pool

            await retriever.connect()

            assert retriever.connected
            mock_create_pool.assert_called_once_with(
                postgres_config["dsn"], min_size=2, max_size=10, timeout=30
            )

    async def test_connect_failure(self, postgres_config):
        """Test connection failure handling."""
        retriever = PostgresRetriever(postgres_config)

        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_create_pool.side_effect = asyncpg.PostgresError("Connection failed")

            with pytest.raises(
                ConnectionError, match="Failed to connect to PostgreSQL"
            ):
                await retriever.connect()

            assert not retriever.connected

    async def test_disconnect(self, postgres_config, mock_pool):
        """Test disconnection from PostgreSQL."""
        retriever = PostgresRetriever(postgres_config)
        retriever._pool = mock_pool
        retriever._connected = True

        await retriever.disconnect()

        assert not retriever.connected
        assert retriever._pool is None
        mock_pool.close.assert_called_once()


@pytest.mark.asyncio
class TestPostgresRetrieverSearch:
    """Test PostgresRetriever search functionality."""

    async def test_retrieve_when_not_connected(self, postgres_config):
        """Test retrieve raises error when not connected."""
        retriever = PostgresRetriever(postgres_config)

        with pytest.raises(ConnectionError, match="Not connected to PostgreSQL"):
            async for _ in retriever.retrieve("SELECT * FROM users"):
                pass

    async def test_retrieve_sql_query(
        self, postgres_config, mock_pool, mock_connection
    ):
        """Test SQL query execution."""
        retriever = PostgresRetriever(postgres_config)
        retriever._pool = mock_pool
        retriever._connected = True

        # Mock query results - asyncpg returns Record objects that behave like dicts
        class MockRecord(dict):
            """Mock asyncpg Record object."""

            pass

        mock_results = [
            MockRecord({"id": 1, "name": "John Doe", "email": "john@example.com"}),
            MockRecord({"id": 2, "name": "Jane Smith", "email": "jane@example.com"}),
        ]
        mock_connection.fetchall.return_value = mock_results

        results = []
        async for result in retriever.retrieve("SELECT * FROM users", limit=10):
            results.append(result)

        assert len(results) == 2
        assert results[0]["name"] == "John Doe"
        assert results[1]["name"] == "Jane Smith"

        mock_connection.fetchall.assert_called_once_with(
            "SELECT * FROM users LIMIT $1", 10
        )

    async def test_retrieve_text_search(
        self, postgres_config, mock_pool, mock_connection
    ):
        """Test full-text search functionality."""
        retriever = PostgresRetriever(postgres_config)
        retriever._pool = mock_pool
        retriever._connected = True

        # Mock search results
        class MockRecord(dict):
            pass

        mock_results = [
            MockRecord(
                {
                    "id": 1,
                    "title": "Python Guide",
                    "content": "Learn Python programming",
                }
            ),
            MockRecord(
                {"id": 2, "title": "Python Tutorial", "content": "Python basics"}
            ),
        ]
        mock_connection.fetchall.return_value = mock_results

        results = []
        async for result in retriever.retrieve(
            "Python", table="documents", search_columns=["title", "content"], limit=5
        ):
            results.append(result)

        assert len(results) == 2

        # Verify text search query was constructed
        call_args = mock_connection.fetchall.call_args
        query = call_args[0][0]
        assert "to_tsquery" in query or "LIKE" in query

    async def test_retrieve_with_filters(
        self, postgres_config, mock_pool, mock_connection
    ):
        """Test query with additional filters."""
        retriever = PostgresRetriever(postgres_config)
        retriever._pool = mock_pool
        retriever._connected = True

        class MockRecord(dict):
            pass

        mock_results = [MockRecord({"id": 1, "status": "active"})]
        mock_connection.fetchall.return_value = mock_results

        results = []
        async for result in retriever.retrieve(
            "SELECT * FROM users",
            filters={"status": "active", "role": "admin"},
            limit=10,
        ):
            results.append(result)

        assert len(results) == 1

    async def test_retrieve_query_error(
        self, postgres_config, mock_pool, mock_connection
    ):
        """Test handling of query errors."""
        retriever = PostgresRetriever(postgres_config)
        retriever._pool = mock_pool
        retriever._connected = True

        mock_connection.fetchall.side_effect = asyncpg.PostgresError("Query failed")

        with pytest.raises(QueryError, match="Query failed"):
            async for _ in retriever.retrieve("INVALID SQL"):
                pass

    async def test_retrieve_empty_results(
        self, postgres_config, mock_pool, mock_connection
    ):
        """Test handling of empty results."""
        retriever = PostgresRetriever(postgres_config)
        retriever._pool = mock_pool
        retriever._connected = True

        mock_connection.fetchall.return_value = []

        results = []
        async for result in retriever.retrieve("SELECT * FROM users WHERE id = -1"):
            results.append(result)

        assert len(results) == 0


@pytest.mark.asyncio
class TestPostgresRetrieverHealthCheck:
    """Test PostgresRetriever health check functionality."""

    async def test_health_check_when_connected(
        self, postgres_config, mock_pool, mock_connection
    ):
        """Test health check when connected."""
        retriever = PostgresRetriever(postgres_config)
        retriever._pool = mock_pool
        retriever._connected = True

        # Mock health check query
        class MockRecord(dict):
            pass

        mock_connection.fetchrow.return_value = MockRecord({"result": 1})

        health = await retriever.health_check()

        assert health.healthy
        assert health.service_name == "PostgresRetriever"
        assert health.details["connected"] is True
        assert health.error is None

        # Verify health check query was executed
        mock_connection.fetchrow.assert_called_once_with("SELECT 1")

    async def test_health_check_when_disconnected(self, postgres_config):
        """Test health check when disconnected."""
        retriever = PostgresRetriever(postgres_config)
        retriever._connected = False

        health = await retriever.health_check()

        assert not health.healthy
        assert health.service_name == "PostgresRetriever"
        assert health.details["connected"] is False
        assert health.error == "Not connected"

    async def test_health_check_query_failure(
        self, postgres_config, mock_pool, mock_connection
    ):
        """Test health check when query fails."""
        retriever = PostgresRetriever(postgres_config)
        retriever._pool = mock_pool
        retriever._connected = True

        mock_connection.fetchrow.side_effect = asyncpg.PostgresError("Connection lost")

        health = await retriever.health_check()

        assert not health.healthy
        assert health.service_name == "PostgresRetriever"
        assert "Connection lost" in health.error


@pytest.mark.asyncio
class TestPostgresRetrieverIntegration:
    """Test PostgresRetriever integration scenarios."""

    async def test_context_manager_usage(self, postgres_config, mock_pool):
        """Test using retriever as async context manager."""
        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_create_pool.return_value = mock_pool

            async with PostgresRetriever(postgres_config) as retriever:
                assert retriever.connected

            # After exiting context, should be disconnected
            assert not retriever.connected

    async def test_execute_write_operation(
        self, postgres_config, mock_pool, mock_connection
    ):
        """Test executing write operations."""
        retriever = PostgresRetriever(postgres_config)
        retriever._pool = mock_pool
        retriever._connected = True

        # Test insert operation
        await retriever.execute(
            "INSERT INTO users (name, email) VALUES ($1, $2)",
            "John Doe",
            "john@example.com",
        )

        mock_connection.execute.assert_called_once_with(
            "INSERT INTO users (name, email) VALUES ($1, $2)",
            "John Doe",
            "john@example.com",
        )

    async def test_transaction_support(
        self, postgres_config, mock_pool, mock_connection
    ):
        """Test transaction support."""
        retriever = PostgresRetriever(postgres_config)
        retriever._pool = mock_pool
        retriever._connected = True

        # Mock transaction
        class MockTransaction:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_connection.transaction = Mock(return_value=MockTransaction())

        async with retriever.transaction():
            await retriever.execute("UPDATE users SET status = 'active'")

        mock_connection.transaction.assert_called_once()

    async def test_prepared_statement(
        self, postgres_config, mock_pool, mock_connection
    ):
        """Test prepared statement usage."""
        retriever = PostgresRetriever(postgres_config)
        retriever._pool = mock_pool
        retriever._connected = True

        # Mock prepared statement
        mock_stmt = AsyncMock()
        mock_connection.prepare.return_value = mock_stmt

        class MockRecord(dict):
            pass

        mock_stmt.fetch.return_value = [MockRecord({"id": 1})]

        results = []
        async for result in retriever.retrieve_prepared(
            "SELECT * FROM users WHERE id = $1", 1
        ):
            results.append(result)

        assert len(results) == 1
        mock_connection.prepare.assert_called_once()
