"""Error handling middleware for MCP server."""

from typing import Any, Callable, Dict
import asyncio
import structlog
import traceback
from datetime import datetime

from fastmcp.server.middleware import Middleware, MiddlewareContext, CallNext

from src.exceptions import (
    MCPError,
    ErrorHandler,
    AuthenticationError,
    AuthorizationError,
    RateLimitError,
    RetrieverError,
    ValidationError,
    TimeoutError,
    ServiceUnavailableError
)

logger = structlog.get_logger(__name__)


class ErrorHandlerMiddleware(Middleware):
    """Middleware for handling and logging errors consistently."""
    
    def __init__(
        self,
        capture_stack_trace: bool = True,
        include_error_details: bool = True,
        max_error_log_length: int = 5000
    ):
        """Initialize error handler middleware.
        
        Args:
            capture_stack_trace: Whether to capture full stack traces
            include_error_details: Whether to include error details in responses
            max_error_log_length: Maximum length of error logs
        """
        self.capture_stack_trace = capture_stack_trace
        self.include_error_details = include_error_details
        self.max_error_log_length = max_error_log_length
        
        # Error statistics
        self._error_counts = {
            "total": 0,
            "by_type": {},
            "by_method": {}
        }
    
    async def on_message(self, context: MiddlewareContext, call_next: CallNext) -> Any:
        """Handle errors from downstream handlers."""
        method = context.method or "unknown"
        request_id = getattr(context, 'request_id', None) or f"req-{id(context)}"
        user = getattr(context, 'user', {})
        
        try:
            # Process request
            response = await call_next(context)
            
            return response
            
        except MCPError as e:
            # Our custom errors - handle gracefully
            await self._log_mcp_error(e, request_id, method, user)
            raise  # Re-raise for FastMCP to handle properly
            
        except Exception as e:
            # Unexpected errors - log with full details
            await self._log_unexpected_error(e, request_id, method, user)
            
            # Re-raise to let FastMCP handle the error response format
            raise
    
    async def _handle_response_error(
        self,
        response: Dict[str, Any],
        request_id: str,
        method: str,
        user: Dict[str, Any]
    ):
        """Handle errors in response from downstream handlers."""
        error = response.get("error", {})
        error_code = error.get("code", "unknown")
        error_message = error.get("message", "Unknown error")
        
        # Update statistics
        self._error_counts["total"] += 1
        self._error_counts["by_method"][method] = self._error_counts["by_method"].get(method, 0) + 1
        
        # Log based on error code
        if error_code in [-32001, -32002]:  # Auth errors
            logger.warning(
                "Authentication/Authorization error",
                request_id=request_id,
                method=method,
                user_id=user.get("id") if isinstance(user, dict) else None,
                error_code=error_code,
                error_message=error_message
            )
        elif error_code == -32003:  # Rate limit
            logger.info(
                "Rate limit exceeded",
                request_id=request_id,
                method=method,
                user_id=user.get("id") if isinstance(user, dict) else None,
                retry_after=error.get("data", {}).get("retry_after")
            )
        else:
            logger.error(
                "Request error",
                request_id=request_id,
                method=method,
                user_id=user.get("id") if isinstance(user, dict) else None,
                error=error
            )
    
    async def _log_mcp_error(
        self,
        error: MCPError,
        request_id: str,
        method: str,
        user: Dict[str, Any]
    ):
        """Log MCP errors with appropriate severity."""
        error_context = ErrorHandler.create_error_context(
            error,
            method=method,
            user_id=user.get("id") if isinstance(user, dict) else None
        )
        error_context["request_id"] = request_id
        
        # Update statistics
        self._error_counts["total"] += 1
        error_type = type(error).__name__
        self._error_counts["by_type"][error_type] = self._error_counts["by_type"].get(error_type, 0) + 1
        self._error_counts["by_method"][method] = self._error_counts["by_method"].get(method, 0) + 1
        
        # Choose log level based on error type
        if isinstance(error, (AuthenticationError, AuthorizationError)):
            logger.warning("Authentication/Authorization error", **error_context)
        elif isinstance(error, RateLimitError):
            logger.info("Rate limit error", **error_context)
        elif isinstance(error, ValidationError):
            logger.warning("Validation error", **error_context)
        elif isinstance(error, (TimeoutError, ServiceUnavailableError)):
            logger.error("Service error", **error_context)
        else:
            logger.error("MCP error", **error_context)
    
    async def _log_error(
        self,
        error: Exception,
        request_id: str,
        method: str,
        user: Dict[str, Any],
        is_timeout: bool = False
    ):
        """Log general errors."""
        error_context = {
            "request_id": request_id,
            "method": method,
            "user_id": user.get("id") if isinstance(user, dict) else None,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "is_timeout": is_timeout
        }
        
        # Update statistics
        self._error_counts["total"] += 1
        error_type = "TimeoutError" if is_timeout else type(error).__name__
        self._error_counts["by_type"][error_type] = self._error_counts["by_type"].get(error_type, 0) + 1
        self._error_counts["by_method"][method] = self._error_counts["by_method"].get(method, 0) + 1
        
        if is_timeout:
            logger.error("Request timeout", **error_context)
        else:
            logger.error("Request error", **error_context)
    
    async def _log_unexpected_error(
        self,
        error: Exception,
        request_id: str,
        method: str,
        user: Dict[str, Any]
    ):
        """Log unexpected errors with full stack trace."""
        error_context = {
            "request_id": request_id,
            "method": method,
            "user_id": user.get("id") if isinstance(user, dict) else None,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Capture stack trace if enabled
        if self.capture_stack_trace:
            stack_trace = traceback.format_exc()
            if len(stack_trace) > self.max_error_log_length:
                stack_trace = stack_trace[:self.max_error_log_length] + "... [TRUNCATED]"
            error_context["stack_trace"] = stack_trace
        
        # Update statistics
        self._error_counts["total"] += 1
        self._error_counts["by_type"]["UnexpectedError"] = self._error_counts["by_type"].get("UnexpectedError", 0) + 1
        self._error_counts["by_method"][method] = self._error_counts["by_method"].get(method, 0) + 1
        
        logger.exception(
            "Unexpected error in request processing",
            **error_context
        )
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """Get current error statistics."""
        return {
            "total_errors": self._error_counts["total"],
            "errors_by_type": dict(self._error_counts["by_type"]),
            "errors_by_method": dict(self._error_counts["by_method"]),
            "most_common_error": max(
                self._error_counts["by_type"].items(),
                key=lambda x: x[1],
                default=("None", 0)
            )[0] if self._error_counts["by_type"] else None,
            "most_error_prone_method": max(
                self._error_counts["by_method"].items(),
                key=lambda x: x[1],
                default=("None", 0)
            )[0] if self._error_counts["by_method"] else None
        }
    
    def reset_statistics(self):
        """Reset error statistics."""
        self._error_counts = {
            "total": 0,
            "by_type": {},
            "by_method": {}
        }