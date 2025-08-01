"""
Connection pool and client manager for optimized resource utilization.

This module provides centralized management for database connections,
vector database clients, and HTTP sessions to improve performance
and resource efficiency.

Key features:
- PostgreSQL connection pool with dynamic sizing
- Qdrant client singleton pattern
- HTTP session pool with connection reuse
- Comprehensive metrics and monitoring
- Automatic pool adjustment based on load
"""

import asyncio
import time
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import statistics

import asyncpg
from asyncpg import Pool
import httpx
from qdrant_client import QdrantClient
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ConnectionPoolMetrics:
    """Metrics for monitoring connection pool performance."""

    total_connections: int = 0
    active_connections: int = 0
    idle_connections: int = 0
    connection_errors: int = 0
    total_requests: int = 0
    pool_exhausted_count: int = 0
    connection_wait_time_ms: List[float] = field(default_factory=list)
    reuse_rate: float = 0.0

    def record_connection_acquired(self, wait_time_ms: float) -> None:
        """Record a connection acquisition."""
        self.active_connections += 1
        self.total_requests += 1
        self.connection_wait_time_ms.append(wait_time_ms)
        if len(self.connection_wait_time_ms) > 1000:  # Keep last 1000 samples
            self.connection_wait_time_ms = self.connection_wait_time_ms[-1000:]

    def record_connection_released(self) -> None:
        """Record a connection release."""
        self.active_connections = max(0, self.active_connections - 1)
        self.idle_connections = self.total_connections - self.active_connections

    def record_connection_error(self) -> None:
        """Record a connection error."""
        self.connection_errors += 1

    def calculate_reuse_rate(self) -> float:
        """Calculate connection reuse rate as percentage."""
        if self.total_requests == 0:
            return 0.0

        # Reuse rate = (requests - new connections) / requests * 100
        new_connections = self.total_connections
        reused_connections = max(0, self.total_requests - new_connections)
        self.reuse_rate = (reused_connections / self.total_requests) * 100
        return self.reuse_rate

    def get_avg_wait_time(self) -> float:
        """Get average connection wait time in milliseconds."""
        if not self.connection_wait_time_ms:
            return 0.0
        return statistics.mean(self.connection_wait_time_ms)

    def get_p95_wait_time(self) -> float:
        """Get 95th percentile connection wait time."""
        if not self.connection_wait_time_ms:
            return 0.0
        return statistics.quantiles(self.connection_wait_time_ms, n=20)[18]


