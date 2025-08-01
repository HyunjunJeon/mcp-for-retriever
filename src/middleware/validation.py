"""Request validation middleware for MCP server."""

from typing import Any, Callable, Dict, Optional, Set
import structlog

logger = structlog.get_logger(__name__)


class ValidationMiddleware:
    """Middleware for validating MCP requests and enforcing permissions."""

    def __init__(
        self,
        allowed_methods: Optional[Set[str]] = None,
        tool_permissions: Optional[Dict[str, Set[str]]] = None,
        validate_params: bool = True,
    ):
        """Initialize validation middleware.

        Args:
            allowed_methods: Set of allowed MCP methods
            tool_permissions: Mapping of role to allowed tools
            validate_params: Whether to validate request parameters
        """
        self.allowed_methods = allowed_methods or {
            "tools/list",
            "tools/call",
            "health_check",
            "search_web",
            "search_vectors",
            "search_database",
            "search_all",
        }

        self.tool_permissions = tool_permissions or {
            "admin": {
                "search_web",
                "search_vectors",
                "search_database",
                "search_all",
                "health_check",
            },
            "user": {
                "search_web",
                "search_vectors",
                "search_database",
                "search_all",
                "health_check",
            },
            "guest": {"search_web", "health_check"},
        }

        self.validate_params = validate_params

    async def __call__(
        self, request: Dict[str, Any], call_next: Callable
    ) -> Dict[str, Any]:
        """Validate incoming requests."""
        # Validate request structure
        if not isinstance(request, dict):
            return self._invalid_request_response("Request must be a JSON object")

        # Validate required fields
        if "jsonrpc" not in request:
            return self._invalid_request_response("Missing required field: jsonrpc")

        if request.get("jsonrpc") != "2.0":
            return self._invalid_request_response(
                "Invalid jsonrpc version, must be 2.0"
            )

        if "method" not in request:
            return self._invalid_request_response("Missing required field: method")

        if "id" not in request:
            return self._invalid_request_response("Missing required field: id")

        method = request["method"]

        # Validate method is allowed
        if method not in self.allowed_methods:
            logger.warning(
                "Method not allowed",
                method=method,
                user_id=request.get("user", {}).get("id"),
            )
            return self._method_not_found_response(method)

        # Validate tool permissions
        if method == "tools/call":
            validation_result = await self._validate_tool_call(request)
            if validation_result:
                return validation_result

        # Validate parameters if enabled
        if self.validate_params:
            validation_result = self._validate_params(request)
            if validation_result:
                return validation_result

        # All validations passed
        return await call_next(request)

    async def _validate_tool_call(
        self, request: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Validate tool call permissions."""
        params = request.get("params", {})

        if not isinstance(params, dict):
            return self._invalid_params_response(
                "Params must be an object for tools/call"
            )

        tool_name = params.get("name")
        if not tool_name:
            return self._invalid_params_response("Missing tool name in params")

        # Check user permissions
        user = request.get("user", {})
        user_roles = (
            user.get("roles", ["guest"]) if isinstance(user, dict) else ["guest"]
        )

        # Service accounts have all permissions
        if isinstance(user, dict) and user.get("type") == "service":
            return None

        # Check if user has permission for this tool
        allowed_tools = set()
        for role in user_roles:
            allowed_tools.update(self.tool_permissions.get(role, set()))

        if tool_name not in allowed_tools:
            logger.warning(
                "Tool access denied",
                tool_name=tool_name,
                user_roles=user_roles,
                user_id=user.get("id") if isinstance(user, dict) else None,
            )
            return self._permission_denied_response(
                f"Access denied for tool: {tool_name}"
            )

        return None

    def _validate_params(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Validate request parameters based on method."""
        method = request["method"]
        params = request.get("params", {})

        # Skip validation for methods without params
        if method in ["tools/list", "health_check"]:
            return None

        if not isinstance(params, dict):
            return self._invalid_params_response("Params must be an object")

        # Validate tools/call params
        if method == "tools/call":
            if "arguments" not in params:
                return self._invalid_params_response("Missing arguments in tool call")

            arguments = params.get("arguments", {})
            if not isinstance(arguments, dict):
                return self._invalid_params_response("Tool arguments must be an object")

            # Validate specific tool arguments
            tool_name = params.get("name")
            if tool_name in [
                "search_web",
                "search_vectors",
                "search_database",
                "search_all",
            ]:
                if "query" not in arguments:
                    return self._invalid_params_response(
                        f"Missing required argument 'query' for {tool_name}"
                    )

                # Validate query is not empty
                query = arguments.get("query", "").strip()
                if not query:
                    return self._invalid_params_response("Query cannot be empty")

                # Validate query length
                if len(query) > 1000:
                    return self._invalid_params_response(
                        "Query too long (max 1000 characters)"
                    )

            # Validate search_vectors specific params
            if tool_name == "search_vectors" and "collection" not in arguments:
                return self._invalid_params_response(
                    "Missing required argument 'collection' for search_vectors"
                )

        return None

    def _invalid_request_response(self, message: str) -> Dict[str, Any]:
        """Create invalid request response."""
        return {
            "jsonrpc": "2.0",
            "error": {
                "code": -32600,
                "message": "Invalid Request",
                "data": {"details": message},
            },
            "id": None,
        }

    def _method_not_found_response(self, method: str) -> Dict[str, Any]:
        """Create method not found response."""
        return {
            "jsonrpc": "2.0",
            "error": {
                "code": -32601,
                "message": "Method not found",
                "data": {"method": method},
            },
            "id": None,
        }

    def _invalid_params_response(self, message: str) -> Dict[str, Any]:
        """Create invalid params response."""
        return {
            "jsonrpc": "2.0",
            "error": {
                "code": -32602,
                "message": "Invalid params",
                "data": {"details": message},
            },
            "id": None,
        }

    def _permission_denied_response(self, message: str) -> Dict[str, Any]:
        """Create permission denied response."""
        return {
            "jsonrpc": "2.0",
            "error": {
                "code": -32603,
                "message": "Permission denied",
                "data": {"details": message},
            },
            "id": None,
        }
