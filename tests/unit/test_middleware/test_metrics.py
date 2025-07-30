"""Unit tests for metrics middleware."""

import pytest
import asyncio
from unittest.mock import AsyncMock

from src.middleware.metrics import MetricsMiddleware


@pytest.fixture
def metrics_middleware():
    """Create metrics middleware instance."""
    return MetricsMiddleware(
        enable_detailed_metrics=True,
        metrics_window_seconds=3600
    )


@pytest.fixture
def mock_call_next():
    """Create mock call_next function."""
    async def call_next(request):
        await asyncio.sleep(0.01)  # Simulate some processing time
        return {"result": "success"}
    return AsyncMock(side_effect=call_next)


@pytest.fixture
def mock_error_call_next():
    """Create mock call_next function that returns error."""
    async def call_next(request):
        await asyncio.sleep(0.01)
        return {"error": {"code": -32603, "message": "Test error"}}
    return AsyncMock(side_effect=call_next)


class TestMetricsMiddleware:
    """Test metrics middleware."""
    
    @pytest.mark.asyncio
    async def test_successful_request_metrics(self, metrics_middleware, mock_call_next):
        """Test metrics collection for successful request."""
        request = {
            "method": "tools/call",
            "params": {"name": "search_web"},
            "user": {"id": "user123", "email": "test@example.com"}
        }
        
        result = await metrics_middleware(request, mock_call_next)
        
        assert result == {"result": "success"}
        
        # Check metrics were updated
        metrics = await metrics_middleware.get_metrics_summary()
        assert metrics["summary"]["total_requests"] == 1
        assert metrics["summary"]["total_errors"] == 0
        assert metrics["summary"]["unique_users"] == 1
        assert "search_web" in metrics["tool_metrics"]
    
    @pytest.mark.asyncio
    async def test_error_request_metrics(self, metrics_middleware, mock_error_call_next):
        """Test metrics collection for error request."""
        request = {
            "method": "tools/call",
            "params": {"name": "search_web"},
            "user": {"id": "user123"}
        }
        
        result = await metrics_middleware(request, mock_error_call_next)
        
        assert "error" in result
        
        # Check metrics were updated
        metrics = await metrics_middleware.get_metrics_summary()
        assert metrics["summary"]["total_requests"] == 1
        assert metrics["summary"]["total_errors"] == 1
        assert len(metrics["recent_errors"]) == 1
    
    @pytest.mark.asyncio
    async def test_response_time_distribution(self, metrics_middleware, mock_call_next):
        """Test response time distribution tracking."""
        request = {
            "method": "tools/list",
            "user": {"id": "user123"}
        }
        
        # Make multiple requests
        for _ in range(5):
            await metrics_middleware(request, mock_call_next)
        
        metrics = await metrics_middleware.get_metrics_summary()
        
        # Check response time distribution
        assert sum(metrics["response_time_distribution"].values()) == 5
        # At least one bucket should have counts
        assert any(count > 0 for count in metrics["response_time_distribution"].values())
    
    @pytest.mark.asyncio
    async def test_tool_specific_metrics(self, metrics_middleware, mock_call_next):
        """Test tool-specific metrics collection."""
        # Make requests for different tools
        tools = ["search_web", "search_vectors", "search_database"]
        
        for tool in tools:
            request = {
                "method": "tools/call",
                "params": {"name": tool},
                "user": {"id": "user123"}
            }
            await metrics_middleware(request, mock_call_next)
        
        # Check individual tool metrics
        for tool in tools:
            tool_metrics = await metrics_middleware.get_tool_metrics(tool)
            assert tool_metrics["count"] == 1
            assert tool_metrics["errors"] == 0
            assert tool_metrics["min_duration_ms"] > 0
            assert tool_metrics["max_duration_ms"] > 0
            assert tool_metrics["avg_duration_ms"] > 0
    
    @pytest.mark.asyncio
    async def test_user_specific_metrics(self, metrics_middleware, mock_call_next):
        """Test user-specific metrics collection."""
        users = ["user1", "user2", "user3"]
        
        for user_id in users:
            request = {
                "method": "tools/call",
                "params": {"name": "search_web"},
                "user": {"id": user_id}
            }
            await metrics_middleware(request, mock_call_next)
        
        # Check individual user metrics
        for user_id in users:
            user_metrics = await metrics_middleware.get_user_metrics(user_id)
            assert user_metrics["user_id"] == user_id
            assert user_metrics["request_count"] == 1
            assert user_metrics["error_count"] == 0
            assert user_metrics["tool_usage"]["search_web"] == 1
            assert user_metrics["last_request_at"] is not None
    
    @pytest.mark.asyncio
    async def test_exception_handling(self, metrics_middleware):
        """Test metrics collection when exception occurs."""
        async def failing_call_next(request):
            raise ValueError("Test exception")
        
        request = {
            "method": "tools/call",
            "params": {"name": "search_web"},
            "user": {"id": "user123"}
        }
        
        with pytest.raises(ValueError):
            await metrics_middleware(request, failing_call_next)
        
        # Metrics should still be updated
        metrics = await metrics_middleware.get_metrics_summary()
        assert metrics["summary"]["total_requests"] == 1
        assert metrics["summary"]["total_errors"] == 1
    
    @pytest.mark.asyncio
    async def test_top_users_and_tools(self, metrics_middleware, mock_call_next):
        """Test top users and tools reporting."""
        # Create varied usage patterns
        for i in range(15):
            user_id = f"user{i % 3}"  # 3 users
            tool_name = ["search_web", "search_vectors"][i % 2]  # 2 tools
            
            request = {
                "method": "tools/call",
                "params": {"name": tool_name},
                "user": {"id": user_id}
            }
            await metrics_middleware(request, mock_call_next)
        
        metrics = await metrics_middleware.get_metrics_summary()
        
        # Check top users (should be limited to 10)
        assert len(metrics["top_users"]) <= 10
        assert all("user_id" in user for user in metrics["top_users"])
        assert all("request_count" in user for user in metrics["top_users"])
        
        # Check tool metrics
        assert len(metrics["tool_metrics"]) == 2
        assert "search_web" in metrics["tool_metrics"]
        assert "search_vectors" in metrics["tool_metrics"]
    
    @pytest.mark.asyncio
    async def test_recent_errors_tracking(self, metrics_middleware, mock_error_call_next):
        """Test recent errors tracking."""
        # Generate multiple errors
        for i in range(5):
            request = {
                "method": "tools/call",
                "params": {"name": f"tool_{i}"},
                "user": {"id": f"user_{i}"}
            }
            await metrics_middleware(request, mock_error_call_next)
        
        metrics = await metrics_middleware.get_metrics_summary()
        
        # Should have recent errors
        assert len(metrics["recent_errors"]) == 5
        for error in metrics["recent_errors"]:
            assert "timestamp" in error
            assert "method" in error
            assert "user_id" in error
            assert "error" in error
    
    @pytest.mark.asyncio
    async def test_reset_metrics(self, metrics_middleware, mock_call_next):
        """Test resetting metrics."""
        # Generate some metrics
        request = {
            "method": "tools/call",
            "params": {"name": "search_web"},
            "user": {"id": "user123"}
        }
        await metrics_middleware(request, mock_call_next)
        
        # Verify metrics exist
        metrics = await metrics_middleware.get_metrics_summary()
        assert metrics["summary"]["total_requests"] == 1
        
        # Reset metrics
        await metrics_middleware.reset_metrics()
        
        # Verify metrics are cleared
        metrics = await metrics_middleware.get_metrics_summary()
        assert metrics["summary"]["total_requests"] == 0
        assert metrics["summary"]["unique_users"] == 0
        assert len(metrics["tool_metrics"]) == 0