class PostgreSQLPoolManager:
    """Manages PostgreSQL connection pool with dynamic sizing."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize PostgreSQL pool manager."""
        self.dsn = config["dsn"]
        self.min_size = config.get("min_size", 10)
        self.max_size = config.get("max_size", 50)
        self.timeout = config.get("timeout", 30)
        self.command_timeout = config.get("command_timeout", 10)
        self.max_queries = config.get("max_queries", 50000)
        self.max_inactive_connection_lifetime = config.get(
            "max_inactive_connection_lifetime", 300
        )

        self._pool: Optional[Pool] = None
        self._lock = asyncio.Lock()
        self.metrics = ConnectionPoolMetrics()

        logger.info(
            "PostgreSQL pool manager initialized",
            min_size=self.min_size,
            max_size=self.max_size,
        )

    async def initialize(self) -> None:
        """Initialize the connection pool."""
        async with self._lock:
            if self._pool is not None:
                return

            try:
                self._pool = await asyncpg.create_pool(
                    self.dsn,
                    min_size=self.min_size,
                    max_size=self.max_size,
                    timeout=self.timeout,
                    command_timeout=self.command_timeout,
                    max_queries=self.max_queries,
                    max_inactive_connection_lifetime=self.max_inactive_connection_lifetime,
                )

                self.metrics.total_connections = self._pool.get_size()
                self.metrics.idle_connections = self._pool.get_idle_size()

                logger.info(
                    "PostgreSQL pool created successfully",
                    pool_size=self._pool.get_size(),
                )

            except Exception as e:
                logger.error("Failed to create PostgreSQL pool", error=str(e))
                raise

    @asynccontextmanager
    async def acquire(self):
        """Acquire a connection from the pool with metrics tracking."""
        if self._pool is None:
            await self.initialize()

        start_time = time.time()
        connection = None

        try:
            connection = await self._pool.acquire()
            wait_time_ms = (time.time() - start_time) * 1000
            self.metrics.record_connection_acquired(wait_time_ms)

            yield connection

        except asyncpg.exceptions.TooManyConnectionsError:
            self.metrics.pool_exhausted_count += 1
            self.metrics.record_connection_error()
            logger.warning("PostgreSQL connection pool exhausted")
            raise
        except Exception as e:
            self.metrics.record_connection_error()
            logger.error("Error acquiring PostgreSQL connection", error=str(e))
            raise
        finally:
            if connection:
                await self._pool.release(connection)
                self.metrics.record_connection_released()

    async def adjust_pool_size(self) -> None:
        """Dynamically adjust pool size based on load."""
        if self._pool is None:
            return

        utilization = self.metrics.active_connections / self.metrics.total_connections
        current_size = self._pool.get_size()

        # High utilization (>80%): increase pool size
        if utilization > 0.8 and current_size < self.max_size:
            new_min = min(current_size + 5, self.max_size)
            await self._pool.set_pool_size(min_size=new_min, max_size=self.max_size)
            logger.info("Increased PostgreSQL pool size", new_size=new_min)

        # Low utilization (<20%): decrease pool size
        elif utilization < 0.2 and current_size > self.min_size:
            new_max = max(current_size - 5, self.min_size)
            await self._pool.set_pool_size(min_size=self.min_size, max_size=new_max)
            logger.info("Decreased PostgreSQL pool size", new_size=new_max)

        self.metrics.total_connections = self._pool.get_size()

    async def health_check(self) -> Dict[str, Any]:
        """Check pool health and return metrics."""
        if self._pool is None:
            return {"status": "not_initialized"}

        try:
            # Test connection
            async with self.acquire() as conn:
                await conn.fetchval("SELECT 1")

            return {
                "status": "healthy",
                "pool_size": self._pool.get_size(),
                "idle_connections": self._pool.get_idle_size(),
                "active_connections": self.metrics.active_connections,
                "total_requests": self.metrics.total_requests,
                "reuse_rate": self.metrics.calculate_reuse_rate(),
                "avg_wait_time_ms": self.metrics.get_avg_wait_time(),
                "p95_wait_time_ms": self.metrics.get_p95_wait_time(),
                "error_rate": (
                    self.metrics.connection_errors / max(1, self.metrics.total_requests)
                )
                * 100,
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "error_count": self.metrics.connection_errors,
            }

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("PostgreSQL pool closed")


