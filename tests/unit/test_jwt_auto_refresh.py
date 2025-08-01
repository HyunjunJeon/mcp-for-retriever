"""Unit tests for JWT token auto-refresh mechanism."""

import pytest
import asyncio
import jwt
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from src.auth.jwt_manager import (
    JWTManager,
    TokenPair,
    RefreshTokenStore,
    AutoRefreshClient,
)


class TestRefreshTokenStore:
    """Test refresh token storage and validation."""

    @pytest.fixture
    def token_store(self):
        """Create a refresh token store instance."""
        return RefreshTokenStore(
            redis_url="redis://localhost:6379/0",
            token_ttl=86400,  # 24 hours
        )

    @pytest.mark.asyncio
    async def test_store_refresh_token(self, token_store):
        """Test storing refresh token with metadata."""
        user_id = "user123"
        refresh_token = "refresh_token_abc123"
        device_id = "device_xyz"

        # Mock Redis operations
        with patch.object(token_store, "_redis", new_callable=AsyncMock) as mock_redis:
            mock_redis.setex = AsyncMock(return_value=True)

            # Store token
            await token_store.store_token(
                user_id=user_id,
                refresh_token=refresh_token,
                device_id=device_id,
                metadata={"ip": "192.168.1.1", "user_agent": "Mozilla/5.0"},
            )

            # Verify Redis call
            mock_redis.setex.assert_called_once()
            call_args = mock_redis.setex.call_args[0]
            assert f"refresh_token:{user_id}:{device_id}" in call_args[0]
            assert call_args[1] == 86400  # TTL

    @pytest.mark.asyncio
    async def test_validate_refresh_token(self, token_store):
        """Test refresh token validation."""
        user_id = "user123"
        refresh_token = "refresh_token_abc123"
        device_id = "device_xyz"

        # Mock Redis get operation
        stored_data = {
            "token": refresh_token,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "device_id": device_id,
            "metadata": {"ip": "192.168.1.1"},
        }

        with patch.object(token_store, "_redis", new_callable=AsyncMock) as mock_redis:
            mock_redis.get = AsyncMock(return_value=json.dumps(stored_data))

            # Validate token
            is_valid = await token_store.validate_token(
                user_id=user_id, refresh_token=refresh_token, device_id=device_id
            )

            assert is_valid is True

    @pytest.mark.asyncio
    async def test_revoke_refresh_token(self, token_store):
        """Test refresh token revocation."""
        user_id = "user123"
        device_id = "device_xyz"

        with patch.object(token_store, "_redis", new_callable=AsyncMock) as mock_redis:
            mock_redis.delete = AsyncMock(return_value=1)

            # Revoke token
            await token_store.revoke_token(user_id, device_id)

            # Verify deletion
            mock_redis.delete.assert_called_once_with(
                f"refresh_token:{user_id}:{device_id}"
            )

    @pytest.mark.asyncio
    async def test_revoke_all_user_tokens(self, token_store):
        """Test revoking all tokens for a user."""
        user_id = "user123"

        with patch.object(token_store, "_redis", new_callable=AsyncMock) as mock_redis:
            # Mock scan to find user's tokens
            mock_redis.scan = AsyncMock(
                return_value=(
                    0,
                    [
                        f"refresh_token:{user_id}:device1",
                        f"refresh_token:{user_id}:device2",
                    ],
                )
            )
            mock_redis.delete = AsyncMock(return_value=2)

            # Revoke all tokens
            count = await token_store.revoke_all_user_tokens(user_id)

            assert count == 2
            mock_redis.delete.assert_called_once()


