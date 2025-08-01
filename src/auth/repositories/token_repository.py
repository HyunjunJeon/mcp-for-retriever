"""
토큰 저장소 인터페이스 및 구현

이 모듈은 JWT 토큰의 무효화를 위한 저장소 패턴을 구현합니다.
Redis를 사용하여 발급된 리프레시 토큰을 추적하고 무효화합니다.

주요 기능:
    - 리프레시 토큰 저장 및 조회
    - 토큰 무효화 (단일/전체)
    - 토큰 유효성 검증
    - 사용자별 토큰 관리
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from datetime import datetime
import json

import redis.asyncio as redis
import structlog

logger = structlog.get_logger(__name__)


class TokenRepository(ABC):
    """토큰 저장소 추상 클래스"""

    @abstractmethod
    async def store_refresh_token(
        self,
        jti: str,
        user_id: str,
        expires_at: datetime,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        리프레시 토큰 저장

        Args:
            jti: JWT ID (토큰의 고유 식별자)
            user_id: 사용자 ID
            expires_at: 토큰 만료 시간
            metadata: 추가 메타데이터 (device_id, IP 등)

        Returns:
            bool: 저장 성공 여부
        """
        pass

    @abstractmethod
    async def is_token_valid(self, jti: str) -> bool:
        """
        토큰 유효성 확인

        Args:
            jti: JWT ID

        Returns:
            bool: 유효한 토큰인지 여부
        """
        pass

    @abstractmethod
    async def revoke_token(self, jti: str) -> bool:
        """
        특정 토큰 무효화

        Args:
            jti: JWT ID

        Returns:
            bool: 무효화 성공 여부
        """
        pass

    @abstractmethod
    async def revoke_user_tokens(self, user_id: str) -> int:
        """
        사용자의 모든 토큰 무효화

        Args:
            user_id: 사용자 ID

        Returns:
            int: 무효화된 토큰 수
        """
        pass

    @abstractmethod
    async def get_user_active_tokens(self, user_id: str) -> List[Dict[str, Any]]:
        """
        사용자의 활성 토큰 목록 조회

        Args:
            user_id: 사용자 ID

        Returns:
            List[Dict]: 활성 토큰 정보 목록
        """
        pass

    @abstractmethod
    async def cleanup_expired_tokens(self) -> int:
        """
        만료된 토큰 정리

        Returns:
            int: 정리된 토큰 수
        """
        pass