class QdrantClientManager:
    """Manages Qdrant client as a singleton with health monitoring."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize Qdrant client manager."""
        self.host = config["host"]
        self.port = config.get("port", 6333)
        self.grpc_port = config.get("grpc_port", 6334)
        self.api_key = config.get("api_key")
        self.timeout = config.get("timeout", 30)
        self.prefer_grpc = config.get("prefer_grpc", True)

        self._client: Optional[QdrantClient] = None
        self._lock = asyncio.Lock()
        self.metrics = ConnectionPoolMetrics()

        logger.info(
            "Qdrant client manager initialized",
            host=self.host,
            prefer_grpc=self.prefer_grpc,
        )

    async def get_client(self) -> QdrantClient:
        """Get or create the singleton Qdrant client."""
        async with self._lock:
            if self._client is None:
                try:
                    self._client = QdrantClient(
                        host=self.host,
                        port=self.grpc_port if self.prefer_grpc else self.port,
                        api_key=self.api_key,
                        timeout=self.timeout,
                        grpc_options={
                            "grpc.max_receive_message_length": 100 * 1024 * 1024
                        }  # 100MB
                        if self.prefer_grpc
                        else None,
                    )

                    self.metrics.total_connections += 1
                    logger.info("Qdrant client created successfully")

                except Exception as e:
                    self.metrics.record_connection_error()
                    logger.error("Failed to create Qdrant client", error=str(e))
                    raise

        self.metrics.total_requests += 1
        return self._client

    async def health_check(self) -> Dict[str, Any]:
        """Check Qdrant client health."""
        try:
            client = await self.get_client()
            # Test connection
            collections_info = client.get_collections()

            return {
                "status": "healthy"
                if self.metrics.connection_errors == 0
                else "reconnected",
                "collections_count": len(collections_info.collections),
                "total_requests": self.metrics.total_requests,
                "connection_errors": self.metrics.connection_errors,
                "reuse_rate": self.metrics.calculate_reuse_rate(),
            }
        except Exception:
            # Try to reconnect
            async with self._lock:
                self._client = None
                self.metrics.record_connection_error()

            try:
                # Attempt reconnection
                client = await self.get_client()
                return {
                    "status": "reconnected",
                    "previous_errors": self.metrics.connection_errors,
                    "message": "Client reconnected after error",
                }
            except Exception as reconnect_error:
                return {
                    "status": "unhealthy",
                    "error": str(reconnect_error),
                    "error_count": self.metrics.connection_errors,
                }

    async def close(self) -> None:
        """Close the Qdrant client."""
        if self._client:
            # Qdrant client doesn't have explicit close method
            self._client = None
            logger.info("Qdrant client closed")


class HTTPSessionManager:
    """Manages HTTP session pool for efficient connection reuse."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize HTTP session manager."""
        self.max_connections = config.get("max_connections", 100)
        self.max_keepalive_connections = config.get("max_keepalive_connections", 20)
        self.keepalive_expiry = config.get("keepalive_expiry", 30)
        self.timeout = config.get("timeout", 30)
        self.retries = config.get("retries", 3)

        self._client: Optional[httpx.AsyncClient] = None
        self._limits = httpx.Limits(
            max_connections=self.max_connections,
            max_keepalive_connections=self.max_keepalive_connections,
            keepalive_expiry=self.keepalive_expiry,
        )
        self._lock = asyncio.Lock()
        self.metrics = ConnectionPoolMetrics()

        logger.info(
            "HTTP session manager initialized", max_connections=self.max_connections
        )

    async def initialize(self) -> None:
        """Initialize the HTTP client."""
        async with self._lock:
            if self._client is not None:
                return

            self._client = httpx.AsyncClient(
                limits=self._limits,
                timeout=httpx.Timeout(self.timeout),
                transport=httpx.AsyncHTTPTransport(retries=self.retries),
            )

            self.metrics.total_connections = 1
            logger.info("HTTP client created successfully")

    @asynccontextmanager
    async def session(self):
        """Get HTTP session for making requests."""
        if self._client is None:
            await self.initialize()

        start_time = time.time()
        self.metrics.total_requests += 1

        try:
            wait_time_ms = (time.time() - start_time) * 1000
            self.metrics.record_connection_acquired(wait_time_ms)

            yield self._client

        except httpx.ConnectError:
            self.metrics.record_connection_error()
            logger.warning("HTTP connection error")
            raise
        except Exception as e:
            self.metrics.record_connection_error()
            logger.error("HTTP request error", error=str(e))
            raise
        finally:
            self.metrics.record_connection_released()

    async def health_check(self) -> Dict[str, Any]:
        """Check HTTP session health."""
        try:
            async with self.session() as session:
                # Test with a simple HEAD request to httpbin
                response = await session.head("https://httpbin.org/status/200")
                response.raise_for_status()

            return {
                "status": "healthy",
                "total_requests": self.metrics.total_requests,
                "connection_errors": self.metrics.connection_errors,
                "reuse_rate": self.metrics.calculate_reuse_rate(),
                "avg_wait_time_ms": self.metrics.get_avg_wait_time(),
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "error_count": self.metrics.connection_errors,
            }

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("HTTP client closed")


