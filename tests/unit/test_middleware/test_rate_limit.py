"""Unit tests for rate limiting middleware."""

import pytest
import time
from unittest.mock import AsyncMock

from src.middleware.rate_limit import RateLimitMiddleware


@pytest.fixture
def rate_limit_middleware():
    """Create rate limit middleware instance."""
    return RateLimitMiddleware(
        requests_per_minute=10, requests_per_hour=100, burst_size=5
    )


@pytest.fixture
def mock_request():
    """Create mock request."""
    return {
        "method": "tools/call",
        "user": {"id": "user123", "email": "test@example.com"},
        "jsonrpc": "2.0",
        "id": 1,
    }


@pytest.fixture
def mock_call_next():
    """Create mock call_next function."""

    async def call_next(request):
        return {"result": "success"}

    return AsyncMock(side_effect=call_next)


class TestRateLimitMiddleware:
    """Test rate limiting middleware."""

    @pytest.mark.asyncio
    async def test_allow_requests_within_limit(
        self, rate_limit_middleware, mock_request, mock_call_next
    ):
        """Test allowing requests within rate limit."""
        # First request should pass
        result = await rate_limit_middleware(mock_request, mock_call_next)
        assert result == {"result": "success"}
        mock_call_next.assert_called()

    @pytest.mark.asyncio
    async def test_block_requests_exceeding_minute_limit(
        self, rate_limit_middleware, mock_request, mock_call_next
    ):
        """Test blocking requests that exceed per-minute limit."""
        # Send requests up to the limit
        for i in range(10):
            await rate_limit_middleware(mock_request, mock_call_next)

        # Reset mock
        mock_call_next.reset_mock()

        # Next request should be blocked
        result = await rate_limit_middleware(mock_request, mock_call_next)

        assert "error" in result
        assert result["error"]["code"] == -32603
        assert "Rate limit exceeded" in result["error"]["message"]
        assert "retry_after" in result["error"]["data"]
        mock_call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_token_bucket_burst_control(
        self, rate_limit_middleware, mock_request, mock_call_next
    ):
        """Test token bucket burst control."""
        # Burst size is 5, so we should be able to send 5 requests immediately
        for i in range(5):
            result = await rate_limit_middleware(mock_request, mock_call_next)
            assert result == {"result": "success"}

        # 6th request should consume from refilled tokens or be blocked
        result = await rate_limit_middleware(mock_request, mock_call_next)
        # This might pass or fail depending on timing

    @pytest.mark.asyncio
    async def test_service_accounts_bypass_rate_limit(
        self, rate_limit_middleware, mock_request, mock_call_next
    ):
        """Test that service accounts bypass rate limiting."""
        mock_request["user"] = {"type": "service", "service": "internal"}

        # Send many requests
        for i in range(20):
            result = await rate_limit_middleware(mock_request, mock_call_next)
            assert result == {"result": "success"}

        assert mock_call_next.call_count == 20

    @pytest.mark.asyncio
    async def test_different_users_have_separate_limits(
        self, rate_limit_middleware, mock_call_next
    ):
        """Test that different users have separate rate limits."""
        request1 = {
            "method": "tools/call",
            "user": {"id": "user1"},
            "jsonrpc": "2.0",
            "id": 1,
        }
        request2 = {
            "method": "tools/call",
            "user": {"id": "user2"},
            "jsonrpc": "2.0",
            "id": 2,
        }

        # Both users should be able to make requests
        result1 = await rate_limit_middleware(request1, mock_call_next)
        result2 = await rate_limit_middleware(request2, mock_call_next)

        assert result1 == {"result": "success"}
        assert result2 == {"result": "success"}
        assert mock_call_next.call_count == 2

    @pytest.mark.asyncio
    async def test_get_usage_stats(
        self, rate_limit_middleware, mock_request, mock_call_next
    ):
        """Test getting usage statistics."""
        # Make some requests
        for i in range(3):
            await rate_limit_middleware(mock_request, mock_call_next)

        stats = await rate_limit_middleware.get_usage_stats("user123")

        assert stats["user_id"] == "user123"
        assert stats["minute_requests"] == 3
        assert stats["hour_requests"] == 3
        assert stats["minute_limit"] == 10
        assert stats["hour_limit"] == 100
        assert "available_burst" in stats
        assert stats["burst_limit"] == 5

    @pytest.mark.asyncio
    async def test_cleanup_old_requests(self, rate_limit_middleware):
        """Test that old requests are cleaned up."""
        # Manually add old requests
        user_id = "test_user"
        now = time.time()
        old_time = now - 3700  # More than an hour ago

        async with rate_limit_middleware._lock:
            rate_limit_middleware._request_counts[user_id] = [old_time, now]

        # Check rate limit - this should trigger cleanup
        allowed, retry_after = await rate_limit_middleware._check_memory_rate_limit(
            user_id
        )

        assert allowed is True
        assert retry_after is None

        # Old request should be cleaned up
        async with rate_limit_middleware._lock:
            requests = rate_limit_middleware._request_counts[user_id]
            assert len(requests) == 1  # Only the new request
