"""Rate limiting middleware for MCP server."""

from typing import Any, Callable, Dict, Optional
import time
import asyncio
from collections import defaultdict
import structlog
import redis.asyncio as redis

from ..utils.redis_rate_limiter import RedisRateLimiter

logger = structlog.get_logger(__name__)


class RateLimitMiddleware:
    """Rate limiting middleware to prevent abuse and ensure fair usage."""

    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        burst_size: int = 10,
        redis_client: Optional[redis.Redis] = None,
        use_sliding_window: bool = True,
    ):
        """Initialize rate limiting middleware.

        Args:
            requests_per_minute: Maximum requests per minute per user
            requests_per_hour: Maximum requests per hour per user
            burst_size: Maximum burst size for token bucket
            redis_client: Optional Redis client for distributed rate limiting
            use_sliding_window: Use Redis sliding window if available
        """
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.burst_size = burst_size
        self.redis_client = redis_client
        self.use_sliding_window = use_sliding_window

        # Redis rate limiter for distributed rate limiting
        self._redis_limiter: Optional[RedisRateLimiter] = None
        if redis_client and use_sliding_window:
            self._redis_limiter = RedisRateLimiter(
                redis_client=redis_client,
                window_seconds=60,  # 1 minute window
                default_limit=requests_per_minute,
            )

        # In-memory storage for fallback rate limiting
        self._request_counts: Dict[str, list[float]] = defaultdict(list)
        self._token_buckets: Dict[str, Dict[str, Any]] = {}

        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    async def __call__(
        self, request: Dict[str, Any], call_next: Callable
    ) -> Dict[str, Any]:
        """Apply rate limiting to incoming requests."""
        # Extract user identifier
        user = request.get("user", {})
        user_id = self._get_user_identifier(user)

        # Skip rate limiting for internal services
        if isinstance(user, dict) and user.get("type") == "service":
            return await call_next(request)

        # Check rate limits
        allowed, retry_after = await self._check_rate_limit(user_id)

        if not allowed:
            logger.warning(
                "Rate limit exceeded",
                user_id=user_id,
                method=request.get("method"),
                retry_after=retry_after,
            )
            return self._rate_limit_exceeded_response(retry_after)

        # Process request
        return await call_next(request)

    def _get_user_identifier(self, user: Any) -> str:
        """Extract user identifier for rate limiting."""
        if isinstance(user, dict):
            # Prefer user ID, fall back to email, then IP
            return str(
                user.get("id") or user.get("email") or user.get("ip", "anonymous")
            )
        return "anonymous"

    async def _check_rate_limit(self, user_id: str) -> tuple[bool, Optional[int]]:
        """Check if user has exceeded rate limits.

        Returns:
            Tuple of (allowed, retry_after_seconds)
        """
        if self._redis_limiter:
            # Use Redis sliding window rate limiter
            allowed, info = await self._redis_limiter.check_rate_limit(
                identifier=user_id, limit=self.requests_per_minute, weight=1
            )
            retry_after = info.get("retry_after", None) if not allowed else None
            return allowed, retry_after
        elif self.redis_client:
            return await self._check_redis_rate_limit(user_id)
        else:
            return await self._check_memory_rate_limit(user_id)

    async def _check_memory_rate_limit(
        self, user_id: str
    ) -> tuple[bool, Optional[int]]:
        """Check rate limit using in-memory storage."""
        async with self._lock:
            now = time.time()

            # Clean up old requests
            minute_ago = now - 60
            hour_ago = now - 3600

            # Get user's request history
            requests = self._request_counts[user_id]

            # Remove old entries
            requests[:] = [ts for ts in requests if ts > hour_ago]

            # Count recent requests
            minute_requests = sum(1 for ts in requests if ts > minute_ago)
            hour_requests = len(requests)

            # Check minute limit
            if minute_requests >= self.requests_per_minute:
                # Calculate retry after
                oldest_minute_request = min(ts for ts in requests if ts > minute_ago)
                retry_after = int(oldest_minute_request + 60 - now) + 1
                return False, retry_after

            # Check hour limit
            if hour_requests >= self.requests_per_hour:
                # Calculate retry after
                oldest_hour_request = min(requests)
                retry_after = int(oldest_hour_request + 3600 - now) + 1
                return False, retry_after

            # Check token bucket for burst control
            bucket = self._get_token_bucket(user_id)
            if bucket["tokens"] < 1:
                # Calculate when next token will be available
                time_per_token = 60 / self.requests_per_minute
                retry_after = int(time_per_token - (now - bucket["last_refill"]))
                return False, max(1, retry_after)

            # Request allowed - update counts and bucket
            requests.append(now)
            bucket["tokens"] -= 1

            return True, None

    def _get_token_bucket(self, user_id: str) -> Dict[str, Any]:
        """Get or create token bucket for user."""
        now = time.time()

        if user_id not in self._token_buckets:
            self._token_buckets[user_id] = {
                "tokens": self.burst_size,
                "last_refill": now,
            }

        bucket = self._token_buckets[user_id]

        # Refill tokens based on time elapsed
        time_elapsed = now - bucket["last_refill"]
        tokens_to_add = time_elapsed * (self.requests_per_minute / 60)

        if tokens_to_add > 0:
            bucket["tokens"] = min(self.burst_size, bucket["tokens"] + tokens_to_add)
            bucket["last_refill"] = now

        return bucket

    async def _check_redis_rate_limit(self, user_id: str) -> tuple[bool, Optional[int]]:
        """Check rate limit using Redis (for distributed systems)."""
        # This would implement Redis-based rate limiting
        # For now, fall back to memory-based
        return await self._check_memory_rate_limit(user_id)

    def _rate_limit_exceeded_response(self, retry_after: int) -> Dict[str, Any]:
        """Create rate limit exceeded response."""
        return {
            "error": {
                "code": -32603,
                "message": "Rate limit exceeded",
                "data": {
                    "type": "RateLimitError",
                    "retry_after": retry_after,
                    "retry_after_human": f"{retry_after} seconds",
                },
            }
        }

    async def get_usage_stats(self, user_id: str) -> Dict[str, Any]:
        """Get current usage statistics for a user."""
        if self._redis_limiter:
            # Use Redis rate limiter stats
            stats = await self._redis_limiter.get_usage_stats(identifier=user_id)
            return {
                "user_id": user_id,
                "minute_requests": stats.get("current_usage", 0),
                "minute_limit": self.requests_per_minute,
                "hour_requests": stats.get(
                    "current_usage", 0
                ),  # Redis tracks per window
                "hour_limit": self.requests_per_hour,
                "available_burst": self.burst_size - stats.get("current_usage", 0),
                "burst_limit": self.burst_size,
                "next_reset": stats.get("next_reset"),
                "time_until_reset": stats.get("time_until_reset"),
            }

        # Fallback to memory-based stats
        async with self._lock:
            now = time.time()
            minute_ago = now - 60
            hour_ago = now - 3600

            requests = self._request_counts.get(user_id, [])
            minute_requests = sum(1 for ts in requests if ts > minute_ago)
            hour_requests = sum(1 for ts in requests if ts > hour_ago)

            bucket = (
                self._get_token_bucket(user_id)
                if user_id in self._token_buckets
                else None
            )

            return {
                "user_id": user_id,
                "minute_requests": minute_requests,
                "minute_limit": self.requests_per_minute,
                "hour_requests": hour_requests,
                "hour_limit": self.requests_per_hour,
                "available_burst": bucket["tokens"] if bucket else self.burst_size,
                "burst_limit": self.burst_size,
            }