class ConnectionManager:
    """Unified connection manager for all external services."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize unified connection manager."""
        self.config = config

        # Initialize individual managers
        self.postgresql: Optional[PostgreSQLPoolManager] = None
        self.qdrant: Optional[QdrantClientManager] = None
        self.http: Optional[HTTPSessionManager] = None

        if "postgresql" in config:
            self.postgresql = PostgreSQLPoolManager(config["postgresql"])

        if "qdrant" in config:
            self.qdrant = QdrantClientManager(config["qdrant"])

        if "http" in config:
            self.http = HTTPSessionManager(config["http"])

        logger.info("Connection manager initialized")

    async def initialize_all(self) -> None:
        """Initialize all connection managers."""
        tasks = []

        if self.postgresql:
            tasks.append(self.postgresql.initialize())

        if self.http:
            tasks.append(self.http.initialize())

        # Qdrant doesn't need explicit initialization

        if tasks:
            await asyncio.gather(*tasks)

        logger.info("All connections initialized")

    async def get_all_metrics(self) -> Dict[str, Any]:
        """Get aggregated metrics from all managers."""
        metrics = {}
        total_requests = 0
        total_errors = 0

        if self.postgresql:
            metrics["postgresql"] = {
                "total_requests": self.postgresql.metrics.total_requests,
                "active_connections": self.postgresql.metrics.active_connections,
                "reuse_rate": self.postgresql.metrics.calculate_reuse_rate(),
                "errors": self.postgresql.metrics.connection_errors,
            }
            total_requests += self.postgresql.metrics.total_requests
            total_errors += self.postgresql.metrics.connection_errors

        if self.qdrant:
            metrics["qdrant"] = {
                "total_requests": self.qdrant.metrics.total_requests,
                "reuse_rate": self.qdrant.metrics.calculate_reuse_rate(),
                "errors": self.qdrant.metrics.connection_errors,
            }
            total_requests += self.qdrant.metrics.total_requests
            total_errors += self.qdrant.metrics.connection_errors

        if self.http:
            metrics["http"] = {
                "total_requests": self.http.metrics.total_requests,
                "active_connections": self.http.metrics.active_connections,
                "reuse_rate": self.http.metrics.calculate_reuse_rate(),
                "errors": self.http.metrics.connection_errors,
            }
            total_requests += self.http.metrics.total_requests
            total_errors += self.http.metrics.connection_errors

        metrics["total_requests"] = total_requests
        metrics["total_errors"] = total_errors
        metrics["overall_error_rate"] = (total_errors / max(1, total_requests)) * 100

        return metrics

    async def health_check_all(self) -> Dict[str, Any]:
        """Perform health check on all connections."""
        health = {}

        if self.postgresql:
            health["postgresql"] = await self.postgresql.health_check()

        if self.qdrant:
            health["qdrant"] = await self.qdrant.health_check()

        if self.http:
            health["http"] = await self.http.health_check()

        # Overall health
        all_healthy = all(
            status.get("status") in ["healthy", "reconnected"]
            for status in health.values()
        )

        health["overall_status"] = "healthy" if all_healthy else "degraded"

        return health

    async def cleanup_all(self) -> None:
        """Clean up all connections."""
        tasks = []

        if self.postgresql:
            tasks.append(self.postgresql.close())

        if self.qdrant:
            tasks.append(self.qdrant.close())

        if self.http:
            tasks.append(self.http.close())

        if tasks:
            await asyncio.gather(*tasks)

        logger.info("All connections cleaned up")


# Global connection manager instance
_connection_manager: Optional[ConnectionManager] = None


def get_connection_manager() -> ConnectionManager:
    """Get the global connection manager instance."""
    global _connection_manager
    if _connection_manager is None:
        raise RuntimeError(
            "Connection manager not initialized. Call init_connection_manager first."
        )
    return _connection_manager


async def init_connection_manager(config: Dict[str, Any]) -> ConnectionManager:
    """Initialize the global connection manager."""
    global _connection_manager
    _connection_manager = ConnectionManager(config)
    await _connection_manager.initialize_all()
    return _connection_manager
