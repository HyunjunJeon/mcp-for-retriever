"""
Redis 기반 Sliding Window Rate Limiter 구현

분산 환경에서 정확한 속도 제한을 위한 Redis 기반 구현입니다.
Sliding Window 알고리즘을 사용하여 시간 기반 정밀한 rate limiting을 제공합니다.

주요 기능:
    - Sliding Window 알고리즘으로 정확한 시간 기반 제한
    - Redis ZSET을 활용한 효율적인 요청 추적
    - Lua 스크립트로 원자성 보장
    - 분산 환경에서 일관된 동작
    - Graceful degradation 지원

알고리즘:
    1. Redis ZSET에 타임스탬프를 score로 요청 기록
    2. 윈도우 외부의 오래된 요청 자동 제거
    3. 현재 윈도우 내의 요청 수 계산
    4. 제한 초과 시 다음 가능 시간 계산

성능 최적화:
    - O(log N) 시간 복잡도
    - 메모리 효율적인 자동 정리
    - 배치 처리로 네트워크 오버헤드 최소화
"""

import time
import uuid
from typing import Optional, Tuple, Dict, Any
import redis.asyncio as redis
import structlog

logger = structlog.get_logger(__name__)


class RedisRateLimiter:
    """Redis 기반 Sliding Window Rate Limiter"""

    # Lua 스크립트: 원자적 rate limit 확인 및 기록
    LUA_SCRIPT = """
    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local window = tonumber(ARGV[2])
    local limit = tonumber(ARGV[3])
    local weight = tonumber(ARGV[4])
    local request_id = ARGV[5]
    
    -- 윈도우 시작 시간 계산
    local window_start = now - window
    
    -- 오래된 요청 제거
    redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)
    
    -- 현재 윈도우 내의 총 가중치 계산
    local current_weight = 0
    local requests = redis.call('ZRANGE', key, 0, -1, 'WITHSCORES')
    
    for i = 1, #requests, 2 do
        local score = tonumber(requests[i + 1])
        -- score의 소수 부분이 가중치를 나타냄
        local req_weight = math.floor((score - math.floor(score)) * 1000 + 0.5)
        if req_weight == 0 then req_weight = 1 end
        current_weight = current_weight + req_weight
    end
    
    -- 새 요청 추가 시 제한 초과 여부 확인
    if current_weight + weight > limit then
        -- 가장 오래된 요청의 만료 시간 계산
        if #requests > 0 then
            local oldest = tonumber(requests[2])
            local oldest_timestamp = math.floor(oldest)
            local retry_after = oldest_timestamp + window - now
            return {0, current_weight, math.ceil(retry_after)}
        else
            return {0, current_weight, 1}
        end
    end
    
    -- 요청 기록 (타임스탬프.가중치 형식으로 score 저장)
    local score = now + (weight / 1000.0)
    redis.call('ZADD', key, score, request_id)
    redis.call('EXPIRE', key, window + 60)  -- 윈도우 + 버퍼
    
    return {1, current_weight + weight, 0}
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        window_seconds: int = 60,
        default_limit: int = 60,
    ):
        """
        Redis Rate Limiter 초기화

        Args:
            redis_client: Redis 비동기 클라이언트
            window_seconds: 슬라이딩 윈도우 크기 (초)
            default_limit: 기본 요청 제한 수
        """
        self.redis = redis_client
        self.window_seconds = window_seconds
        self.default_limit = default_limit
        self._script_sha: Optional[str] = None

    async def _ensure_script_loaded(self) -> str:
        """Lua 스크립트가 Redis에 로드되었는지 확인"""
        if self._script_sha is None:
            self._script_sha = await self.redis.script_load(self.LUA_SCRIPT)
        return self._script_sha

    def _get_key(self, identifier: str, endpoint: Optional[str] = None) -> str:
        """Rate limit 키 생성"""
        if endpoint:
            return f"rate_limit:{identifier}:{endpoint}"
        return f"rate_limit:{identifier}"

    async def check_rate_limit(
        self,
        identifier: str,
        limit: Optional[int] = None,
        weight: int = 1,
        endpoint: Optional[str] = None,
        window_seconds: Optional[int] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Rate limit 확인 및 요청 기록

        Args:
            identifier: 사용자/클라이언트 식별자
            limit: 요청 제한 수 (None이면 기본값 사용)
            weight: 요청 가중치 (기본값: 1)
            endpoint: 엔드포인트 식별자 (선택적)
            window_seconds: 커스텀 윈도우 크기 (선택적)

        Returns:
            (allowed, info) 튜플
            - allowed: 요청 허용 여부
            - info: 상세 정보 (current_usage, limit, retry_after 등)
        """
        try:
            key = self._get_key(identifier, endpoint)
            current_time = time.time()
            window = window_seconds or self.window_seconds
            req_limit = limit or self.default_limit
            request_id = str(uuid.uuid4())

            # Lua 스크립트 실행
            script_sha = await self._ensure_script_loaded()
            result = await self.redis.evalsha(
                script_sha,
                1,  # number of keys
                key,  # KEYS[1]
                str(current_time),  # ARGV[1]
                str(window),  # ARGV[2]
                str(req_limit),  # ARGV[3]
                str(weight),  # ARGV[4]
                request_id,  # ARGV[5]
            )

            allowed = bool(result[0])
            current_usage = int(result[1])
            retry_after = int(result[2]) if len(result) > 2 else 0

            info = {
                "allowed": allowed,
                "current_usage": current_usage,
                "limit": req_limit,
                "window_seconds": window,
                "retry_after": retry_after,
                "remaining": max(0, req_limit - current_usage) if allowed else 0,
                "reset_at": int(current_time + window),
                "identifier": identifier,
                "endpoint": endpoint,
                "weight": weight,
            }

            if allowed:
                logger.debug("Rate limit check passed", **info)
            else:
                logger.warning("Rate limit exceeded", **info)

            return allowed, info

        except redis.RedisError as e:
            # Redis 오류 시 graceful degradation
            logger.error(
                "Redis rate limiter error", error=str(e), identifier=identifier
            )
            # 오류 시 요청 허용 (서비스 가용성 우선)
            return True, {"allowed": True, "error": str(e), "degraded": True}
        except Exception as e:
            logger.error(
                "Unexpected rate limiter error", error=str(e), identifier=identifier
            )
            return True, {"allowed": True, "error": str(e), "degraded": True}

    async def get_usage_stats(
        self,
        identifier: str,
        endpoint: Optional[str] = None,
        window_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        현재 사용량 통계 조회

        Args:
            identifier: 사용자/클라이언트 식별자
            endpoint: 엔드포인트 식별자 (선택적)
            window_seconds: 커스텀 윈도우 크기 (선택적)

        Returns:
            사용량 통계 정보
        """
        try:
            key = self._get_key(identifier, endpoint)
            current_time = time.time()
            window = window_seconds or self.window_seconds
            window_start = current_time - window

            # 오래된 요청 제거
            await self.redis.zremrangebyscore(key, "-inf", window_start)

            # 현재 윈도우 내의 요청 조회
            requests = await self.redis.zrange(key, 0, -1, withscores=True)

            # 총 가중치 계산
            total_weight = 0
            request_times = []

            for _, score in requests:
                # score가 float인지 확인
                score_float = float(score)
                timestamp = int(score_float)
                # 소수 부분이 가중치를 나타냄
                weight_part = score_float - timestamp
                weight = int(weight_part * 1000 + 0.5) if weight_part > 0 else 1
                total_weight += weight
                request_times.append(timestamp)

            # 다음 리셋 시간 계산
            if request_times:
                oldest_request = min(request_times)
                next_reset = oldest_request + window
            else:
                next_reset = current_time + window

            return {
                "current_usage": total_weight,
                "request_count": len(requests),
                "window_seconds": window,
                "next_reset": int(next_reset),
                "time_until_reset": max(0, int(next_reset - current_time)),
            }

        except Exception as e:
            logger.error(
                "Failed to get usage stats", error=str(e), identifier=identifier
            )
            return {"error": str(e), "current_usage": 0, "request_count": 0}

    async def reset_limit(
        self, identifier: str, endpoint: Optional[str] = None
    ) -> bool:
        """
        특정 식별자의 rate limit 초기화

        Args:
            identifier: 사용자/클라이언트 식별자
            endpoint: 엔드포인트 식별자 (선택적)

        Returns:
            성공 여부
        """
        try:
            key = self._get_key(identifier, endpoint)
            await self.redis.delete(key)

            logger.info("Rate limit reset", identifier=identifier, endpoint=endpoint)
            return True

        except Exception as e:
            logger.error(
                "Failed to reset rate limit", error=str(e), identifier=identifier
            )
            return False

    async def cleanup_expired(self, batch_size: int = 100) -> int:
        """
        만료된 rate limit 데이터 정리

        Args:
            batch_size: 한 번에 처리할 키 개수

        Returns:
            정리된 키 개수
        """
        try:
            cleaned = 0
            cursor = 0
            current_time = time.time()

            while True:
                # SCAN으로 rate_limit 키 조회
                cursor, keys = await self.redis.scan(
                    cursor, match="rate_limit:*", count=batch_size
                )

                for key in keys:
                    # 빈 ZSET 제거
                    card = await self.redis.zcard(key)
                    if card == 0:
                        await self.redis.delete(key)
                        cleaned += 1
                    else:
                        # 오래된 엔트리만 있는 경우 전체 키 삭제
                        newest = await self.redis.zrange(key, -1, -1, withscores=True)
                        if newest and len(newest) > 0:
                            # newest는 [(member, score)] 형태
                            newest_score = float(newest[0][1])
                            newest_time = int(newest_score)
                            if newest_time + self.window_seconds < current_time:
                                await self.redis.delete(key)
                                cleaned += 1

                if cursor == 0:
                    break

            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} expired rate limit keys")

            return cleaned

        except Exception as e:
            logger.error("Failed to cleanup expired rate limits", error=str(e))
            return 0
