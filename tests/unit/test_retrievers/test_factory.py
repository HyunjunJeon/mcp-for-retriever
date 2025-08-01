"""Unit tests for retriever factory."""

import pytest
from unittest.mock import AsyncMock, patch

from src.retrievers.base import Retriever
from src.retrievers.factory import RetrieverFactory, RetrieverFactoryError


class TestRetrieverFactory:
    """Test retriever factory functionality."""

    def test_factory_initialization(self):
        """Test factory can be initialized."""
        factory = RetrieverFactory()
        assert factory is not None
        assert hasattr(factory, "_retrievers")

    def test_register_retriever(self):
        """Test registering a retriever class."""
        factory = RetrieverFactory()

        # Create a mock retriever class that inherits from Retriever
        class MockRetriever(Retriever):
            async def connect(self):
                pass

            async def disconnect(self):
                pass

            async def retrieve(self, query, limit=10, **kwargs):
                yield {}

            async def health_check(self):
                pass

        factory.register("mock", MockRetriever)

        assert "mock" in factory._retrievers
        assert factory._retrievers["mock"] == MockRetriever

    def test_register_invalid_retriever(self):
        """Test registering an invalid retriever fails."""
        factory = RetrieverFactory()

        # Not a class
        with pytest.raises(ValueError, match="must be a class"):
            factory.register("invalid", "not a class")

        # Not a subclass of Retriever
        class NotARetriever:
            pass

        with pytest.raises(ValueError, match="must be a subclass of Retriever"):
            factory.register("invalid", NotARetriever)

    def test_create_registered_retriever(self):
        """Test creating a registered retriever."""
        factory = RetrieverFactory()

        # Create a mock retriever class
        class MockRetriever(Retriever):
            def __init__(self, config):
                super().__init__(config)
                self.test_config = config

            async def connect(self):
                pass

            async def disconnect(self):
                pass

            async def retrieve(self, query, limit=10, **kwargs):
                yield {}

            async def health_check(self):
                pass

        factory.register("mock", MockRetriever)

        # Create retriever
        config = {"type": "mock", "api_key": "test"}
        retriever = factory.create(config)

        assert isinstance(retriever, MockRetriever)
        assert retriever.test_config == {"api_key": "test"}

    def test_create_unregistered_retriever(self):
        """Test creating an unregistered retriever fails."""
        factory = RetrieverFactory()

        config = {"type": "unknown"}

        with pytest.raises(
            RetrieverFactoryError, match="Unknown retriever type: unknown"
        ):
            factory.create(config)

    def test_create_without_type(self):
        """Test creating retriever without type fails."""
        factory = RetrieverFactory()

        config = {"api_key": "test"}

        with pytest.raises(ValueError, match="type"):
            factory.create(config)

    def test_list_available_retrievers(self):
        """Test listing available retriever types."""
        factory = RetrieverFactory()

        # Register some retrievers
        class MockRetriever1(Retriever):
            async def connect(self):
                pass

            async def disconnect(self):
                pass

            async def retrieve(self, query, limit=10, **kwargs):
                yield {}

            async def health_check(self):
                pass

        class MockRetriever2(Retriever):
            async def connect(self):
                pass

            async def disconnect(self):
                pass

            async def retrieve(self, query, limit=10, **kwargs):
                yield {}

            async def health_check(self):
                pass

        factory.register("mock1", MockRetriever1)
        factory.register("mock2", MockRetriever2)

        available = factory.list_available()

        assert "mock1" in available
        assert "mock2" in available
        assert len(available) >= 2

    def test_get_retriever_class(self):
        """Test getting a registered retriever class."""
        factory = RetrieverFactory()

        class MockRetriever(Retriever):
            async def connect(self):
                pass

            async def disconnect(self):
                pass

            async def retrieve(self, query, limit=10, **kwargs):
                yield {}

            async def health_check(self):
                pass

        factory.register("mock", MockRetriever)

        retrieved_class = factory.get_retriever_class("mock")

        assert retrieved_class == MockRetriever

    def test_get_unregistered_retriever_class(self):
        """Test getting an unregistered retriever class returns None."""
        factory = RetrieverFactory()

        retrieved_class = factory.get_retriever_class("unknown")

        assert retrieved_class is None


