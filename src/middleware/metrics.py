"""Metrics collection middleware for MCP server."""

from typing import Any, Callable, Dict, Optional
import time
from datetime import datetime
from collections import defaultdict
import asyncio
import structlog

logger = structlog.get_logger(__name__)


class MetricsMiddleware:
    """Middleware for collecting performance metrics and usage statistics."""

    def __init__(
        self, enable_detailed_metrics: bool = True, metrics_window_seconds: int = 3600
    ):
        """Initialize metrics middleware.

        Args:
            enable_detailed_metrics: Whether to collect detailed per-tool metrics
            metrics_window_seconds: Time window for metrics aggregation
        """
        self.enable_detailed_metrics = enable_detailed_metrics
        self.metrics_window_seconds = metrics_window_seconds

        # Metrics storage
        self._request_count = 0
        self._error_count = 0
        self._tool_metrics: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "count": 0,
                "errors": 0,
                "total_duration_ms": 0,
                "min_duration_ms": float("inf"),
                "max_duration_ms": 0,
                "avg_duration_ms": 0,
            }
        )

        self._user_metrics: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "request_count": 0,
                "error_count": 0,
                "tool_usage": defaultdict(int),
                "last_request_at": None,
            }
        )

        self._response_time_buckets = [10, 50, 100, 250, 500, 1000, 2500, 5000]
        self._response_time_histogram = defaultdict(int)

        # Recent errors for debugging
        self._recent_errors: list[Dict[str, Any]] = []
        self._max_recent_errors = 100

        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    async def __call__(
        self, request: Dict[str, Any], call_next: Callable
    ) -> Dict[str, Any]:
        """Collect metrics for incoming requests."""
        start_time = time.time()

        # Extract request information
        method = request.get("method", "unknown")
        user = request.get("user", {})
        user_id = self._get_user_identifier(user)
        tool_name = None

        if method == "tools/call":
            params = request.get("params", {})
            tool_name = params.get("name") if isinstance(params, dict) else None

        # Process request
        error_occurred = False
        error_details = None

        try:
            response = await call_next(request)

            # Check for errors in response
            if isinstance(response, dict) and "error" in response:
                error_occurred = True
                error_details = response["error"]

            return response

        except Exception as e:
            error_occurred = True
            error_details = str(e)
            raise

        finally:
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Update metrics
            await self._update_metrics(
                method=method,
                tool_name=tool_name,
                user_id=user_id,
                duration_ms=duration_ms,
                error_occurred=error_occurred,
                error_details=error_details,
            )

    def _get_user_identifier(self, user: Any) -> str:
        """Extract user identifier for metrics."""
        if isinstance(user, dict):
            if user.get("type") == "service":
                return f"service:{user.get('service', 'unknown')}"
            return str(user.get("id") or user.get("email", "anonymous"))
        return "anonymous"

    async def _update_metrics(
        self,
        method: str,
        tool_name: Optional[str],
        user_id: str,
        duration_ms: float,
        error_occurred: bool,
        error_details: Any,
    ):
        """Update metrics with request information."""
        async with self._lock:
            # Update global counters
            self._request_count += 1
            if error_occurred:
                self._error_count += 1

            # Update response time histogram
            for bucket in self._response_time_buckets:
                if duration_ms <= bucket:
                    self._response_time_histogram[bucket] += 1
                    break
            else:
                self._response_time_histogram["inf"] += 1

            # Update tool metrics if applicable
            if tool_name and self.enable_detailed_metrics:
                tool_stats = self._tool_metrics[tool_name]
                tool_stats["count"] += 1
                if error_occurred:
                    tool_stats["errors"] += 1

                tool_stats["total_duration_ms"] += duration_ms
                tool_stats["min_duration_ms"] = min(
                    tool_stats["min_duration_ms"], duration_ms
                )
                tool_stats["max_duration_ms"] = max(
                    tool_stats["max_duration_ms"], duration_ms
                )
                tool_stats["avg_duration_ms"] = (
                    tool_stats["total_duration_ms"] / tool_stats["count"]
                )

            # Update user metrics
            user_stats = self._user_metrics[user_id]
            user_stats["request_count"] += 1
            if error_occurred:
                user_stats["error_count"] += 1
            if tool_name:
                user_stats["tool_usage"][tool_name] += 1
            user_stats["last_request_at"] = datetime.utcnow().isoformat()

            # Track recent errors
            if error_occurred and error_details:
                error_record = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "method": method,
                    "tool_name": tool_name,
                    "user_id": user_id,
                    "duration_ms": duration_ms,
                    "error": error_details,
                }
                self._recent_errors.append(error_record)

                # Keep only recent errors
                if len(self._recent_errors) > self._max_recent_errors:
                    self._recent_errors = self._recent_errors[
                        -self._max_recent_errors :
                    ]

    async def get_metrics_summary(self) -> Dict[str, Any]:
        """Get current metrics summary."""
        async with self._lock:
            # Calculate success rate
            success_rate = (
                ((self._request_count - self._error_count) / self._request_count * 100)
                if self._request_count > 0
                else 0
            )

            # Get top tools by usage
            top_tools = sorted(
                self._tool_metrics.items(), key=lambda x: x[1]["count"], reverse=True
            )[:10]

            # Get most active users
            active_users = sorted(
                self._user_metrics.items(),
                key=lambda x: x[1]["request_count"],
                reverse=True,
            )[:10]

            return {
                "summary": {
                    "total_requests": self._request_count,
                    "total_errors": self._error_count,
                    "success_rate": f"{success_rate:.2f}%",
                    "unique_users": len(self._user_metrics),
                },
                "response_time_distribution": dict(self._response_time_histogram),
                "tool_metrics": {name: stats for name, stats in top_tools},
                "top_users": [
                    {
                        "user_id": user_id,
                        "request_count": stats["request_count"],
                        "error_count": stats["error_count"],
                        "last_request_at": stats["last_request_at"],
                    }
                    for user_id, stats in active_users
                ],
                "recent_errors": self._recent_errors[-10:],  # Last 10 errors
            }

    async def get_tool_metrics(self, tool_name: str) -> Dict[str, Any]:
        """Get metrics for a specific tool."""
        async with self._lock:
            return dict(
                self._tool_metrics.get(
                    tool_name,
                    {
                        "count": 0,
                        "errors": 0,
                        "total_duration_ms": 0,
                        "min_duration_ms": 0,
                        "max_duration_ms": 0,
                        "avg_duration_ms": 0,
                    },
                )
            )

    async def get_user_metrics(self, user_id: str) -> Dict[str, Any]:
        """Get metrics for a specific user."""
        async with self._lock:
            stats = self._user_metrics.get(user_id, {})
            return {
                "user_id": user_id,
                "request_count": stats.get("request_count", 0),
                "error_count": stats.get("error_count", 0),
                "tool_usage": dict(stats.get("tool_usage", {})),
                "last_request_at": stats.get("last_request_at"),
            }

    async def reset_metrics(self):
        """Reset all metrics (useful for testing)."""
        async with self._lock:
            self._request_count = 0
            self._error_count = 0
            self._tool_metrics.clear()
            self._user_metrics.clear()
            self._response_time_histogram.clear()
            self._recent_errors.clear()

            logger.info("Metrics reset completed")
