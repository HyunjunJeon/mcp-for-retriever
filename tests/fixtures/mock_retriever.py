"""Mock retriever implementation for testing."""

from typing import AsyncIterator, Any

from src.retrievers.base import (
    Retriever,
    RetrieverHealth,
    ConnectionError,
    QueryError,
    QueryResult,
    RetrieverConfig,
)


class MockRetriever(Retriever):
    """Mock retriever implementation for testing."""

    def __init__(self, config: RetrieverConfig):
        super().__init__(config)
        self.connect_called = False
        self.disconnect_called = False
        self.should_fail_connection = config.get("fail_connection", False)
        self.should_fail_query = config.get("fail_query", False)
        self.mock_data = config.get("mock_data", [])

    async def connect(self) -> None:
        """Mock connection implementation."""
        self.connect_called = True
        if self.should_fail_connection:
            raise ConnectionError("Mock connection failed", "MockRetriever")
        self._connected = True
        self._log_operation("connect")

    async def disconnect(self) -> None:
        """Mock disconnection implementation."""
        self.disconnect_called = True
        self._connected = False
        self._log_operation("disconnect")

    async def retrieve(
        self, query: str, limit: int = 10, **kwargs: Any
    ) -> AsyncIterator[QueryResult]:
        """Mock retrieve implementation."""
        if not self._connected:
            raise ConnectionError("Not connected", "MockRetriever")

        if self.should_fail_query:
            raise QueryError(f"Mock query failed: {query}", "MockRetriever")

        # Yield mock data up to limit
        for i, data in enumerate(self.mock_data[:limit]):
            yield data

    async def health_check(self) -> RetrieverHealth:
        """Mock health check implementation."""
        return RetrieverHealth(
            healthy=self._connected,
            service_name="MockRetriever",
            details={"mock": True},
        )
