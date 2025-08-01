"""Unit tests for authentication middleware."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from src.middleware.auth import AuthMiddleware


@pytest.fixture
def auth_middleware():
    """Create auth middleware instance."""
    return AuthMiddleware(
        internal_api_key="test-api-key",
        auth_gateway_url="http://localhost:8000",
        require_auth=True,
    )


@pytest.fixture
def mock_request():
    """Create mock request."""
    return {"method": "tools/call", "headers": {}, "jsonrpc": "2.0", "id": 1}


@pytest.fixture
def mock_call_next():
    """Create mock call_next function."""

    async def call_next(request):
        return {"result": "success"}

    return AsyncMock(side_effect=call_next)


class TestAuthMiddleware:
    """Test authentication middleware."""

    @pytest.mark.asyncio
    async def test_missing_auth_header(
        self, auth_middleware, mock_request, mock_call_next
    ):
        """Test request without authorization header."""
        result = await auth_middleware(mock_request, mock_call_next)

        assert "error" in result
        assert result["error"]["code"] == -32603
        assert "Missing authorization header" in result["error"]["message"]
        mock_call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_internal_api_key_auth(
        self, auth_middleware, mock_request, mock_call_next
    ):
        """Test authentication with internal API key."""
        mock_request["headers"]["authorization"] = "Bearer test-api-key"

        result = await auth_middleware(mock_request, mock_call_next)

        assert result == {"result": "success"}
        assert mock_request["user"]["type"] == "service"
        assert mock_request["user"]["service"] == "internal"
        mock_call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_jwt_token_validation_success(
        self, auth_middleware, mock_request, mock_call_next
    ):
        """Test successful JWT token validation."""
        mock_request["headers"]["authorization"] = "Bearer jwt-token"

        # Mock successful auth gateway response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "user123",
            "email": "test@example.com",
            "roles": ["user"],
        }

        with patch.object(
            auth_middleware.http_client, "get", return_value=mock_response
        ) as mock_get:
            result = await auth_middleware(mock_request, mock_call_next)

        assert result == {"result": "success"}
        assert mock_request["user"]["id"] == "user123"
        assert mock_request["user"]["email"] == "test@example.com"
        mock_get.assert_called_once_with(
            "http://localhost:8000/auth/me",
            headers={"Authorization": "Bearer jwt-token"},
        )
        mock_call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_jwt_token_validation_failure(
        self, auth_middleware, mock_request, mock_call_next
    ):
        """Test failed JWT token validation."""
        mock_request["headers"]["authorization"] = "Bearer invalid-token"

        # Mock failed auth gateway response
        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch.object(
            auth_middleware.http_client, "get", return_value=mock_response
        ):
            result = await auth_middleware(mock_request, mock_call_next)

        assert "error" in result
        assert result["error"]["code"] == -32603
        assert "Invalid or expired token" in result["error"]["message"]
        mock_call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_auth_gateway_connection_error(
        self, auth_middleware, mock_request, mock_call_next
    ):
        """Test auth gateway connection failure."""
        mock_request["headers"]["authorization"] = "Bearer jwt-token"

        with patch.object(
            auth_middleware.http_client,
            "get",
            side_effect=httpx.ConnectError("Connection failed"),
        ):
            result = await auth_middleware(mock_request, mock_call_next)

        assert "error" in result
        assert result["error"]["code"] == -32603
        assert "Authentication service unavailable" in result["error"]["message"]
        mock_call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_skip_auth_for_allowed_methods(self, mock_request, mock_call_next):
        """Test skipping auth for certain methods when not required."""
        auth_middleware = AuthMiddleware(
            internal_api_key="test-api-key",
            auth_gateway_url="http://localhost:8000",
            require_auth=False,
        )

        mock_request["method"] = "tools/list"

        result = await auth_middleware(mock_request, mock_call_next)

        assert result == {"result": "success"}
        mock_call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_resources(self, auth_middleware):
        """Test resource cleanup."""
        # Create a mock client
        auth_middleware._http_client = AsyncMock()

        await auth_middleware.close()

        auth_middleware._http_client.aclose.assert_called_once()
        assert auth_middleware._http_client is None