class RedisTokenRepository(TokenRepository):
    """Redis 기반 토큰 저장소 구현"""

    def __init__(self, redis_client: redis.Redis):
        """
        Redis 토큰 저장소 초기화

        Args:
            redis_client: Redis 비동기 클라이언트
        """
        self.redis = redis_client
        self.token_prefix = "refresh_token:"
        self.user_tokens_prefix = "user_tokens:"
        self.revoked_tokens_prefix = "revoked_tokens:"

    async def store_refresh_token(
        self,
        jti: str,
        user_id: str,
        expires_at: datetime,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """리프레시 토큰 저장"""
        try:
            # 토큰 정보 구성
            token_data = {
                "jti": jti,
                "user_id": user_id,
                "issued_at": datetime.utcnow().isoformat(),
                "expires_at": expires_at.isoformat(),
                "metadata": metadata or {},
            }

            # Redis에 토큰 저장 (만료 시간 설정)
            ttl = int((expires_at - datetime.utcnow()).total_seconds())
            if ttl > 0:
                # 토큰 정보 저장
                await self.redis.setex(
                    f"{self.token_prefix}{jti}", ttl, json.dumps(token_data)
                )

                # 사용자별 토큰 목록에 추가
                await self.redis.sadd(f"{self.user_tokens_prefix}{user_id}", jti)

                # 사용자 토큰 목록도 TTL 설정 (가장 긴 토큰 만료시간으로)
                await self.redis.expire(f"{self.user_tokens_prefix}{user_id}", ttl)

                logger.info(
                    "리프레시 토큰 저장됨", jti=jti, user_id=user_id, ttl_seconds=ttl
                )
                return True
            else:
                logger.warning("토큰이 이미 만료됨", jti=jti)
                return False

        except Exception as e:
            logger.error("토큰 저장 실패", error=str(e), jti=jti)
            return False

    async def is_token_valid(self, jti: str) -> bool:
        """토큰 유효성 확인"""
        try:
            # 무효화된 토큰인지 확인
            if await self.redis.exists(f"{self.revoked_tokens_prefix}{jti}"):
                return False

            # 저장된 토큰인지 확인
            return bool(await self.redis.exists(f"{self.token_prefix}{jti}"))

        except Exception as e:
            logger.error("토큰 유효성 확인 실패", error=str(e), jti=jti)
            return False

    async def revoke_token(self, jti: str) -> bool:
        """특정 토큰 무효화"""
        try:
            # 토큰 정보 조회
            token_data = await self.redis.get(f"{self.token_prefix}{jti}")
            if not token_data:
                logger.warning("존재하지 않는 토큰", jti=jti)
                return False

            token_info = json.loads(token_data)

            # 무효화 목록에 추가 (원래 만료시간까지 유지)
            expires_at = datetime.fromisoformat(token_info["expires_at"])
            ttl = int((expires_at - datetime.utcnow()).total_seconds())

            if ttl > 0:
                await self.redis.setex(
                    f"{self.revoked_tokens_prefix}{jti}",
                    ttl,
                    json.dumps(
                        {
                            "revoked_at": datetime.utcnow().isoformat(),
                            "user_id": token_info["user_id"],
                        }
                    ),
                )

            # 원본 토큰 삭제
            await self.redis.delete(f"{self.token_prefix}{jti}")

            # 사용자 토큰 목록에서 제거
            user_id = token_info["user_id"]
            await self.redis.srem(f"{self.user_tokens_prefix}{user_id}", jti)

            logger.info("토큰 무효화됨", jti=jti, user_id=user_id)
            return True

        except Exception as e:
            logger.error("토큰 무효화 실패", error=str(e), jti=jti)
            return False

    async def revoke_user_tokens(self, user_id: str) -> int:
        """사용자의 모든 토큰 무효화"""
        try:
            # 사용자의 모든 토큰 ID 조회
            token_ids = await self.redis.smembers(f"{self.user_tokens_prefix}{user_id}")

            if not token_ids:
                return 0

            # 각 토큰 무효화
            revoked_count = 0
            for jti_bytes in token_ids:
                jti = jti_bytes.decode() if isinstance(jti_bytes, bytes) else jti_bytes
                if await self.revoke_token(jti):
                    revoked_count += 1

            # 사용자 토큰 목록 삭제
            await self.redis.delete(f"{self.user_tokens_prefix}{user_id}")

            logger.info(
                "사용자 토큰 모두 무효화됨",
                user_id=user_id,
                revoked_count=revoked_count,
            )
            return revoked_count

        except Exception as e:
            logger.error("사용자 토큰 무효화 실패", error=str(e), user_id=user_id)
            return 0

    async def get_user_active_tokens(self, user_id: str) -> List[Dict[str, Any]]:
        """사용자의 활성 토큰 목록 조회"""
        try:
            # 사용자의 토큰 ID 목록 조회
            token_ids = await self.redis.smembers(f"{self.user_tokens_prefix}{user_id}")

            if not token_ids:
                return []

            # 각 토큰의 상세 정보 조회
            active_tokens = []
            for jti_bytes in token_ids:
                jti = jti_bytes.decode() if isinstance(jti_bytes, bytes) else jti_bytes
                token_data = await self.redis.get(f"{self.token_prefix}{jti}")

                if token_data:
                    token_info = json.loads(token_data)
                    # 무효화되지 않은 토큰만 포함
                    if not await self.redis.exists(
                        f"{self.revoked_tokens_prefix}{jti}"
                    ):
                        active_tokens.append(token_info)

            return active_tokens

        except Exception as e:
            logger.error("활성 토큰 조회 실패", error=str(e), user_id=user_id)
            return []

    async def cleanup_expired_tokens(self) -> int:
        """만료된 토큰 정리 (Redis TTL이 자동으로 처리하므로 추가 작업 불필요)"""
        # Redis의 TTL 메커니즘이 자동으로 만료된 키를 삭제함
        logger.info("Redis TTL이 만료된 토큰을 자동으로 정리합니다")
        return 0


class InMemoryTokenRepository(TokenRepository):
    """메모리 기반 토큰 저장소 (테스트용)"""

    def __init__(self):
        self.tokens: Dict[str, Dict[str, Any]] = {}
        self.user_tokens: Dict[str, set] = {}
        self.revoked_tokens: set = set()

    async def store_refresh_token(
        self,
        jti: str,
        user_id: str,
        expires_at: datetime,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """리프레시 토큰 저장"""
        self.tokens[jti] = {
            "jti": jti,
            "user_id": user_id,
            "issued_at": datetime.utcnow(),
            "expires_at": expires_at,
            "metadata": metadata or {},
        }

        if user_id not in self.user_tokens:
            self.user_tokens[user_id] = set()
        self.user_tokens[user_id].add(jti)

        return True

    async def is_token_valid(self, jti: str) -> bool:
        """토큰 유효성 확인"""
        if jti in self.revoked_tokens:
            return False

        token = self.tokens.get(jti)
        if not token:
            return False

        # 만료 확인
        return token["expires_at"] > datetime.utcnow()

    async def revoke_token(self, jti: str) -> bool:
        """특정 토큰 무효화"""
        if jti in self.tokens:
            self.revoked_tokens.add(jti)
            user_id = self.tokens[jti]["user_id"]

            if user_id in self.user_tokens:
                self.user_tokens[user_id].discard(jti)

            return True
        return False

    async def revoke_user_tokens(self, user_id: str) -> int:
        """사용자의 모든 토큰 무효화"""
        if user_id not in self.user_tokens:
            return 0

        tokens = list(self.user_tokens[user_id])
        for jti in tokens:
            await self.revoke_token(jti)

        return len(tokens)

    async def get_user_active_tokens(self, user_id: str) -> List[Dict[str, Any]]:
        """사용자의 활성 토큰 목록 조회"""
        if user_id not in self.user_tokens:
            return []

        active_tokens = []
        for jti in self.user_tokens[user_id]:
            if await self.is_token_valid(jti):
                active_tokens.append(self.tokens[jti])

        return active_tokens

    async def cleanup_expired_tokens(self) -> int:
        """만료된 토큰 정리"""
        expired = []
        for jti, token in self.tokens.items():
            if token["expires_at"] <= datetime.utcnow():
                expired.append(jti)

        for jti in expired:
            user_id = self.tokens[jti]["user_id"]
            del self.tokens[jti]
            if user_id in self.user_tokens:
                self.user_tokens[user_id].discard(jti)

        return len(expired)