class TestJWTManager:
    """Test JWT token generation and validation."""

    @pytest.fixture
    def jwt_manager(self):
        """Create JWT manager instance."""
        return JWTManager(
            secret_key="test-secret-key-for-testing-only",
            algorithm="HS256",
            access_token_expire_minutes=15,
            refresh_token_expire_days=7,
            refresh_token_store=MagicMock(),
        )

    def test_create_access_token(self, jwt_manager):
        """Test access token creation."""
        user_data = {
            "user_id": "user123",
            "email": "test@example.com",
            "roles": ["user"],
        }

        token = jwt_manager.create_access_token(user_data)

        # Decode and verify
        decoded = jwt.decode(
            token, jwt_manager.secret_key, algorithms=[jwt_manager.algorithm]
        )

        assert decoded["user_id"] == "user123"
        assert decoded["email"] == "test@example.com"
        assert decoded["roles"] == ["user"]
        assert decoded["type"] == "access"
        assert "exp" in decoded
        assert "iat" in decoded
        assert "jti" in decoded  # JWT ID for tracking

    def test_create_refresh_token(self, jwt_manager):
        """Test refresh token creation."""
        user_id = "user123"
        device_id = "device_xyz"

        token = jwt_manager.create_refresh_token(user_id, device_id)

        # Decode and verify
        decoded = jwt.decode(
            token, jwt_manager.secret_key, algorithms=[jwt_manager.algorithm]
        )

        assert decoded["user_id"] == "user123"
        assert decoded["device_id"] == "device_xyz"
        assert decoded["type"] == "refresh"
        assert "exp" in decoded

        # Verify longer expiration than access token
        exp_time = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
        now = datetime.now(timezone.utc)
        assert (exp_time - now).days >= 6

    @pytest.mark.asyncio
    async def test_create_token_pair(self, jwt_manager):
        """Test creating access and refresh token pair."""
        user_data = {
            "user_id": "user123",
            "email": "test@example.com",
            "roles": ["user"],
        }
        device_id = "device_xyz"

        # Mock refresh token store
        jwt_manager.refresh_token_store.store_token = AsyncMock()

        token_pair = await jwt_manager.create_token_pair(user_data, device_id)

        assert isinstance(token_pair, TokenPair)
        assert token_pair.access_token
        assert token_pair.refresh_token
        assert token_pair.expires_in == 900  # 15 minutes
        assert token_pair.refresh_expires_in == 604800  # 7 days

        # Verify refresh token was stored
        jwt_manager.refresh_token_store.store_token.assert_called_once()

    def test_validate_access_token(self, jwt_manager):
        """Test access token validation."""
        user_data = {"user_id": "user123", "email": "test@example.com"}
        token = jwt_manager.create_access_token(user_data)

        # Valid token
        decoded = jwt_manager.validate_access_token(token)
        assert decoded["user_id"] == "user123"

        # Invalid token
        invalid = jwt_manager.validate_access_token("invalid.token.here")
        assert invalid is None

        # Expired token
        expired_token = jwt.encode(
            {
                "user_id": "user123",
                "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
            },
            jwt_manager.secret_key,
            algorithm=jwt_manager.algorithm,
        )
        decoded = jwt_manager.validate_access_token(expired_token)
        assert decoded is None

    @pytest.mark.asyncio
    async def test_refresh_tokens(self, jwt_manager):
        """Test token refresh flow."""
        # Create initial tokens
        user_data = {
            "user_id": "user123",
            "email": "test@example.com",
            "roles": ["user"],
        }
        device_id = "device_xyz"

        # Mock store methods
        jwt_manager.refresh_token_store.store_token = AsyncMock()
        jwt_manager.refresh_token_store.validate_token = AsyncMock(return_value=True)
        jwt_manager.refresh_token_store.revoke_token = AsyncMock()

        # Create initial token pair
        initial_pair = await jwt_manager.create_token_pair(user_data, device_id)

        # Wait a bit to ensure different token generation
        await asyncio.sleep(0.1)

        # Refresh tokens
        new_pair = await jwt_manager.refresh_tokens(
            initial_pair.refresh_token, device_id
        )

        assert new_pair.access_token != initial_pair.access_token
        assert new_pair.refresh_token != initial_pair.refresh_token

        # Verify old refresh token was revoked
        jwt_manager.refresh_token_store.revoke_token.assert_called_once()

        # Verify new refresh token was stored
        assert jwt_manager.refresh_token_store.store_token.call_count == 2

    def test_token_near_expiry(self, jwt_manager):
        """Test checking if token is near expiry."""
        # Token expiring in 2 minutes
        near_expiry_token = jwt.encode(
            {
                "user_id": "user123",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=2),
            },
            jwt_manager.secret_key,
            algorithm=jwt_manager.algorithm,
        )

        # Should be considered near expiry (default threshold is 5 minutes)
        assert jwt_manager.is_token_near_expiry(near_expiry_token) is True

        # Token with plenty of time
        valid_token = jwt.encode(
            {
                "user_id": "user123",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
            },
            jwt_manager.secret_key,
            algorithm=jwt_manager.algorithm,
        )

        assert jwt_manager.is_token_near_expiry(valid_token) is False


