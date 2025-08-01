"""Unit tests for custom exceptions and error handling."""

import asyncio

from src.exceptions import (
    ErrorCode,
    MCPError,
    AuthenticationError,
    AuthorizationError,
    RateLimitError,
    RetrieverError,
    ValidationError,
    TimeoutError,
    ResourceNotFoundError,
    ServiceUnavailableError,
    ErrorHandler,
)


class TestMCPError:
    """Test MCPError base class."""

    def test_mcp_error_creation(self):
        """Test creating MCPError."""
        error = MCPError("Test error", ErrorCode.INTERNAL_ERROR, {"detail": "test"})

        assert str(error) == "Test error"
        assert error.code == ErrorCode.INTERNAL_ERROR
        assert error.data == {"detail": "test"}

    def test_mcp_error_to_dict(self):
        """Test converting MCPError to dict."""
        error = MCPError("Test error", ErrorCode.VALIDATION_ERROR, {"field": "query"})
        error_dict = error.to_dict()

        assert error_dict["code"] == ErrorCode.VALIDATION_ERROR.value
        assert error_dict["message"] == "Test error"
        assert error_dict["data"] == {"field": "query"}

    def test_mcp_error_without_data(self):
        """Test MCPError without additional data."""
        error = MCPError("Simple error")
        error_dict = error.to_dict()

        assert error_dict["code"] == ErrorCode.INTERNAL_ERROR.value
        assert error_dict["message"] == "Simple error"
        assert "data" not in error_dict


class TestSpecificErrors:
    """Test specific error types."""

    def test_authentication_error(self):
        """Test AuthenticationError."""
        error = AuthenticationError("Invalid token")
        error_dict = error.to_dict()

        assert error_dict["code"] == ErrorCode.AUTHENTICATION_ERROR.value
        assert error_dict["message"] == "Invalid token"

    def test_authorization_error(self):
        """Test AuthorizationError."""
        error = AuthorizationError("Access denied", {"resource": "admin_tool"})
        error_dict = error.to_dict()

        assert error_dict["code"] == ErrorCode.AUTHORIZATION_ERROR.value
        assert error_dict["message"] == "Access denied"
        assert error_dict["data"]["resource"] == "admin_tool"

    def test_rate_limit_error(self):
        """Test RateLimitError."""
        error = RateLimitError("Too many requests", retry_after=60)
        error_dict = error.to_dict()

        assert error_dict["code"] == ErrorCode.RATE_LIMIT_ERROR.value
        assert error_dict["message"] == "Too many requests"
        assert error_dict["data"]["retry_after"] == 60
        assert error_dict["data"]["retry_after_human"] == "60 seconds"

    def test_retriever_error(self):
        """Test RetrieverError."""
        error = RetrieverError(
            "Connection failed", retriever_name="tavily", operation="connect"
        )
        error_dict = error.to_dict()

        assert error_dict["code"] == ErrorCode.RETRIEVER_ERROR.value
        assert error_dict["message"] == "Connection failed"
        assert error_dict["data"]["retriever"] == "tavily"
        assert error_dict["data"]["operation"] == "connect"

    def test_validation_error(self):
        """Test ValidationError."""
        error = ValidationError("Invalid value", field="query", value="x" * 1001)
        error_dict = error.to_dict()

        assert error_dict["code"] == ErrorCode.VALIDATION_ERROR.value
        assert error_dict["message"] == "Invalid value"
        assert error_dict["data"]["field"] == "query"
        assert len(error_dict["data"]["value"]) == 100  # Truncated

    def test_timeout_error(self):
        """Test TimeoutError."""
        error = TimeoutError(
            "Request timed out", operation="search_web", timeout_seconds=30.0
        )
        error_dict = error.to_dict()

        assert error_dict["code"] == ErrorCode.TIMEOUT_ERROR.value
        assert error_dict["message"] == "Request timed out"
        assert error_dict["data"]["operation"] == "search_web"
        assert error_dict["data"]["timeout_seconds"] == 30.0

    def test_resource_not_found_error(self):
        """Test ResourceNotFoundError."""
        error = ResourceNotFoundError(
            "Collection not found",
            resource_type="vector_collection",
            resource_id="my_collection",
        )
        error_dict = error.to_dict()

        assert error_dict["code"] == ErrorCode.RESOURCE_NOT_FOUND.value
        assert error_dict["message"] == "Collection not found"
        assert error_dict["data"]["resource_type"] == "vector_collection"
        assert error_dict["data"]["resource_id"] == "my_collection"

    def test_service_unavailable_error(self):
        """Test ServiceUnavailableError."""
        error = ServiceUnavailableError(
            "Database is down", service_name="postgres", retry_after=300
        )
        error_dict = error.to_dict()

        assert error_dict["code"] == ErrorCode.SERVICE_UNAVAILABLE.value
        assert error_dict["message"] == "Database is down"
        assert error_dict["data"]["service"] == "postgres"
        assert error_dict["data"]["retry_after"] == 300


class TestErrorHandler:
    """Test ErrorHandler utility."""

    def test_handle_mcp_error(self):
        """Test handling MCPError."""
        error = AuthenticationError("Invalid token")
        response = ErrorHandler.handle_error(error, request_id="123")

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == "123"
        assert response["error"]["code"] == ErrorCode.AUTHENTICATION_ERROR.value
        assert response["error"]["message"] == "Invalid token"

    def test_handle_asyncio_timeout(self):
        """Test handling asyncio.TimeoutError."""
        error = asyncio.TimeoutError()
        response = ErrorHandler.handle_error(error, request_id="456")

        assert response["error"]["code"] == ErrorCode.TIMEOUT_ERROR.value
        assert response["error"]["message"] == "Operation timed out"

    def test_handle_value_error(self):
        """Test handling ValueError."""
        error = ValueError("Invalid input")
        response = ErrorHandler.handle_error(error)

        assert response["error"]["code"] == ErrorCode.VALIDATION_ERROR.value
        assert response["error"]["message"] == "Invalid input"
        assert response["id"] is None

    def test_handle_generic_exception(self):
        """Test handling generic exception."""
        error = RuntimeError("Something went wrong")
        response = ErrorHandler.handle_error(error, request_id="789")

        assert response["error"]["code"] == ErrorCode.INTERNAL_ERROR.value
        assert response["error"]["message"] == "Internal server error"
        assert response["error"]["data"]["exception_type"] == "RuntimeError"
        assert response["error"]["data"]["exception_message"] == "Something went wrong"

    def test_create_error_context(self):
        """Test creating error context for logging."""
        error = RateLimitError("Too many requests", retry_after=60)
        context = ErrorHandler.create_error_context(
            error, method="tools/call", user_id="user123", tool_name="search_web"
        )

        assert context["error_type"] == "RateLimitError"
        assert context["error_message"] == "Too many requests"
        assert context["method"] == "tools/call"
        assert context["user_id"] == "user123"
        assert context["tool_name"] == "search_web"
        assert context["error_code"] == ErrorCode.RATE_LIMIT_ERROR.value
        assert context["error_data"]["retry_after"] == 60

    def test_create_error_context_generic(self):
        """Test creating error context for generic exception."""
        error = KeyError("missing_key")
        context = ErrorHandler.create_error_context(error)

        assert context["error_type"] == "KeyError"
        assert context["error_message"] == "'missing_key'"
        assert "error_code" not in context
        assert "error_data" not in context
