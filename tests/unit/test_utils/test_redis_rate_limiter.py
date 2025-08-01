"""Unit tests for Redis-based rate limiter."""

import pytest
import time
import asyncio
from unittest.mock import AsyncMock
import redis.asyncio as redis

from src.utils.redis_rate_limiter import RedisRateLimiter


class TestRedisRateLimiter:
    """Test Redis-based sliding window rate limiter."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        mock = AsyncMock(spec=redis.Redis)
        mock.script_load = AsyncMock(return_value="test_sha")
        mock.evalsha = AsyncMock()
        mock.zremrangebyscore = AsyncMock()
        mock.zrange = AsyncMock(return_value=[])
        mock.delete = AsyncMock()
        mock.zcard = AsyncMock(return_value=0)
        mock.scan = AsyncMock(return_value=(0, []))
        return mock

    @pytest.fixture
    def rate_limiter(self, mock_redis):
        """Create rate limiter with mock Redis."""
        return RedisRateLimiter(
            redis_client=mock_redis, window_seconds=60, default_limit=10
        )

    @pytest.mark.asyncio
    async def test_check_rate_limit_allowed(self, rate_limiter, mock_redis):
        """Test rate limit check when request is allowed."""
        # Mock Lua script result: [allowed, current_usage, retry_after]
        mock_redis.evalsha.return_value = [1, 5, 0]

        allowed, info = await rate_limiter.check_rate_limit(
            identifier="user123", limit=10, weight=1
        )

        assert allowed is True
        assert info["allowed"] is True
        assert info["current_usage"] == 5
        assert info["limit"] == 10
        assert info["remaining"] == 5
        assert info["retry_after"] == 0

        # Verify Lua script was called
        mock_redis.evalsha.assert_called_once()
        args = mock_redis.evalsha.call_args[0]
        assert args[0] == "test_sha"  # script SHA
        assert args[1] == 1  # number of keys
        assert args[2] == "rate_limit:user123"  # key

    @pytest.mark.asyncio
    async def test_check_rate_limit_exceeded(self, rate_limiter, mock_redis):
        """Test rate limit check when limit is exceeded."""
        # Mock Lua script result: limit exceeded
        mock_redis.evalsha.return_value = [0, 10, 30]  # 30 seconds retry

        allowed, info = await rate_limiter.check_rate_limit(
            identifier="user123", limit=10
        )

        assert allowed is False
        assert info["allowed"] is False
        assert info["current_usage"] == 10
        assert info["limit"] == 10
        assert info["remaining"] == 0
        assert info["retry_after"] == 30

    @pytest.mark.asyncio
    async def test_check_rate_limit_with_endpoint(self, rate_limiter, mock_redis):
        """Test rate limit with endpoint-specific key."""
        mock_redis.evalsha.return_value = [1, 2, 0]

        allowed, info = await rate_limiter.check_rate_limit(
            identifier="user123", endpoint="search_web", weight=2
        )

        assert allowed is True
        assert info["endpoint"] == "search_web"
        assert info["weight"] == 2

        # Check the key includes endpoint
        args = mock_redis.evalsha.call_args[0]
        assert args[2] == "rate_limit:user123:search_web"

    @pytest.mark.asyncio
    async def test_check_rate_limit_redis_error(self, rate_limiter, mock_redis):
        """Test graceful degradation on Redis error."""
        mock_redis.evalsha.side_effect = redis.RedisError("Connection failed")

        allowed, info = await rate_limiter.check_rate_limit("user123")

        # Should allow request on error (graceful degradation)
        assert allowed is True
        assert info["allowed"] is True
        assert info["degraded"] is True
        assert "error" in info

    @pytest.mark.asyncio
    async def test_get_usage_stats(self, rate_limiter, mock_redis):
        """Test getting usage statistics."""
        current_time = time.time()

        # Mock Redis responses
        mock_redis.zrange.return_value = [
            ("req1", current_time - 30),  # 30 seconds ago
            ("req2", current_time - 10),  # 10 seconds ago
            ("req3", current_time - 5),  # 5 seconds ago
        ]

        stats = await rate_limiter.get_usage_stats("user123")

        # Weight calculation - each request has weight 1
        # But we need to fix the test since timestamps don't include weight info
        assert stats["current_usage"] == 3  # 3 requests with weight 1 each
        assert stats["request_count"] == 3
        assert stats["window_seconds"] == 60
        assert "next_reset" in stats
        assert "time_until_reset" in stats

        # Verify cleanup was called
        mock_redis.zremrangebyscore.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_usage_stats_with_weights(self, rate_limiter, mock_redis):
        """Test usage stats with weighted requests."""
        current_time = time.time()

        # Mock Redis responses with weights
        # Score format: timestamp.weight (weight as decimal part * 1000)
        mock_redis.zrange.return_value = [
            ("req1", current_time - 30 + 0.002),  # weight 2
            ("req2", current_time - 10 + 0.003),  # weight 3
            ("req3", current_time - 5 + 0.001),  # weight 1
        ]

        stats = await rate_limiter.get_usage_stats("user123")

        assert stats["current_usage"] == 6  # 2 + 3 + 1 = 6
        assert stats["request_count"] == 3

    @pytest.mark.asyncio
    async def test_reset_limit(self, rate_limiter, mock_redis):
        """Test resetting rate limit for a user."""
        result = await rate_limiter.reset_limit("user123")

        assert result is True
        mock_redis.delete.assert_called_once_with("rate_limit:user123")

    @pytest.mark.asyncio
    async def test_reset_limit_with_endpoint(self, rate_limiter, mock_redis):
        """Test resetting rate limit for specific endpoint."""
        result = await rate_limiter.reset_limit("user123", "search_web")

        assert result is True
        mock_redis.delete.assert_called_once_with("rate_limit:user123:search_web")

    @pytest.mark.asyncio
    async def test_cleanup_expired(self, rate_limiter, mock_redis):
        """Test cleanup of expired rate limit data."""
        # Mock SCAN results
        mock_redis.scan = AsyncMock()
        mock_redis.scan.side_effect = [
            (100, ["rate_limit:user1", "rate_limit:user2"]),
            (0, ["rate_limit:user3"]),
        ]

        # Mock ZCARD results
        mock_redis.zcard.side_effect = [
            0,
            1,
            0,
        ]  # user1: empty, user2: has data, user3: empty

        # Mock ZRANGE for checking newest timestamp
        current_time = time.time()
        mock_redis.zrange.return_value = [
            (("req", current_time - 120),)
        ]  # 2 minutes old

        cleaned = await rate_limiter.cleanup_expired()

        assert cleaned == 3  # user1, user2 (old), and user3 deleted
        assert mock_redis.delete.call_count == 3

    @pytest.mark.asyncio
    async def test_custom_window_size(self, rate_limiter, mock_redis):
        """Test using custom window size."""
        mock_redis.evalsha.return_value = [1, 5, 0]

        allowed, info = await rate_limiter.check_rate_limit(
            identifier="user123",
            window_seconds=300,  # 5 minutes
        )

        assert allowed is True
        assert info["window_seconds"] == 300

        # Check window parameter in Lua script
        args = mock_redis.evalsha.call_args[0]
        assert args[4] == "300"  # ARGV[2] is window

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, rate_limiter, mock_redis):
        """Test handling concurrent rate limit checks."""
        # Simulate multiple concurrent requests
        mock_redis.evalsha.side_effect = [
            [1, 1, 0],  # First request allowed
            [1, 2, 0],  # Second request allowed
            [1, 3, 0],  # Third request allowed
            [0, 4, 10],  # Fourth request denied
        ]

        # Run concurrent checks
        results = await asyncio.gather(
            rate_limiter.check_rate_limit("user123", limit=3),
            rate_limiter.check_rate_limit("user123", limit=3),
            rate_limiter.check_rate_limit("user123", limit=3),
            rate_limiter.check_rate_limit("user123", limit=3),
        )

        # First 3 should be allowed, 4th denied
        assert results[0][0] is True
        assert results[1][0] is True
        assert results[2][0] is True
        assert results[3][0] is False
        assert results[3][1]["retry_after"] == 10