class TestAutoRefreshClient:
    """Test automatic token refresh client."""

    @pytest.fixture
    def auto_refresh_client(self):
        """Create auto-refresh client instance."""
        jwt_manager = MagicMock()
        return AutoRefreshClient(
            jwt_manager=jwt_manager,
            refresh_threshold_minutes=5,
            retry_attempts=3,
            retry_delay_seconds=1,
        )

    @pytest.mark.asyncio
    async def test_auto_refresh_near_expiry(self, auto_refresh_client):
        """Test automatic refresh when token is near expiry."""
        # Mock current tokens
        current_access = "current_access_token"
        current_refresh = "current_refresh_token"
        device_id = "device_xyz"

        # Mock JWT manager methods
        auto_refresh_client.jwt_manager.is_token_near_expiry = MagicMock(
            return_value=True
        )
        auto_refresh_client.jwt_manager.refresh_tokens = AsyncMock(
            return_value=TokenPair(
                access_token="new_access_token",
                refresh_token="new_refresh_token",
                expires_in=900,
                refresh_expires_in=604800,
            )
        )

        # Set current tokens
        auto_refresh_client.set_tokens(current_access, current_refresh, device_id)

        # Make a request that should trigger refresh
        async def mock_request():
            return {"data": "response"}

        with patch.object(
            auto_refresh_client, "_make_authenticated_request", mock_request
        ):
            result = await auto_refresh_client.request("GET", "/api/test")

        assert result == {"data": "response"}

        # Verify refresh was called
        auto_refresh_client.jwt_manager.refresh_tokens.assert_called_once_with(
            current_refresh, device_id
        )

        # Verify new tokens are set
        assert auto_refresh_client._access_token == "new_access_token"
        assert auto_refresh_client._refresh_token == "new_refresh_token"

    @pytest.mark.asyncio
    async def test_retry_on_401(self, auto_refresh_client):
        """Test retry with token refresh on 401 response."""
        # Set initial tokens
        auto_refresh_client.set_tokens("expired_token", "refresh_token", "device_xyz")

        # Mock responses
        call_count = 0

        async def mock_request_handler(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # First call returns 401
                raise HTTPException(status_code=401, detail="Token expired")
            else:
                # Second call succeeds after refresh
                return {"data": "success"}

        # Mock refresh
        auto_refresh_client.jwt_manager.refresh_tokens = AsyncMock(
            return_value=TokenPair(
                access_token="new_token",
                refresh_token="new_refresh",
                expires_in=900,
                refresh_expires_in=604800,
            )
        )

        with patch.object(
            auto_refresh_client,
            "_make_authenticated_request",
            side_effect=mock_request_handler,
        ):
            result = await auto_refresh_client.request("GET", "/api/test")

        assert result == {"data": "success"}
        assert call_count == 2

        # Verify refresh was called
        auto_refresh_client.jwt_manager.refresh_tokens.assert_called_once()

    @pytest.mark.asyncio
    async def test_background_refresh_task(self, auto_refresh_client):
        """Test background token refresh task."""
        # Mock tokens with short expiry
        auto_refresh_client.set_tokens("access_token", "refresh_token", "device_xyz")

        # Mock JWT manager
        check_count = 0

        def mock_near_expiry(*args):
            nonlocal check_count
            check_count += 1
            # Return True on second check
            return check_count >= 2

        auto_refresh_client.jwt_manager.is_token_near_expiry = MagicMock(
            side_effect=mock_near_expiry
        )

        auto_refresh_client.jwt_manager.refresh_tokens = AsyncMock(
            return_value=TokenPair(
                access_token="refreshed_token",
                refresh_token="refreshed_refresh",
                expires_in=900,
                refresh_expires_in=604800,
            )
        )

        # Start background refresh with short interval
        await auto_refresh_client.start_background_refresh(check_interval_seconds=0.1)

        # Wait for refresh to occur
        await asyncio.sleep(0.3)

        # Stop background task
        await auto_refresh_client.stop_background_refresh()

        # Verify refresh occurred
        assert auto_refresh_client._access_token == "refreshed_token"
        auto_refresh_client.jwt_manager.refresh_tokens.assert_called()

    @pytest.mark.asyncio
    async def test_concurrent_refresh_prevention(self, auto_refresh_client):
        """Test that concurrent refreshes are prevented."""
        # Set tokens
        auto_refresh_client.set_tokens("access_token", "refresh_token", "device_xyz")

        # Mock slow refresh
        refresh_event = asyncio.Event()

        async def slow_refresh(*args):
            await refresh_event.wait()
            return TokenPair(
                access_token="new_token",
                refresh_token="new_refresh",
                expires_in=900,
                refresh_expires_in=604800,
            )

        auto_refresh_client.jwt_manager.refresh_tokens = AsyncMock(
            side_effect=slow_refresh
        )

        # Start multiple refresh attempts
        refresh_tasks = [
            asyncio.create_task(auto_refresh_client._refresh_tokens()) for _ in range(5)
        ]

        # Allow some time for tasks to start
        await asyncio.sleep(0.1)

        # Complete the refresh
        refresh_event.set()

        # Wait for all tasks
        results = await asyncio.gather(*refresh_tasks)

        # All should return the same token (only one refresh should occur)
        assert all(r.access_token == "new_token" for r in results)

        # Verify only one refresh call was made
        assert auto_refresh_client.jwt_manager.refresh_tokens.call_count == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
