"""
토큰 무효화 기능 단위 테스트

이 모듈은 JWT 토큰 무효화 기능의 핵심 동작을 검증합니다.
Redis 기반 토큰 저장소와 JWT 서비스의 통합을 테스트합니다.
"""

import pytest
from datetime import datetime, timedelta, UTC
from unittest.mock import AsyncMock

from src.auth.repositories.token_repository import (
    TokenRepository,
    RedisTokenRepository,
    InMemoryTokenRepository,
)
from src.auth.services.jwt_service import JWTService


class TestTokenRepository:
    """토큰 저장소 테스트"""

    @pytest.mark.asyncio
    async def test_in_memory_token_storage(self):
        """메모리 기반 토큰 저장 테스트"""
        repository = InMemoryTokenRepository()

        # 토큰 저장
        jti = "test-jti-123"
        user_id = "user-123"
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        success = await repository.store_refresh_token(
            jti=jti,
            user_id=user_id,
            expires_at=expires_at,
            metadata={"device": "test-device"},
        )

        assert success is True

        # 토큰 유효성 확인
        is_valid = await repository.is_token_valid(jti)
        assert is_valid is True

    @pytest.mark.asyncio
    async def test_token_revocation(self):
        """토큰 무효화 테스트"""
        repository = InMemoryTokenRepository()

        # 토큰 저장
        jti = "test-jti-456"
        user_id = "user-456"
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        await repository.store_refresh_token(
            jti=jti, user_id=user_id, expires_at=expires_at
        )

        # 토큰 무효화
        revoked = await repository.revoke_token(jti)
        assert revoked is True

        # 무효화된 토큰 확인
        is_valid = await repository.is_token_valid(jti)
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_revoke_user_tokens(self):
        """사용자의 모든 토큰 무효화 테스트"""
        repository = InMemoryTokenRepository()
        user_id = "user-789"

        # 여러 토큰 저장
        for i in range(3):
            await repository.store_refresh_token(
                jti=f"test-jti-{i}",
                user_id=user_id,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )

        # 사용자의 모든 토큰 무효화
        count = await repository.revoke_user_tokens(user_id)
        assert count == 3

        # 모든 토큰이 무효화되었는지 확인
        for i in range(3):
            is_valid = await repository.is_token_valid(f"test-jti-{i}")
            assert is_valid is False

    @pytest.mark.asyncio
    async def test_get_user_active_tokens(self):
        """사용자의 활성 토큰 조회 테스트"""
        repository = InMemoryTokenRepository()
        user_id = "user-active"

        # 활성 토큰 저장
        await repository.store_refresh_token(
            jti="active-1",
            user_id=user_id,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            metadata={"device": "mobile"},
        )

        await repository.store_refresh_token(
            jti="active-2",
            user_id=user_id,
            expires_at=datetime.now(UTC) + timedelta(hours=2),
            metadata={"device": "web"},
        )

        # 하나 무효화
        await repository.revoke_token("active-1")

        # 활성 토큰 조회
        active_tokens = await repository.get_user_active_tokens(user_id)
        assert len(active_tokens) == 1
        assert active_tokens[0]["jti"] == "active-2"
        assert active_tokens[0]["metadata"]["device"] == "web"


class TestRedisTokenRepository:
    """Redis 기반 토큰 저장소 테스트"""

    @pytest.mark.asyncio
    async def test_redis_token_storage(self):
        """Redis 토큰 저장 테스트"""
        # Mock Redis 클라이언트
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock(return_value=True)
        mock_redis.sadd = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock(return_value=True)

        repository = RedisTokenRepository(mock_redis)

        # 토큰 저장
        jti = "redis-jti-123"
        user_id = "redis-user-123"
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        success = await repository.store_refresh_token(
            jti=jti,
            user_id=user_id,
            expires_at=expires_at,
            metadata={"ip": "192.168.1.1"},
        )

        assert success is True
        mock_redis.setex.assert_called_once()
        mock_redis.sadd.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_token_validation(self):
        """Redis 토큰 유효성 검증 테스트"""
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(
            side_effect=[False, True]
        )  # 무효화 목록에 없음, 저장된 토큰임

        repository = RedisTokenRepository(mock_redis)

        is_valid = await repository.is_token_valid("test-jti")
        assert is_valid is True

        # 무효화된 토큰
        mock_redis.exists = AsyncMock(return_value=True)  # 무효화 목록에 있음
        is_valid = await repository.is_token_valid("revoked-jti")
        assert is_valid is False


