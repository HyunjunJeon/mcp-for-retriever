"""Integration tests for server profiles functionality."""

import pytest
import os
import asyncio
import httpx

from src.server_unified import UnifiedMCPServer
from src.config import ServerConfig
from tests.integration.conftest import wait_for_server


class TestServerProfiles:
    """Test different server profile configurations."""

    @pytest.mark.asyncio
    async def test_basic_profile_features(self):
        """Test BASIC profile has minimal features."""
        os.environ["MCP_PROFILE"] = "BASIC"
        os.environ["MCP_TRANSPORT"] = "stdio"

        config = ServerConfig.from_env()
        UnifiedMCPServer(config)

        # Verify features are disabled
        assert not config.features["auth"]
        assert not config.features["cache"]
        assert not config.features["rate_limit"]
        assert not config.features["context"]
        assert not config.features["metrics"]

    @pytest.mark.asyncio
    async def test_auth_profile_features(self):
        """Test AUTH profile enables authentication."""
        os.environ["MCP_PROFILE"] = "AUTH"
        os.environ["MCP_TRANSPORT"] = "http"
        os.environ["MCP_INTERNAL_API_KEY"] = "test-key"
        os.environ["JWT_SECRET_KEY"] = "test-secret"

        config = ServerConfig.from_env()
        UnifiedMCPServer(config)

        # Verify auth is enabled but other advanced features are not
        assert config.features["auth"]
        assert config.features["validation"]
        assert config.features["enhanced_logging"]
        assert not config.features["cache"]
        assert not config.features["context"]
        assert not config.features["rate_limit"]

    @pytest.mark.asyncio
    async def test_context_profile_features(self):
        """Test CONTEXT profile enables context tracking."""
        os.environ["MCP_PROFILE"] = "CONTEXT"
        os.environ["MCP_TRANSPORT"] = "http"
        os.environ["MCP_INTERNAL_API_KEY"] = "test-key"
        os.environ["JWT_SECRET_KEY"] = "test-secret"

        config = ServerConfig.from_env()
        UnifiedMCPServer(config)

        # Verify context and metrics are enabled
        assert config.features["auth"]
        assert config.features["context"]
        assert config.features["metrics"]
        assert not config.features["cache"]
        assert not config.features["rate_limit"]

    @pytest.mark.asyncio
    async def test_cached_profile_features(self):
        """Test CACHED profile enables caching."""
        os.environ["MCP_PROFILE"] = "CACHED"
        os.environ["MCP_TRANSPORT"] = "http"
        os.environ["MCP_INTERNAL_API_KEY"] = "test-key"
        os.environ["JWT_SECRET_KEY"] = "test-secret"
        os.environ["REDIS_URL"] = "redis://localhost:6379/0"

        config = ServerConfig.from_env()
        UnifiedMCPServer(config)

        # Verify cache is enabled
        assert config.features["auth"]
        assert config.features["cache"]
        assert not config.features["context"]
        assert not config.features["rate_limit"]

    @pytest.mark.asyncio
    async def test_complete_profile_features(self):
        """Test COMPLETE profile enables all features."""
        os.environ["MCP_PROFILE"] = "COMPLETE"
        os.environ["MCP_TRANSPORT"] = "http"
        os.environ["MCP_INTERNAL_API_KEY"] = "test-key"
        os.environ["JWT_SECRET_KEY"] = "test-secret"
        os.environ["REDIS_URL"] = "redis://localhost:6379/0"

        config = ServerConfig.from_env()
        UnifiedMCPServer(config)

        # Verify all features are enabled
        assert config.features["auth"]
        assert config.features["cache"]
        assert config.features["context"]
        assert config.features["rate_limit"]
        assert config.features["metrics"]
        assert config.features["validation"]
        assert config.features["enhanced_logging"]

    @pytest.mark.asyncio
    async def test_custom_profile_features(self):
        """Test CUSTOM profile with selective features."""
        os.environ["MCP_PROFILE"] = "CUSTOM"
        os.environ["MCP_TRANSPORT"] = "http"
        os.environ["MCP_ENABLE_AUTH"] = "true"
        os.environ["MCP_ENABLE_CACHE"] = "true"
        os.environ["MCP_ENABLE_CONTEXT"] = "false"
        os.environ["MCP_ENABLE_RATE_LIMIT"] = "false"
        os.environ["MCP_ENABLE_METRICS"] = "true"
        os.environ["MCP_INTERNAL_API_KEY"] = "test-key"
        os.environ["JWT_SECRET_KEY"] = "test-secret"
        os.environ["REDIS_URL"] = "redis://localhost:6379/0"

        config = ServerConfig.from_env()
        UnifiedMCPServer(config)

        # Verify only selected features are enabled
        assert config.features["auth"]
        assert config.features["cache"]
        assert not config.features["context"]
        assert not config.features["rate_limit"]
        assert config.features["metrics"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_profile_middleware_stack(self):
        """Test that middleware is correctly applied based on profile."""
        # Test AUTH profile middleware
        os.environ["MCP_PROFILE"] = "AUTH"
        os.environ["MCP_TRANSPORT"] = "http"
        os.environ["MCP_SERVER_PORT"] = "8002"
        os.environ["MCP_INTERNAL_API_KEY"] = "test-key"
        os.environ["JWT_SECRET_KEY"] = "test-secret"

        config = ServerConfig.from_env()
        server = UnifiedMCPServer(config)

        # Start server
        server_task = asyncio.create_task(server.run())

        try:
            # Wait for server to start
            await wait_for_server("http://localhost:8002/health")

            # Test without auth - should fail
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8002/",
                    json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
                )
                assert response.status_code == 401

            # Test with auth - should succeed
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8002/",
                    headers={"Authorization": "Bearer test-key"},
                    json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
                )
                assert response.status_code == 200

        finally:
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_profile_transition(self):
        """Test transitioning between profiles."""
        # Start with BASIC profile
        os.environ["MCP_PROFILE"] = "BASIC"
        config1 = ServerConfig.from_env()
        assert not config1.features["auth"]

        # Change to AUTH profile
        os.environ["MCP_PROFILE"] = "AUTH"
        config2 = ServerConfig.from_env()
        assert config2.features["auth"]

        # Change to COMPLETE profile
        os.environ["MCP_PROFILE"] = "COMPLETE"
        config3 = ServerConfig.from_env()
        assert all(config3.features.values())

    def teardown_method(self):
        """Clean up environment variables after each test."""
        env_vars_to_remove = [
            "MCP_PROFILE",
            "MCP_TRANSPORT",
            "MCP_SERVER_PORT",
            "MCP_INTERNAL_API_KEY",
            "JWT_SECRET_KEY",
            "REDIS_URL",
        ]
        for var in env_vars_to_remove:
            os.environ.pop(var, None)

        # Also remove individual feature flags
        for key in os.environ.copy():
            if key.startswith("MCP_ENABLE_"):
                os.environ.pop(key)
