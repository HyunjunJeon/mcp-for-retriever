"""Full system integration tests with all middleware and observability."""

import pytest
from typing import Dict, Any, List, AsyncIterator
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import asyncio
import json
import time
from datetime import datetime, timedelta

from src.server_improved import create_mcp_server
from src.middleware import (
    AuthMiddleware,
    LoggingMiddleware,
    RateLimitMiddleware,
    ValidationMiddleware,
    MetricsMiddleware,
    ErrorHandlingMiddleware
)
from src.middleware.observability import ObservabilityMiddleware
from src.auth.models import User, UserRole
from src.retrievers.base import Retriever, RetrieverConfig


class MockRetrieverConfig(RetrieverConfig):
    """Mock retriever configuration."""
    test_param: str = "test"


class MockRetriever(Retriever[MockRetrieverConfig]):
    """Mock retriever for testing."""
    
    def __init__(self, config: MockRetrieverConfig):
        super().__init__(config)
        self.connected = False
        self.search_count = 0
    
    async def connect(self) -> None:
        self.connected = True
    
    async def disconnect(self) -> None:
        self.connected = False
    
    async def retrieve(self, query: str, **kwargs) -> AsyncIterator[Dict[str, Any]]:
        self.search_count += 1
        
        # Simulate different responses based on query
        if "error" in query:
            raise ValueError("Simulated retriever error")
        
        if "empty" in query:
            return
            
        # Normal response
        for i in range(3):
            yield {
                "id": f"result-{i}",
                "content": f"Result for '{query}' - item {i}",
                "score": 0.9 - (i * 0.1),
                "metadata": {"source": "mock", "timestamp": datetime.utcnow().isoformat()}
            }
    
    async def health_check(self) -> Dict[str, Any]:
        return {
            "status": "healthy" if self.connected else "disconnected",
            "search_count": self.search_count
        }


