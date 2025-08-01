"""JWT token management with automatic refresh mechanism.

This module provides comprehensive JWT token management including:
- Access and refresh token generation
- Automatic token refresh before expiry
- Refresh token storage and validation
- Background refresh tasks
- Concurrent refresh prevention
"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
import jwt
import redis.asyncio as redis
import httpx
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class TokenPair:
    """Represents an access and refresh token pair."""

    access_token: str
    refresh_token: str
    expires_in: int  # seconds
    refresh_expires_in: int  # seconds


class TokenRefreshError(Exception):
    """Raised when token refresh fails."""

    pass


class RefreshTokenStore:
    """Manages refresh token storage and validation using Redis."""

    def __init__(self, redis_url: str, token_ttl: int = 86400 * 7):
        """Initialize refresh token store.

        Args:
            redis_url: Redis connection URL
            token_ttl: Token TTL in seconds (default: 7 days)
        """
        self.redis_url = redis_url
        self.token_ttl = token_ttl
        self._redis: Optional[redis.Redis] = None

    async def connect(self):
        """Connect to Redis."""
        if self._redis is None:
            self._redis = await redis.from_url(self.redis_url)

    async def disconnect(self):
        """Disconnect from Redis."""
        if self._redis:
            await self._redis.close()
            self._redis = None

    async def store_token(
        self,
        user_id: str,
        refresh_token: str,
        device_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store refresh token with metadata.

        Args:
            user_id: User ID
            refresh_token: Refresh token
            device_id: Device identifier
            metadata: Additional metadata (IP, user agent, etc.)
        """
        await self.connect()

        key = f"refresh_token:{user_id}:{device_id}"
        value = {
            "token": refresh_token,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "device_id": device_id,
            "metadata": metadata or {},
        }

        await self._redis.setex(key, self.token_ttl, json.dumps(value))

        logger.info("Stored refresh token", user_id=user_id, device_id=device_id)

    async def validate_token(
        self, user_id: str, refresh_token: str, device_id: str
    ) -> bool:
        """Validate refresh token.

        Args:
            user_id: User ID
            refresh_token: Refresh token to validate
            device_id: Device identifier

        Returns:
            True if valid, False otherwise
        """
        await self.connect()

        key = f"refresh_token:{user_id}:{device_id}"
        stored_data = await self._redis.get(key)

        if not stored_data:
            return False

        try:
            data = json.loads(stored_data)
            return data["token"] == refresh_token
        except (json.JSONDecodeError, KeyError):
            return False

    async def revoke_token(self, user_id: str, device_id: str) -> None:
        """Revoke a specific refresh token.

        Args:
            user_id: User ID
            device_id: Device identifier
        """
        await self.connect()

        key = f"refresh_token:{user_id}:{device_id}"
        await self._redis.delete(key)

        logger.info("Revoked refresh token", user_id=user_id, device_id=device_id)

    async def revoke_all_user_tokens(self, user_id: str) -> int:
        """Revoke all refresh tokens for a user.

        Args:
            user_id: User ID

        Returns:
            Number of tokens revoked
        """
        await self.connect()

        # Find all tokens for user
        pattern = f"refresh_token:{user_id}:*"
        keys = []

        async for key in self._redis.scan_iter(match=pattern):
            keys.append(key)

        if keys:
            count = await self._redis.delete(*keys)
            logger.info("Revoked all user tokens", user_id=user_id, count=count)
            return count

        return 0


