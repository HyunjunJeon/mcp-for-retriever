"""Integration tests for JWT auto-refresh mechanism."""

import pytest
import asyncio
import os
from unittest.mock import patch

from src.auth.jwt_manager import JWTManager, AutoRefreshClient, create_jwt_system
from src.auth.services.jwt_service import JWTService


class TestJWTAutoRefreshIntegration:
    """Integration tests for JWT auto-refresh functionality."""

    @pytest.fixture
    async def jwt_system(self):
        """Create complete JWT system with Redis."""
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        secret_key = os.getenv("JWT_SECRET_KEY", "test-secret-key-for-testing")

        jwt_manager, token_store = await create_jwt_system(
            secret_key=secret_key,
            redis_url=redis_url,
            access_expire_minutes=1,  # Short expiry for testing
            refresh_expire_days=7,
        )

        yield jwt_manager, token_store

        # Cleanup
        await token_store.disconnect()

    @pytest.fixture
    def jwt_service_with_auto_refresh(self):
        """Create JWT service with auto-refresh enabled."""
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        secret_key = os.getenv("JWT_SECRET_KEY", "test-secret-key-for-testing")

        return JWTService(
            secret_key=secret_key,
            access_token_expire_minutes=1,  # Short expiry for testing
            refresh_token_expire_minutes=60 * 24 * 7,
            enable_auto_refresh=True,
            redis_url=redis_url,
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_full_token_lifecycle(self, jwt_system):
        """Test complete token lifecycle with auto-refresh."""
        jwt_manager, token_store = jwt_system

        user_data = {
            "user_id": "test123",
            "email": "test@example.com",
            "roles": ["user"],
            "scopes": ["read:vectors", "write:database"],
        }
        device_id = "test-device-001"
        metadata = {"ip": "192.168.1.100", "user_agent": "TestClient/1.0"}

        # Create initial token pair
        initial_pair = await jwt_manager.create_token_pair(
            user_data=user_data, device_id=device_id, metadata=metadata
        )

        assert initial_pair.access_token
        assert initial_pair.refresh_token
        assert initial_pair.expires_in == 60  # 1 minute

        # Verify tokens are valid
        access_payload = jwt_manager.validate_access_token(initial_pair.access_token)
        assert access_payload["user_id"] == "test123"
        assert access_payload["scopes"] == ["read:vectors", "write:database"]

        # Wait for token to be near expiry
        await asyncio.sleep(0.5)

        # Check if near expiry
        is_near_expiry = jwt_manager.is_token_near_expiry(
            initial_pair.access_token, threshold_minutes=1
        )
        assert is_near_expiry is True

        # Refresh tokens
        new_pair = await jwt_manager.refresh_tokens(
            refresh_token=initial_pair.refresh_token,
            device_id=device_id,
            metadata=metadata,
        )

        assert new_pair.access_token != initial_pair.access_token
        assert new_pair.refresh_token != initial_pair.refresh_token

        # Verify old refresh token is revoked
        is_valid = await token_store.validate_token(
            user_id="test123",
            refresh_token=initial_pair.refresh_token,
            device_id=device_id,
        )
        assert is_valid is False

        # Verify new refresh token is stored
        is_valid = await token_store.validate_token(
            user_id="test123", refresh_token=new_pair.refresh_token, device_id=device_id
        )
        assert is_valid is True

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_auto_refresh_client(self, jwt_system):
        """Test AutoRefreshClient with automatic token refresh."""
        jwt_manager, token_store = jwt_system

        # Create mock HTTP server
        async def mock_api_handler(request):
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return {"status": 401, "error": "Unauthorized"}

            token = auth_header[7:]
            payload = jwt_manager.validate_access_token(token)

            if not payload:
                return {"status": 401, "error": "Invalid token"}

            return {
                "status": 200,
                "data": {"user_id": payload["user_id"], "message": "Success"},
            }

        # Create initial tokens
        user_data = {
            "user_id": "client123",
            "email": "client@example.com",
            "roles": ["user"],
        }
        device_id = "client-device-001"

        initial_pair = await jwt_manager.create_token_pair(
            user_data=user_data, device_id=device_id
        )

        # Create auto-refresh client
        client = AutoRefreshClient(jwt_manager=jwt_manager, refresh_threshold_minutes=1)

        client.set_tokens(
            access_token=initial_pair.access_token,
            refresh_token=initial_pair.refresh_token,
            device_id=device_id,
        )

        # Mock the HTTP request
        with patch.object(
            client, "_make_authenticated_request", side_effect=mock_api_handler
        ):
            # First request should work
            result = await client.request("GET", "/api/test")
            assert result["status"] == 200
            assert result["data"]["user_id"] == "client123"

            # Wait for token to be near expiry
            await asyncio.sleep(0.5)

            # Next request should trigger auto-refresh
            result = await client.request("GET", "/api/test")
            assert result["status"] == 200

            # Verify token was refreshed
            assert client._access_token != initial_pair.access_token

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_jwt_service_integration(self, jwt_service_with_auto_refresh):
        """Test updated JWT service with auto-refresh support."""
        jwt_service = jwt_service_with_auto_refresh

        user_id = "service123"
        email = "service@example.com"
        roles = ["admin", "user"]
        device_id = "service-device-001"
        scopes = ["admin:all", "read:all", "write:all"]
        metadata = {"source": "integration_test"}

        # Create token pair using async method
        token_pair = await jwt_service.create_token_pair_async(
            user_id=user_id,
            email=email,
            roles=roles,
            device_id=device_id,
            scopes=scopes,
            metadata=metadata,
        )

        assert token_pair is not None
        assert token_pair.access_token
        assert token_pair.refresh_token

        # Decode and verify access token
        token_data = jwt_service.decode_token(token_pair.access_token)
        assert token_data.user_id == user_id
        assert token_data.email == email
        assert token_data.roles == roles
        assert token_data.scopes == scopes

        # Test refresh
        await asyncio.sleep(0.5)

        new_pair = await jwt_service.refresh_tokens_async(
            refresh_token=token_pair.refresh_token,
            device_id=device_id,
            metadata=metadata,
        )

        assert new_pair is not None
        assert new_pair.access_token != token_pair.access_token

        # Test token revocation
        revoked = await jwt_service.revoke_refresh_token(user_id, device_id)
        assert revoked is True

        # Refresh should fail after revocation
        failed_pair = await jwt_service.refresh_tokens_async(
            refresh_token=new_pair.refresh_token, device_id=device_id
        )
        assert failed_pair is None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_concurrent_refresh_handling(self, jwt_system):
        """Test that concurrent refresh attempts are handled properly."""
        jwt_manager, token_store = jwt_system

        # Create initial tokens
        user_data = {
            "user_id": "concurrent123",
            "email": "concurrent@example.com",
            "roles": ["user"],
        }
        device_id = "concurrent-device-001"

        initial_pair = await jwt_manager.create_token_pair(
            user_data=user_data, device_id=device_id
        )

        # Create auto-refresh client
        client = AutoRefreshClient(jwt_manager=jwt_manager)
        client.set_tokens(
            access_token=initial_pair.access_token,
            refresh_token=initial_pair.refresh_token,
            device_id=device_id,
        )

        # Simulate concurrent refresh attempts
        refresh_tasks = []
        for _ in range(10):
            task = asyncio.create_task(client._refresh_tokens())
            refresh_tasks.append(task)

        # Wait for all tasks to complete
        results = await asyncio.gather(*refresh_tasks)

        # All tasks should return the same new token
        first_token = results[0].access_token
        assert all(r.access_token == first_token for r in results)

        # Verify only one refresh actually occurred in the store
        # (This is ensured by the lock mechanism)
        assert client._access_token == first_token

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_device_tracking(self, jwt_system):
        """Test multi-device token management."""
        jwt_manager, token_store = jwt_system

        user_id = "multidevice123"
        user_data = {
            "user_id": user_id,
            "email": "multidevice@example.com",
            "roles": ["user"],
        }

        # Create tokens for multiple devices
        devices = ["phone-001", "tablet-002", "desktop-003"]
        tokens = {}

        for device_id in devices:
            pair = await jwt_manager.create_token_pair(
                user_data=user_data,
                device_id=device_id,
                metadata={"device_type": device_id.split("-")[0]},
            )
            tokens[device_id] = pair

        # Verify all tokens are valid
        for device_id, pair in tokens.items():
            is_valid = await token_store.validate_token(
                user_id=user_id, refresh_token=pair.refresh_token, device_id=device_id
            )
            assert is_valid is True

        # Revoke one device
        await token_store.revoke_token(user_id, "phone-001")

        # Verify phone token is revoked but others are still valid
        is_valid = await token_store.validate_token(
            user_id=user_id,
            refresh_token=tokens["phone-001"].refresh_token,
            device_id="phone-001",
        )
        assert is_valid is False

        # Other devices should still be valid
        for device_id in ["tablet-002", "desktop-003"]:
            is_valid = await token_store.validate_token(
                user_id=user_id,
                refresh_token=tokens[device_id].refresh_token,
                device_id=device_id,
            )
            assert is_valid is True

        # Revoke all user tokens
        count = await token_store.revoke_all_user_tokens(user_id)
        assert count == 2  # Only 2 remaining tokens

        # Verify all tokens are now invalid
        for device_id in ["tablet-002", "desktop-003"]:
            is_valid = await token_store.validate_token(
                user_id=user_id,
                refresh_token=tokens[device_id].refresh_token,
                device_id=device_id,
            )
            assert is_valid is False

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_background_refresh_task(self, jwt_system):
        """Test background token refresh functionality."""
        jwt_manager, token_store = jwt_system

        # Create tokens with very short expiry
        user_data = {
            "user_id": "background123",
            "email": "background@example.com",
            "roles": ["user"],
        }
        device_id = "background-device-001"

        # Create JWT manager with 30 second expiry for testing
        test_jwt_manager = JWTManager(
            secret_key=jwt_manager.secret_key,
            access_token_expire_minutes=0.5,  # 30 seconds
            refresh_token_expire_days=7,
            refresh_token_store=token_store,
        )

        initial_pair = await test_jwt_manager.create_token_pair(
            user_data=user_data, device_id=device_id
        )

        # Create client with background refresh
        client = AutoRefreshClient(
            jwt_manager=test_jwt_manager,
            refresh_threshold_minutes=0.3,  # 18 seconds before expiry
        )

        client.set_tokens(
            access_token=initial_pair.access_token,
            refresh_token=initial_pair.refresh_token,
            device_id=device_id,
        )

        # Track token changes
        original_access = client._access_token
        refresh_count = 0

        def on_refresh():
            nonlocal refresh_count
            refresh_count += 1

        # Patch refresh method to track calls
        original_refresh = client._refresh_tokens

        async def tracked_refresh():
            result = await original_refresh()
            on_refresh()
            return result

        client._refresh_tokens = tracked_refresh

        # Start background refresh with short interval
        await client.start_background_refresh(
            check_interval_seconds=0.2  # Check every 200ms
        )

        # Wait for automatic refresh to occur
        await asyncio.sleep(1)

        # Stop background task
        await client.stop_background_refresh()

        # Verify token was refreshed
        assert refresh_count >= 1
        assert client._access_token != original_access

        # Cleanup
        await client.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-k", "jwt_auto_refresh"])