class TestFullSystemScenarios:
    """Test complete system scenarios with all components."""
    
    @pytest.fixture
    async def mock_retrievers(self):
        """Create mock retrievers."""
        web_retriever = MockRetriever(MockRetrieverConfig(test_param="web"))
        vector_retriever = MockRetriever(MockRetrieverConfig(test_param="vector"))
        db_retriever = MockRetriever(MockRetrieverConfig(test_param="database"))
        
        await web_retriever.connect()
        await vector_retriever.connect()
        await db_retriever.connect()
        
        yield {
            "web": web_retriever,
            "vector": vector_retriever,
            "database": db_retriever
        }
        
        await web_retriever.disconnect()
        await vector_retriever.disconnect()
        await db_retriever.disconnect()
    
    @pytest.fixture
    def mock_jwt_service(self):
        """Create mock JWT service."""
        mock_service = Mock()
        
        # Mock decode method
        def mock_decode(token: str):
            if token == "valid-jwt-token":
                return {"sub": "user-123", "email": "test@example.com", "role": "user"}
            elif token == "admin-jwt-token":
                return {"sub": "admin-456", "email": "admin@example.com", "role": "admin"}
            else:
                raise ValueError("Invalid token")
        
        mock_service.decode = mock_decode
        return mock_service
    
    @pytest.fixture
    def mock_user_service(self):
        """Create mock user service."""
        mock_service = AsyncMock()
        
        # Mock get_user method
        async def mock_get_user(user_id: str):
            if user_id == "user-123":
                return User(
                    id="user-123",
                    email="test@example.com",
                    role=UserRole.USER,
                    created_at=datetime.utcnow()
                )
            elif user_id == "admin-456":
                return User(
                    id="admin-456",
                    email="admin@example.com",
                    role=UserRole.ADMIN,
                    created_at=datetime.utcnow()
                )
            return None
        
        mock_service.get_user = mock_get_user
        return mock_service
    
    @pytest.fixture
    async def full_mcp_server(self, mock_retrievers, mock_jwt_service, mock_user_service):
        """Create MCP server with all middleware."""
        # Patch retrievers
        with patch('src.server_improved.web_retriever', mock_retrievers["web"]):
            with patch('src.server_improved.vector_retriever', mock_retrievers["vector"]):
                with patch('src.server_improved.db_retriever', mock_retrievers["database"]):
                    # Create server
                    mcp = create_mcp_server()
                    
                    # Add all middleware in proper order
                    middlewares = []
                    
                    # 1. Observability (outermost)
                    observability = ObservabilityMiddleware(
                        service_name="test-mcp",
                        enable_tracing=True,
                        enable_sentry=True,
                        trace_all_requests=True
                    )
                    middlewares.append(observability)
                    
                    # 2. Authentication
                    auth = AuthMiddleware(
                        jwt_service=mock_jwt_service,
                        user_service=mock_user_service,
                        internal_api_key="test-internal-key"
                    )
                    middlewares.append(auth)
                    
                    # 3. Logging
                    logging = LoggingMiddleware()
                    middlewares.append(logging)
                    
                    # 4. Validation
                    validation = ValidationMiddleware()
                    middlewares.append(validation)
                    
                    # 5. Rate Limiting
                    rate_limit = RateLimitMiddleware(
                        requests_per_minute=10,
                        burst_size=5
                    )
                    middlewares.append(rate_limit)
                    
                    # 6. Metrics
                    metrics = MetricsMiddleware()
                    middlewares.append(metrics)
                    
                    # 7. Error Handling (innermost)
                    error_handling = ErrorHandlingMiddleware()
                    middlewares.append(error_handling)
                    
                    # Apply middleware chain
                    handler = mcp._handle_request
                    for middleware in reversed(middlewares):
                        handler = lambda req, mw=middleware, h=handler: mw(req, h)
                    
                    mcp._handle_request = handler
                    
                    # Store middleware references for testing
                    mcp._test_middlewares = {
                        "observability": observability,
                        "auth": auth,
                        "logging": logging,
                        "validation": validation,
                        "rate_limit": rate_limit,
                        "metrics": metrics,
                        "error_handling": error_handling
                    }
                    
                    yield mcp
    
    @pytest.mark.asyncio
    async def test_successful_authenticated_search_flow(self, full_mcp_server):
        """Test successful search with authentication and full middleware stack."""
        # Create authenticated request
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "search_web",
                "arguments": {"query": "machine learning", "limit": 5}
            },
            "id": 1,
            "request_id": "req-success-123",
            "headers": {"authorization": "Bearer valid-jwt-token"}
        }
        
        # Process request
        response = await full_mcp_server._handle_request(request)
        
        # Verify successful response
        assert "result" in response
        assert "results" in response["result"]
        assert len(response["result"]["results"]) == 3  # Mock returns 3 results
        
        # Verify metrics were collected
        metrics = full_mcp_server._test_middlewares["metrics"]
        assert metrics.request_count > 0
        assert "search_web" in metrics.tool_usage
        
        # Verify rate limit was tracked
        rate_limiter = full_mcp_server._test_middlewares["rate_limit"]
        user_key = "user:user-123"
        assert user_key in rate_limiter.buckets
    
    @pytest.mark.asyncio
    async def test_rate_limit_scenario(self, full_mcp_server):
        """Test rate limiting across multiple requests."""
        # Set aggressive rate limit for testing
        rate_limiter = full_mcp_server._test_middlewares["rate_limit"]
        rate_limiter.requests_per_minute = 3
        rate_limiter.burst_size = 2
        
        # Create request template
        def create_request(req_id: int):
            return {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "search_web",
                    "arguments": {"query": f"query-{req_id}"}
                },
                "id": req_id,
                "request_id": f"req-{req_id}",
                "headers": {"authorization": "Bearer valid-jwt-token"}
            }
        
        # Send burst of requests
        responses = []
        for i in range(5):
            request = create_request(i)
            response = await full_mcp_server._handle_request(request)
            responses.append(response)
            await asyncio.sleep(0.1)  # Small delay between requests
        
        # First 2 should succeed (burst size)
        assert "result" in responses[0]
        assert "result" in responses[1]
        
        # Remaining should be rate limited
        for i in range(2, 5):
            assert "error" in responses[i]
            assert responses[i]["error"]["code"] == -32045
            assert "Rate limit exceeded" in responses[i]["error"]["message"]
    
    @pytest.mark.asyncio
    async def test_error_propagation_and_recovery(self, full_mcp_server):
        """Test error handling and recovery across the system."""
        # Request that will cause an error
        error_request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "search_database",
                "arguments": {"query": "error in query"}  # Will trigger error
            },
            "id": 1,
            "request_id": "req-error-123",
            "headers": {"authorization": "Bearer valid-jwt-token"}
        }
        
        # Process error request
        error_response = await full_mcp_server._handle_request(error_request)
        
        # Verify error response
        assert "error" in error_response
        assert error_response["error"]["code"] == -32603  # Internal error
        assert "retriever error" in error_response["error"]["message"].lower()
        
        # Verify system can still process normal requests
        normal_request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "search_web",
                "arguments": {"query": "normal query"}
            },
            "id": 2,
            "request_id": "req-normal-456",
            "headers": {"authorization": "Bearer valid-jwt-token"}
        }
        
        normal_response = await full_mcp_server._handle_request(normal_request)
        assert "result" in normal_response
        assert len(normal_response["result"]["results"]) > 0
    
    @pytest.mark.asyncio
    async def test_concurrent_requests_handling(self, full_mcp_server):
        """Test system behavior under concurrent load."""
        # Create multiple concurrent requests
        async def make_request(query: str, req_id: int):
            request = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "search_all",
                    "arguments": {"query": query, "limit": 3}
                },
                "id": req_id,
                "request_id": f"req-concurrent-{req_id}",
                "headers": {"authorization": "Bearer valid-jwt-token"}
            }
            return await full_mcp_server._handle_request(request)
        
        # Send 10 concurrent requests
        tasks = []
        for i in range(10):
            query = f"concurrent test {i}"
            task = make_request(query, i)
            tasks.append(task)
        
        # Wait for all to complete
        start_time = time.time()
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        duration = time.time() - start_time
        
        # Verify all succeeded
        successful_responses = [r for r in responses if not isinstance(r, Exception) and "result" in r]
        assert len(successful_responses) >= 8  # At least 80% should succeed
        
        # Verify performance
        assert duration < 5.0  # Should complete within 5 seconds
        
        # Check metrics
        metrics = full_mcp_server._test_middlewares["metrics"]
        assert metrics.request_count >= 10
        assert metrics.concurrent_requests <= 10
    
    @pytest.mark.asyncio
    async def test_authentication_bypass_for_public_methods(self, full_mcp_server):
        """Test that public methods work without authentication."""
        # Request without auth header
        public_request = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "id": 1,
            "request_id": "req-public-123"
        }
        
        response = await full_mcp_server._handle_request(public_request)
        
        # Should succeed
        assert "result" in response
        assert "tools" in response["result"]
        assert len(response["result"]["tools"]) > 0
    
    @pytest.mark.asyncio
    async def test_admin_only_operations(self, full_mcp_server):
        """Test admin-only operations with proper authorization."""
        # Regular user request for health check
        user_request = {
            "jsonrpc": "2.0",
            "method": "health_check",
            "id": 1,
            "request_id": "req-user-health",
            "headers": {"authorization": "Bearer valid-jwt-token"}
        }
        
        user_response = await full_mcp_server._handle_request(user_request)
        
        # Should be denied for regular user
        assert "error" in user_response
        assert user_response["error"]["code"] == -32041
        assert "permission denied" in user_response["error"]["message"].lower()
        
        # Admin request for health check
        admin_request = {
            "jsonrpc": "2.0",
            "method": "health_check",
            "id": 2,
            "request_id": "req-admin-health",
            "headers": {"authorization": "Bearer admin-jwt-token"}
        }
        
        admin_response = await full_mcp_server._handle_request(admin_request)
        
        # Should succeed for admin
        assert "result" in admin_response
        assert "retrievers" in admin_response["result"]
    
    @pytest.mark.asyncio
    async def test_validation_failures(self, full_mcp_server):
        """Test various validation failure scenarios."""
        # Invalid method format
        invalid_method = {
            "jsonrpc": "2.0",
            "method": "invalid_method_format",
            "id": 1,
            "request_id": "req-invalid-method",
            "headers": {"authorization": "Bearer valid-jwt-token"}
        }
        
        response1 = await full_mcp_server._handle_request(invalid_method)
        assert "error" in response1
        assert response1["error"]["code"] == -32601  # Method not found
        
        # Missing required parameters
        missing_params = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "search_web"},  # Missing arguments
            "id": 2,
            "request_id": "req-missing-params",
            "headers": {"authorization": "Bearer valid-jwt-token"}
        }
        
        response2 = await full_mcp_server._handle_request(missing_params)
        assert "error" in response2
        assert response2["error"]["code"] == -32602  # Invalid params
        
        # Invalid parameter types
        invalid_types = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "search_web",
                "arguments": {"query": 123, "limit": "not-a-number"}  # Wrong types
            },
            "id": 3,
            "request_id": "req-invalid-types",
            "headers": {"authorization": "Bearer valid-jwt-token"}
        }
        
        response3 = await full_mcp_server._handle_request(invalid_types)
        assert "error" in response3
    
    @pytest.mark.asyncio
    async def test_middleware_order_and_interaction(self, full_mcp_server):
        """Test that middleware execute in correct order and interact properly."""
        # Track middleware execution order
        execution_order = []
        
        # Patch middleware methods to track order
        original_methods = {}
        
        for name, middleware in full_mcp_server._test_middlewares.items():
            original_method = middleware.__call__
            
            async def tracked_call(request, call_next, mw_name=name, orig=original_method):
                execution_order.append(f"{mw_name}_start")
                result = await orig(request, call_next)
                execution_order.append(f"{mw_name}_end")
                return result
            
            middleware.__call__ = tracked_call
            original_methods[name] = original_method
        
        # Make request
        request = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "id": 1,
            "request_id": "req-order-test"
        }
        
        await full_mcp_server._handle_request(request)
        
        # Restore original methods
        for name, method in original_methods.items():
            full_mcp_server._test_middlewares[name].__call__ = method
        
        # Verify execution order (outer to inner on start, inner to outer on end)
        expected_order = [
            "observability_start",
            "auth_start",
            "logging_start", 
            "validation_start",
            "rate_limit_start",
            "metrics_start",
            "error_handling_start",
            "error_handling_end",
            "metrics_end",
            "rate_limit_end",
            "validation_end",
            "logging_end",
            "auth_end",
            "observability_end"
        ]
        
        assert execution_order == expected_order