class TestJWTServiceWithRevocation:
    """토큰 무효화 기능이 통합된 JWT 서비스 테스트"""

    def test_jwt_service_with_repository(self):
        """토큰 저장소와 통합된 JWT 서비스 테스트"""
        # Mock 토큰 저장소
        mock_repository = AsyncMock(spec=TokenRepository)

        # JWT 서비스 생성
        jwt_service = JWTService(
            secret_key="test-secret-key", token_repository=mock_repository
        )

        # 리프레시 토큰 생성
        refresh_token = jwt_service.create_refresh_token(
            user_id="test-user", device_id="test-device"
        )

        # 토큰이 생성되었는지 확인
        assert refresh_token is not None

        # 토큰 디코딩
        token_data = jwt_service.decode_token(refresh_token)
        assert token_data is not None
        assert token_data.user_id == "test-user"
        assert token_data.jti is not None

    @pytest.mark.asyncio
    async def test_revoke_refresh_token(self):
        """리프레시 토큰 무효화 테스트"""
        repository = InMemoryTokenRepository()
        jwt_service = JWTService(
            secret_key="test-secret-key", token_repository=repository
        )

        # 토큰 생성 및 저장
        user_id = "revoke-test-user"
        device_id = "revoke-test-device"

        # 먼저 토큰을 저장
        jti = "test-revoke-jti"
        await repository.store_refresh_token(
            jti=jti,
            user_id=user_id,
            expires_at=datetime.now(UTC) + timedelta(days=7),
            metadata={"device_id": device_id},
        )

        # 토큰 무효화
        success = await jwt_service.revoke_refresh_token(user_id, device_id)
        assert success is True

    @pytest.mark.asyncio
    async def test_revoke_all_user_tokens(self):
        """사용자의 모든 토큰 무효화 테스트"""
        repository = InMemoryTokenRepository()
        jwt_service = JWTService(
            secret_key="test-secret-key", token_repository=repository
        )

        user_id = "revoke-all-user"

        # 여러 토큰 저장
        for i in range(3):
            await repository.store_refresh_token(
                jti=f"jti-{i}",
                user_id=user_id,
                expires_at=datetime.now(UTC) + timedelta(days=7),
            )

        # 모든 토큰 무효화
        count = await jwt_service.revoke_all_user_tokens(user_id)
        assert count == 3

    @pytest.mark.asyncio
    async def test_get_active_sessions(self):
        """활성 세션 조회 테스트"""
        repository = InMemoryTokenRepository()
        jwt_service = JWTService(
            secret_key="test-secret-key", token_repository=repository
        )

        user_id = "session-test-user"

        # 세션 저장
        await repository.store_refresh_token(
            jti="session-1",
            user_id=user_id,
            expires_at=datetime.now(UTC) + timedelta(days=1),
            metadata={"device": "iPhone", "ip": "192.168.1.100"},
        )

        await repository.store_refresh_token(
            jti="session-2",
            user_id=user_id,
            expires_at=datetime.now(UTC) + timedelta(days=2),
            metadata={"device": "Chrome", "ip": "192.168.1.101"},
        )

        # 활성 세션 조회
        sessions = await jwt_service.get_active_sessions(user_id)
        assert len(sessions) == 2
        assert any(s["metadata"]["device"] == "iPhone" for s in sessions)
        assert any(s["metadata"]["device"] == "Chrome" for s in sessions)


@pytest.mark.asyncio
async def test_expired_token_cleanup():
    """만료된 토큰 정리 테스트"""
    repository = InMemoryTokenRepository()

    # 만료된 토큰 저장
    await repository.store_refresh_token(
        jti="expired-1",
        user_id="user-1",
        expires_at=datetime.now(UTC) - timedelta(hours=1),  # 이미 만료됨
    )

    # 유효한 토큰 저장
    await repository.store_refresh_token(
        jti="valid-1",
        user_id="user-1",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    # 만료된 토큰 정리
    cleaned = await repository.cleanup_expired_tokens()
    assert cleaned == 1

    # 유효한 토큰은 남아있어야 함
    is_valid = await repository.is_token_valid("valid-1")
    assert is_valid is True

    # 만료된 토큰은 제거되어야 함
    is_valid = await repository.is_token_valid("expired-1")
    assert is_valid is False
