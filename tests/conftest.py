"""Shared test fixtures and configuration."""

import pytest
import asyncio
import os
from typing import Dict, Any, AsyncGenerator
from unittest.mock import Mock, AsyncMock, patch

# Configure pytest-asyncio
pytest_plugins = ["pytest_asyncio"]


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def mock_retriever():
    """Create a mock retriever for testing."""
    from src.retrievers.base import Retriever, RetrieverConfig
    
    class MockConfig(RetrieverConfig):
        test_param: str = "test"
    
    class MockRetriever(Retriever[MockConfig]):
        def __init__(self, config: MockConfig):
            super().__init__(config)
            self.connected = False
            
        async def connect(self) -> None:
            self.connected = True
            
        async def disconnect(self) -> None:
            self.connected = False
            
        async def retrieve(self, query: str, **kwargs) -> AsyncGenerator[Dict[str, Any], None]:
            for i in range(3):
                yield {"id": f"mock-{i}", "content": f"Result {i} for {query}"}
                
        async def health_check(self) -> Dict[str, Any]:
            return {"status": "healthy" if self.connected else "disconnected"}
    
    retriever = MockRetriever(MockConfig())
    await retriever.connect()
    yield retriever
    await retriever.disconnect()


@pytest.fixture
def mock_jwt_service():
    """Create a mock JWT service."""
    service = Mock()
    service.create.return_value = "mock-jwt-token"
    service.decode.return_value = {
        "sub": "user-123",
        "email": "test@example.com",
        "role": "user"
    }
    return service


@pytest.fixture
def mock_user_service():
    """Create a mock user service."""
    from src.auth.models import User, UserRole
    from datetime import datetime
    
    service = AsyncMock()
    service.get_user.return_value = User(
        id="user-123",
        email="test@example.com",
        role=UserRole.USER,
        created_at=datetime.utcnow()
    )
    return service


@pytest.fixture
def disable_observability():
    """Disable observability features for tests."""
    with patch.dict(os.environ, {
        "OTEL_SDK_DISABLED": "true",
        "SENTRY_DSN": ""
    }):
        yield


@pytest.fixture
def mock_telemetry():
    """Create mock telemetry setup."""
    from src.observability.telemetry import TelemetrySetup
    from opentelemetry.sdk.trace.export import InMemorySpanExporter
    
    telemetry = TelemetrySetup(
        service_name="test-service",
        enable_console_export=False,
        enable_prometheus=False
    )
    
    # Add in-memory exporter for testing
    memory_exporter = InMemorySpanExporter()
    telemetry._memory_exporter = memory_exporter
    
    return telemetry, memory_exporter


@pytest.fixture
def mock_sentry():
    """Create mock Sentry integration."""
    from src.observability.sentry_integration import SentryIntegration
    
    sentry = SentryIntegration(
        dsn=None,  # Disable actual sending
        environment="test"
    )
    sentry._initialized = True
    
    # Mock methods
    sentry.capture_error = Mock()
    sentry.capture_message_event = Mock()
    sentry.create_transaction = Mock(return_value=None)
    
    return sentry


@pytest.fixture
async def test_database():
    """Create a test database connection."""
    if os.getenv("TEST_DATABASE_URL"):
        import asyncpg
        conn = await asyncpg.connect(os.getenv("TEST_DATABASE_URL"))
        yield conn
        await conn.close()
    else:
        pytest.skip("Test database not configured")


@pytest.fixture
def redis_mock():
    """Create a mock Redis client."""
    from unittest.mock import AsyncMock
    
    redis = AsyncMock()
    redis.get.return_value = None
    redis.set.return_value = True
    redis.delete.return_value = 1
    redis.exists.return_value = False
    redis.expire.return_value = True
    
    return redis


# Test markers
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "docker: mark test as requiring Docker services"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "observability: mark test as testing observability features"
    )


# Environment setup
@pytest.fixture(autouse=True)
def setup_test_environment():
    """Setup test environment variables."""
    test_env = {
        "ENVIRONMENT": "test",
        "LOG_LEVEL": "DEBUG",
        "JWT_SECRET_KEY": "test-secret-key",
        "TAVILY_API_KEY": "test-tavily-key"
    }
    
    with patch.dict(os.environ, test_env):
        yield