class TestRetrieverFactoryWithDefaults:
    """Test retriever factory with default retrievers."""

    def test_factory_with_default_retrievers(self):
        """Test factory initializes with default retrievers."""
        # Create factory with defaults
        factory = RetrieverFactory(register_defaults=True)

        # Check that default retrievers are registered
        assert "tavily" in factory._retrievers

        # Import TavilyRetriever to check it's registered
        from src.retrievers.tavily import TavilyRetriever

        assert factory._retrievers["tavily"] == TavilyRetriever

    def test_create_tavily_retriever(self):
        """Test creating a Tavily retriever through factory."""
        # Import the actual TavilyRetriever to test integration
        from src.retrievers.tavily import TavilyRetriever

        factory = RetrieverFactory(register_defaults=True)

        config = {"type": "tavily", "api_key": "test-key", "max_results": 5}

        retriever = factory.create(config)

        assert isinstance(retriever, TavilyRetriever)
        assert retriever.api_key == "test-key"
        assert retriever.max_results == 5

    @pytest.mark.asyncio
    async def test_create_and_use_retriever(self):
        """Test creating and using a retriever through factory."""

        factory = RetrieverFactory(register_defaults=True)

        config = {"type": "tavily", "api_key": "test-key"}

        retriever = factory.create(config)

        # Test that we can use it as a context manager
        with patch.object(retriever, "_test_connection", new_callable=AsyncMock):
            async with retriever:
                assert retriever.connected


class TestRetrieverFactorySingleton:
    """Test retriever factory singleton pattern."""

    def test_get_default_factory(self):
        """Test getting the default factory instance."""
        factory1 = RetrieverFactory.get_default()
        factory2 = RetrieverFactory.get_default()

        assert factory1 is factory2
        assert "tavily" in factory1._retrievers

    def test_default_factory_persistence(self):
        """Test that registrations persist in default factory."""
        factory = RetrieverFactory.get_default()

        # Register a custom retriever
        class CustomRetriever(Retriever):
            async def connect(self):
                pass

            async def disconnect(self):
                pass

            async def retrieve(self, query, limit=10, **kwargs):
                yield {}

            async def health_check(self):
                pass

        factory.register("custom", CustomRetriever)

        # Get factory again
        factory2 = RetrieverFactory.get_default()

        assert "custom" in factory2._retrievers
        assert factory2._retrievers["custom"] == CustomRetriever


class TestRetrieverFactoryConfigValidation:
    """Test configuration validation in factory."""

    def test_create_with_extra_config(self):
        """Test creating retriever with extra configuration."""
        factory = RetrieverFactory()

        class MockRetriever(Retriever):
            def __init__(self, config):
                super().__init__(config)
                self.received_config = config

            async def connect(self):
                pass

            async def disconnect(self):
                pass

            async def retrieve(self, query, limit=10, **kwargs):
                yield {}

            async def health_check(self):
                pass

        factory.register("mock", MockRetriever)

        config = {"type": "mock", "api_key": "test", "extra_param": "value"}

        retriever = factory.create(config)

        # Should pass all config except 'type'
        assert retriever.received_config == {"api_key": "test", "extra_param": "value"}

    def test_create_with_invalid_config_type(self):
        """Test creating retriever with invalid config type."""
        factory = RetrieverFactory()

        with pytest.raises(TypeError, match="Config must be a dictionary"):
            factory.create("not a dict")

    def test_create_handles_retriever_init_error(self):
        """Test factory handles errors during retriever initialization."""
        factory = RetrieverFactory()

        # Retriever that raises on init
        class BrokenRetriever(Retriever):
            def __init__(self, config):
                raise ValueError("Invalid config")

            async def connect(self):
                pass

            async def disconnect(self):
                pass

            async def retrieve(self, query, limit=10, **kwargs):
                yield {}

            async def health_check(self):
                pass

        factory.register("broken", BrokenRetriever)

        config = {"type": "broken"}

        with pytest.raises(RetrieverFactoryError, match="Failed to create retriever"):
            factory.create(config)
