"""Unit tests for validation middleware."""

import pytest
from unittest.mock import AsyncMock

from src.middleware.validation import ValidationMiddleware


@pytest.fixture
def validation_middleware():
    """Create validation middleware instance."""
    return ValidationMiddleware(validate_params=True)


@pytest.fixture
def mock_call_next():
    """Create mock call_next function."""

    async def call_next(request):
        return {"result": "success"}

    return AsyncMock(side_effect=call_next)


class TestValidationMiddleware:
    """Test validation middleware."""

    @pytest.mark.asyncio
    async def test_valid_request_passes(self, validation_middleware, mock_call_next):
        """Test that valid request passes through."""
        request = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}

        result = await validation_middleware(request, mock_call_next)

        assert result == {"result": "success"}
        mock_call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_request_type(self, validation_middleware, mock_call_next):
        """Test invalid request type."""
        request = "not a dict"

        result = await validation_middleware(request, mock_call_next)

        assert "error" in result
        assert result["error"]["code"] == -32600
        assert "Request must be a JSON object" in result["error"]["message"]
        mock_call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_jsonrpc(self, validation_middleware, mock_call_next):
        """Test missing jsonrpc field."""
        request = {"method": "tools/list", "id": 1}

        result = await validation_middleware(request, mock_call_next)

        assert "error" in result
        assert result["error"]["code"] == -32600
        assert "Missing required field: jsonrpc" in result["error"]["message"]
        mock_call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_jsonrpc_version(self, validation_middleware, mock_call_next):
        """Test invalid jsonrpc version."""
        request = {"jsonrpc": "1.0", "method": "tools/list", "id": 1}

        result = await validation_middleware(request, mock_call_next)

        assert "error" in result
        assert result["error"]["code"] == -32600
        assert "Invalid jsonrpc version" in result["error"]["message"]
        mock_call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_method(self, validation_middleware, mock_call_next):
        """Test missing method field."""
        request = {"jsonrpc": "2.0", "id": 1}

        result = await validation_middleware(request, mock_call_next)

        assert "error" in result
        assert result["error"]["code"] == -32600
        assert "Missing required field: method" in result["error"]["message"]
        mock_call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_method_not_allowed(self, validation_middleware, mock_call_next):
        """Test method not in allowed list."""
        request = {"jsonrpc": "2.0", "method": "invalid_method", "id": 1}

        result = await validation_middleware(request, mock_call_next)

        assert "error" in result
        assert result["error"]["code"] == -32601
        assert "Method not found" in result["error"]["message"]
        mock_call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_tool_call_permission_denied(
        self, validation_middleware, mock_call_next
    ):
        """Test tool call permission denied."""
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "admin_tool"},
            "user": {"roles": ["guest"]},
            "id": 1,
        }

        result = await validation_middleware(request, mock_call_next)

        assert "error" in result
        assert result["error"]["code"] == -32603
        assert "Access denied for tool" in result["error"]["message"]
        mock_call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_tool_call_permission_allowed(
        self, validation_middleware, mock_call_next
    ):
        """Test tool call permission allowed."""
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "search_web", "arguments": {"query": "test"}},
            "user": {"roles": ["user"]},
            "id": 1,
        }

        result = await validation_middleware(request, mock_call_next)

        assert result == {"result": "success"}
        mock_call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_service_account_has_all_permissions(
        self, validation_middleware, mock_call_next
    ):
        """Test service account has all permissions."""
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "any_tool", "arguments": {}},
            "user": {"type": "service"},
            "id": 1,
        }

        result = await validation_middleware(request, mock_call_next)

        assert result == {"result": "success"}
        mock_call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_tool_arguments(self, validation_middleware, mock_call_next):
        """Test tool argument validation."""
        # Missing query argument
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "search_web", "arguments": {}},
            "user": {"roles": ["user"]},
            "id": 1,
        }

        result = await validation_middleware(request, mock_call_next)

        assert "error" in result
        assert result["error"]["code"] == -32602
        assert "Missing required argument 'query'" in result["error"]["message"]
        mock_call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_empty_query(self, validation_middleware, mock_call_next):
        """Test empty query validation."""
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "search_web", "arguments": {"query": "   "}},
            "user": {"roles": ["user"]},
            "id": 1,
        }

        result = await validation_middleware(request, mock_call_next)

        assert "error" in result
        assert result["error"]["code"] == -32602
        assert "Query cannot be empty" in result["error"]["message"]
        mock_call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_query_length(self, validation_middleware, mock_call_next):
        """Test query length validation."""
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "search_web", "arguments": {"query": "x" * 1001}},
            "user": {"roles": ["user"]},
            "id": 1,
        }

        result = await validation_middleware(request, mock_call_next)

        assert "error" in result
        assert result["error"]["code"] == -32602
        assert "Query too long" in result["error"]["message"]
        mock_call_next.assert_not_called()