class JWTManager:
    """Manages JWT token generation, validation, and refresh."""

    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 15,
        refresh_token_expire_days: int = 7,
        refresh_token_store: Optional[RefreshTokenStore] = None,
    ):
        """Initialize JWT manager.

        Args:
            secret_key: Secret key for token signing
            algorithm: JWT algorithm (default: HS256)
            access_token_expire_minutes: Access token expiry in minutes
            refresh_token_expire_days: Refresh token expiry in days
            refresh_token_store: Optional refresh token store
        """
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_expire_minutes = access_token_expire_minutes
        self.refresh_token_expire_days = refresh_token_expire_days
        self.refresh_token_store = refresh_token_store

    def create_access_token(self, user_data: Dict[str, Any]) -> str:
        """Create an access token.

        Args:
            user_data: User data to encode in token

        Returns:
            JWT access token
        """
        now = datetime.now(timezone.utc)
        expire = now + timedelta(minutes=self.access_token_expire_minutes)

        to_encode = user_data.copy()
        to_encode.update(
            {
                "exp": expire,
                "iat": now,
                "type": "access",
                "jti": str(uuid.uuid4()),  # JWT ID for tracking
            }
        )

        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

    def create_refresh_token(self, user_id: str, device_id: str) -> str:
        """Create a refresh token.

        Args:
            user_id: User ID
            device_id: Device identifier

        Returns:
            JWT refresh token
        """
        now = datetime.now(timezone.utc)
        expire = now + timedelta(days=self.refresh_token_expire_days)

        to_encode = {
            "user_id": user_id,
            "device_id": device_id,
            "exp": expire,
            "iat": now,
            "type": "refresh",
            "jti": str(uuid.uuid4()),
        }

        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

    async def create_token_pair(
        self,
        user_data: Dict[str, Any],
        device_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TokenPair:
        """Create access and refresh token pair.

        Args:
            user_data: User data for access token
            device_id: Device identifier
            metadata: Additional metadata for refresh token

        Returns:
            Token pair with expiry information
        """
        access_token = self.create_access_token(user_data)
        refresh_token = self.create_refresh_token(user_data["user_id"], device_id)

        # Store refresh token if store is available
        if self.refresh_token_store:
            await self.refresh_token_store.store_token(
                user_id=user_data["user_id"],
                refresh_token=refresh_token,
                device_id=device_id,
                metadata=metadata,
            )

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self.access_token_expire_minutes * 60,
            refresh_expires_in=self.refresh_token_expire_days * 86400,
        )

    def validate_access_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate access token.

        Args:
            token: JWT token to validate

        Returns:
            Decoded token data if valid, None otherwise
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])

            if payload.get("type") != "access":
                return None

            return payload

        except jwt.ExpiredSignatureError:
            logger.debug("Access token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.debug("Invalid access token", error=str(e))
            return None

    async def refresh_tokens(
        self,
        refresh_token: str,
        device_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TokenPair:
        """Refresh tokens using refresh token.

        Args:
            refresh_token: Current refresh token
            device_id: Device identifier
            metadata: Additional metadata

        Returns:
            New token pair

        Raises:
            TokenRefreshError: If refresh fails
        """
        try:
            # Decode refresh token
            payload = jwt.decode(
                refresh_token, self.secret_key, algorithms=[self.algorithm]
            )

            if payload.get("type") != "refresh":
                raise TokenRefreshError("Invalid token type")

            user_id = payload["user_id"]
            token_device_id = payload.get("device_id")

            if token_device_id != device_id:
                raise TokenRefreshError("Device ID mismatch")

            # Validate with store if available
            if self.refresh_token_store:
                is_valid = await self.refresh_token_store.validate_token(
                    user_id=user_id, refresh_token=refresh_token, device_id=device_id
                )

                if not is_valid:
                    raise TokenRefreshError("Refresh token not found or invalid")

                # Revoke old token
                await self.refresh_token_store.revoke_token(user_id, device_id)

            # Create new tokens
            # In real implementation, fetch fresh user data from database
            user_data = {
                "user_id": user_id,
                # Add other user data as needed
            }

            new_pair = await self.create_token_pair(user_data, device_id, metadata)

            logger.info(
                "Tokens refreshed successfully", user_id=user_id, device_id=device_id
            )

            return new_pair

        except jwt.ExpiredSignatureError:
            raise TokenRefreshError("Refresh token expired")
        except jwt.InvalidTokenError as e:
            raise TokenRefreshError(f"Invalid refresh token: {e}")

    def is_token_near_expiry(self, token: str, threshold_minutes: int = 5) -> bool:
        """Check if token is near expiry.

        Args:
            token: JWT token to check
            threshold_minutes: Minutes before expiry to consider "near"

        Returns:
            True if near expiry, False otherwise
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={"verify_exp": False},  # Don't verify expiry
            )

            exp = payload.get("exp")
            if not exp:
                return True

            expiry_time = datetime.fromtimestamp(exp, tz=timezone.utc)
            time_to_expiry = expiry_time - datetime.now(timezone.utc)

            return time_to_expiry.total_seconds() < threshold_minutes * 60

        except jwt.InvalidTokenError:
            return True


class AutoRefreshClient:
    """HTTP client with automatic token refresh."""

    def __init__(
        self,
        jwt_manager: JWTManager,
        base_url: Optional[str] = None,
        refresh_threshold_minutes: int = 5,
        retry_attempts: int = 3,
        retry_delay_seconds: float = 1.0,
    ):
        """Initialize auto-refresh client.

        Args:
            jwt_manager: JWT manager instance
            base_url: Optional base URL for requests
            refresh_threshold_minutes: Minutes before expiry to refresh
            retry_attempts: Number of retry attempts on 401
            retry_delay_seconds: Delay between retries
        """
        self.jwt_manager = jwt_manager
        self.base_url = base_url
        self.refresh_threshold_minutes = refresh_threshold_minutes
        self.retry_attempts = retry_attempts
        self.retry_delay_seconds = retry_delay_seconds

        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._device_id: Optional[str] = None
        self._refresh_lock = asyncio.Lock()
        self._refresh_task: Optional[asyncio.Task] = None
        self._client = httpx.AsyncClient(base_url=base_url)

    def set_tokens(self, access_token: str, refresh_token: str, device_id: str) -> None:
        """Set current tokens.

        Args:
            access_token: Access token
            refresh_token: Refresh token
            device_id: Device identifier
        """
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._device_id = device_id

    async def _refresh_tokens(self) -> TokenPair:
        """Refresh tokens with lock to prevent concurrent refresh."""
        async with self._refresh_lock:
            # Check if already refreshed by another coroutine
            if self._access_token and not self.jwt_manager.is_token_near_expiry(
                self._access_token
            ):
                # Token already refreshed
                return TokenPair(
                    access_token=self._access_token,
                    refresh_token=self._refresh_token,
                    expires_in=0,  # Not used
                    refresh_expires_in=0,  # Not used
                )

            # Perform refresh
            new_pair = await self.jwt_manager.refresh_tokens(
                self._refresh_token, self._device_id
            )

            # Update tokens
            self._access_token = new_pair.access_token
            self._refresh_token = new_pair.refresh_token

            return new_pair

    async def _make_authenticated_request(self, method: str, url: str, **kwargs) -> Any:
        """Make authenticated HTTP request.

        Args:
            method: HTTP method
            url: Request URL
            **kwargs: Additional request arguments

        Returns:
            Response data
        """
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._access_token}"

        response = await self._client.request(method, url, headers=headers, **kwargs)

        response.raise_for_status()
        return response.json()

    async def request(self, method: str, url: str, **kwargs) -> Any:
        """Make HTTP request with automatic token refresh.

        Args:
            method: HTTP method
            url: Request URL
            **kwargs: Additional request arguments

        Returns:
            Response data
        """
        # Check if token needs refresh
        if self._access_token and self.jwt_manager.is_token_near_expiry(
            self._access_token, self.refresh_threshold_minutes
        ):
            await self._refresh_tokens()

        # Attempt request with retries
        for attempt in range(self.retry_attempts):
            try:
                return await self._make_authenticated_request(method, url, **kwargs)

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401 and attempt < self.retry_attempts - 1:
                    # Token might be invalid, try refresh
                    logger.debug("Got 401, attempting token refresh", attempt=attempt)

                    try:
                        await self._refresh_tokens()
                        await asyncio.sleep(self.retry_delay_seconds)
                        continue
                    except TokenRefreshError:
                        logger.error("Token refresh failed")
                        raise
                else:
                    raise

        raise Exception("Max retry attempts exceeded")

    async def start_background_refresh(
        self, check_interval_seconds: int = 60
    ) -> asyncio.Task:
        """Start background token refresh task.

        Args:
            check_interval_seconds: Interval between checks

        Returns:
            Background task
        """

        async def refresh_loop():
            while True:
                try:
                    await asyncio.sleep(check_interval_seconds)

                    if self._access_token and self.jwt_manager.is_token_near_expiry(
                        self._access_token, self.refresh_threshold_minutes
                    ):
                        logger.info("Background refresh triggered")
                        await self._refresh_tokens()

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error("Background refresh failed", error=str(e))

        self._refresh_task = asyncio.create_task(refresh_loop())
        return self._refresh_task

    async def stop_background_refresh(self) -> None:
        """Stop background refresh task."""
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            self._refresh_task = None

    async def close(self) -> None:
        """Close client and cleanup."""
        await self.stop_background_refresh()
        await self._client.aclose()


# Convenience functions for integration
async def create_jwt_system(
    secret_key: str,
    redis_url: str,
    access_expire_minutes: int = 15,
    refresh_expire_days: int = 7,
) -> Tuple[JWTManager, RefreshTokenStore]:
    """Create complete JWT system with token store.

    Args:
        secret_key: JWT secret key
        redis_url: Redis connection URL
        access_expire_minutes: Access token expiry
        refresh_expire_days: Refresh token expiry

    Returns:
        Tuple of (JWTManager, RefreshTokenStore)
    """
    token_store = RefreshTokenStore(redis_url)
    await token_store.connect()

    jwt_manager = JWTManager(
        secret_key=secret_key,
        access_token_expire_minutes=access_expire_minutes,
        refresh_token_expire_days=refresh_expire_days,
        refresh_token_store=token_store,
    )

    return jwt_manager, token_store
