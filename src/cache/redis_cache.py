"""
Redis 기반 고성능 캐싱 시스템

이 모듈은 Redis를 백엔드로 사용하는 분산 캐싱 시스템을 구현합니다.
MCP 서버의 검색 결과와 계산 결과를 효율적으로 캐싱하여 성능을 향상시킵니다.

주요 기능:
    - 비동기 Redis 클라이언트 사용
    - 네임스페이스 기반 캐시 격리
    - TTL(Time-To-Live) 기반 자동 만료
    - JSON 직렬화/역직렬화
    - 패턴 매칭 기반 캐시 무효화
    - 데코레이터를 통한 자동 캐싱

성능 최적화:
    - 긴 키 자동 해싱으로 메모리 효율성
    - SCAN 기반 안전한 키 탐색
    - 연결 풀링으로 동시성 향상
    - 실패 시 Graceful Degradation

캐싱 전략:
    - Write-Through: 데이터 저장 시 즉시 캐시 업데이트
    - TTL 기반 만료: 데이터 일관성 유지
    - 네임스페이스 격리: 도메인별 캐시 관리

의존성:
    - redis: Redis 비동기 클라이언트
    - pydantic: 설정 검증
    - structlog: 구조화된 로깅
"""

import json
import hashlib
from typing import Any, Optional, Callable
import redis.asyncio as redis
from pydantic import BaseModel
import structlog

# 모듈별 구조화된 로거
logger = structlog.get_logger(__name__)


class CacheConfig(BaseModel):
    """
    Redis 캐시 설정 모델

    캐시 시스템의 동작을 제어하는 설정 파라미터들을 정의합니다.
    Pydantic을 사용하여 타입 안전성과 검증을 보장합니다.

    Attributes:
        redis_url (str): Redis 서버 연결 URL
            형식: "redis://host:port/db"
            예: "redis://localhost:6379/0"
        default_ttl (int): 기본 캐시 만료 시간 (초 단위)
            데이터가 캐시에 유지되는 기본 시간
        max_ttl (int): 최대 캐시 만료 시간 (초 단위)
            클라이언트가 설정할 수 있는 최대 TTL
        key_prefix (str): 캐시 키 접두사
            다른 애플리케이션과의 키 충돌 방지
        enable_compression (bool): 압축 사용 여부
            대용량 데이터의 메모리 사용량 최적화
    """

    redis_url: str = "redis://localhost:6379/0"
    default_ttl: int = 300  # 5분 (검색 결과의 일반적인 유효 시간)
    max_ttl: int = 3600  # 1시간 (보안상 최대 캐시 시간)
    key_prefix: str = "mcp_cache"  # MCP 서버 전용 키 접두사
    enable_compression: bool = False  # 향후 압축 기능 지원


class RedisCache:
    """
    Redis 기반 분산 캐시 구현체

    고성능 분산 캐싱을 위한 Redis 클라이언트 래퍼입니다.
    비동기 처리와 연결 풀링을 통해 높은 동시성을 지원하며,
    네임스페이스 기반으로 다양한 데이터 타입을 격리하여 관리합니다.

    캐시 계층 구조:
        {key_prefix}:{namespace}:{key} = value
        예: "mcp_cache:retriever:search_python_10_abc123"

    데이터 직렬화:
        - dict/list: JSON으로 직렬화
        - str/int/float: 그대로 저장
        - 기타 객체: str() 변환

    오류 처리:
        - Redis 연결 실패 시 캐시 기능 비활성화
        - 개별 작업 실패 시 로깅 후 기본값 반환
        - 애플리케이션 중단 없는 Graceful Degradation

    사용 예시:
        ```python
        config = CacheConfig(redis_url="redis://localhost:6379/0")
        cache = RedisCache(config)

        await cache.connect()

        # 데이터 저장
        await cache.set("users", "user_123", {"name": "John"}, ttl=600)

        # 데이터 조회
        user_data = await cache.get("users", "user_123")
        ```

    Attributes:
        config (CacheConfig): 캐시 설정
        _client (redis.Redis): Redis 비동기 클라이언트
        _connected (bool): 연결 상태
    """

    def __init__(self, config: CacheConfig):
        """
        Redis 캐시 인스턴스 초기화

        설정을 저장하고 Redis 클라이언트를 위한 초기 상태를 설정합니다.
        실제 연결은 connect() 메서드에서 수행됩니다.

        Args:
            config (CacheConfig): 캐시 설정 객체
                Redis 연결 정보와 캐시 동작 파라미터 포함
        """
        self.config = config
        self._client: Optional[redis.Redis] = None  # Redis 클라이언트 (미연결 상태)
        self._connected = False  # 연결 상태 플래그

    async def connect(self) -> None:
        """
        Redis 서버에 비동기 연결

        Redis 서버에 연결하고 ping 테스트를 통해 연결 상태를 확인합니다.
        연결 풀링을 사용하여 높은 동시성을 지원합니다.

        연결 설정:
            - decode_responses=True: 문자열 자동 디코딩
            - 연결 풀: 자동 관리로 성능 최적화
            - 타임아웃: Redis 클라이언트 기본값 사용

        Raises:
            redis.ConnectionError: Redis 서버 연결 실패
            redis.TimeoutError: 연결 시간 초과
            Exception: 기타 연결 관련 오류

        Note:
            연결 실패 시에도 캐시 인스턴스는 유지되며,
            모든 캐시 작업은 기본값을 반환합니다.
        """
        try:
            # Redis 클라이언트 생성 (연결 풀 포함)
            self._client = redis.from_url(
                self.config.redis_url,
                decode_responses=True,  # 바이트를 문자열로 자동 변환
            )

            # 연결 테스트 (ping 명령어)
            await self._client.ping()

            # 연결 성공 상태 업데이트
            self._connected = True
            logger.info("Redis 캐시 연결 성공", redis_url=self.config.redis_url)

        except Exception as e:
            # 연결 실패 시 상태 초기화 및 로깅
            logger.error(
                "Redis 캐시 연결 실패", error=str(e), redis_url=self.config.redis_url
            )
            self._connected = False
            # 예외를 재발생시켜 호출자가 연결 실패를 알 수 있도록 함
            raise

    async def disconnect(self) -> None:
        """
        Redis 서버 연결 해제

        활성화된 Redis 연결을 안전하게 종료하고 리소스를 정리합니다.
        애플리케이션 종료 시나 연결 재설정 시 호출됩니다.

        해제 과정:
            1. 클라이언트 존재 여부 확인
            2. Redis 클라이언트 연결 종료 (close() 호출)
            3. 연결 상태 플래그 업데이트
            4. 연결 해제 로깅

        리소스 정리:
            - TCP 연결 종료
            - 연결 풀 정리
            - 메모리 해제
            - 내부 상태 초기화

        안전성:
            - 이미 연결이 해제된 상태에서도 안전하게 호출 가능
            - 예외 발생 없이 graceful shutdown 보장
            - 중복 호출에 대한 보호

        호출 시점:
            - 애플리케이션 종료 시
            - 캐시 설정 변경 시
            - 연결 오류 복구 시
            - 메모리 정리가 필요한 시점
        """
        if self._client:
            await self._client.close()
            self._connected = False
            logger.info("Redis 캐시 연결 해제")

    def _generate_key(self, namespace: str, key: str) -> str:
        """
        Redis 저장용 최종 캐시 키 생성

        네임스페이스와 사용자 키를 조합하여 Redis에서 사용할 최종 키를 생성합니다.
        키가 너무 길면 SHA256 해시를 사용하여 메모리 효율성을 보장합니다.

        Args:
            namespace (str): 캐시 네임스페이스
                도메인별 캐시 격리를 위한 구분자
            key (str): 사용자 정의 캐시 키
                실제 데이터를 식별하는 키

        Returns:
            str: Redis에서 사용할 최종 캐시 키
                형식: "{prefix}:{namespace}:{key}" 또는 "{prefix}:{namespace}:{hash}"

        키 생성 규칙:
            1. 기본 형식: "{config.key_prefix}:{namespace}:{key}"
            2. 키 길이 검사 (200자 초과 시)
            3. 긴 키는 SHA256 해시로 변환
            4. 해시 형식: "{config.key_prefix}:{namespace}:{sha256_hash}"

        길이 제한 이유:
            - Redis 키 길이 권장사항 준수 (일반적으로 250자 이하)
            - 메모리 사용량 최적화
            - 네트워크 전송 효율성
            - 인덱싱 성능 향상

        해시 사용 시 특징:
            - SHA256: 256비트 해시 (64자 hex 문자열)
            - 충돌 확률 극히 낮음 (사실상 무시 가능)
            - 결정적 해시 (동일 입력 = 동일 출력)
            - 단방향 해시 (원본 복구 불가)

        키 예시:
            ```python
            # 짧은 키 (원본 유지)
            _generate_key("user", "session_123")
            # → "mcp_cache:user:session_123"

            # 긴 키 (해시 변환)
            long_key = "search_query_with_very_long_parameters_..." * 10
            _generate_key("retriever", long_key)
            # → "mcp_cache:retriever:a1b2c3d4e5f6..."
            ```

        성능 특징:
            - 단순 문자열 결합: O(1)
            - 해시 계산 필요 시: O(n) (n: 키 길이)
            - 메모리 효율적 처리

        주의사항:
            - 해시 변환 시 원본 키 정보 손실
            - 디버깅 시 해시된 키는 해석 어려움
            - 네임스페이스별로 키 공간 격리됨
        """
        # 키가 너무 길면 해시 사용
        if len(key) > 200:
            key_hash = hashlib.sha256(key.encode()).hexdigest()
            return f"{self.config.key_prefix}:{namespace}:{key_hash}"
        return f"{self.config.key_prefix}:{namespace}:{key}"

    async def get(self, namespace: str, key: str, default: Any = None) -> Any:
        """
        캐시에서 값 조회

        지정된 네임스페이스와 키로 캐시된 값을 조회합니다.
        값이 존재하지 않거나 오류가 발생하면 기본값을 반환합니다.

        Args:
            namespace (str): 캐시 네임스페이스
                데이터 도메인별 격리를 위한 구분자
                예: "retriever", "user_session", "api_response"
            key (str): 캐시 키
                네임스페이스 내에서 고유한 식별자
            default (Any): 기본값 (기본값: None)
                캐시 미스이거나 오류 시 반환할 값

        Returns:
            Any: 캐시된 값 또는 기본값
                JSON으로 저장된 경우 자동으로 파싱된 객체
                문자열인 경우 그대로 반환

        캐시 조회 순서:
            1. 연결 상태 확인
            2. 캐시 키 생성 (네임스페이스 + 키)
            3. Redis GET 명령 실행
            4. JSON 역직렬화 시도
            5. 결과 반환 또는 기본값 반환

        성능 특징:
            - O(1) 시간 복잡도
            - 네트워크 지연만 발생
            - 자동 JSON 파싱으로 편의성 제공

        오류 처리:
            - Redis 연결 끊김: 기본값 반환
            - 키 없음: 기본값 반환
            - JSON 파싱 실패: 원본 문자열 반환
            - 기타 오류: 로깅 후 기본값 반환
        """
        # 연결 상태 확인 (빠른 실패)
        if not self._connected or not self._client:
            return default

        try:
            # 전체 캐시 키 생성 (prefix:namespace:key)
            cache_key = self._generate_key(namespace, key)

            # Redis에서 값 조회
            value = await self._client.get(cache_key)

            # 캐시 미스 처리
            if value is None:
                return default

            # JSON 역직렬화 시도
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                # JSON이 아닌 문자열은 그대로 반환
                return value

        except Exception as e:
            # 모든 오류를 로깅하고 기본값 반환
            logger.warning("캐시 조회 실패", namespace=namespace, key=key, error=str(e))
            return default

    async def set(
        self, namespace: str, key: str, value: Any, ttl: Optional[int] = None
    ) -> bool:
        """
        캐시에 값 저장

        지정된 네임스페이스와 키로 값을 Redis에 저장합니다.
        TTL을 설정하여 자동 만료되도록 하며, 다양한 데이터 타입을 지원합니다.

        Args:
            namespace (str): 캐시 네임스페이스
                데이터 도메인별 격리를 위한 구분자
            key (str): 캐시 키
                네임스페이스 내에서 고유한 식별자
            value (Any): 저장할 값
                dict/list: JSON으로 직렬화하여 저장
                str/int/float: 그대로 저장
                기타 객체: str() 변환 후 저장
            ttl (Optional[int]): Time-To-Live (초 단위)
                None: 기본 TTL 사용 (config.default_ttl)
                정수: 지정된 시간 후 만료 (max_ttl 이하로 제한)

        Returns:
            bool: 저장 성공 여부
                True: 성공적으로 저장됨
                False: 저장 실패 또는 캐시 비활성화

        저장 과정:
            1. 연결 상태 확인
            2. 캐시 키 생성 (prefix:namespace:key)
            3. 값 직렬화 (필요한 경우)
            4. TTL 검증 및 적용
            5. Redis SETEX 명령으로 저장

        직렬화 규칙:
            - dict, list → JSON 문자열 (한글 지원)
            - str, int, float → 타입 그대로 저장
            - 기타 → str() 변환하여 저장

        TTL 정책:
            - 기본값: config.default_ttl (300초 = 5분)
            - 최대값: config.max_ttl (3600초 = 1시간)
            - 보안상 과도한 TTL 차단

        오류 처리:
            - Redis 연결 끊김: False 반환
            - 직렬화 실패: 로깅 후 False 반환
            - Redis 명령 실패: 로깅 후 False 반환
        """
        if not self._connected or not self._client:
            return False

        try:
            cache_key = self._generate_key(namespace, key)

            # JSON 인코딩
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)

            # TTL 설정
            if ttl is None:
                ttl = self.config.default_ttl
            else:
                ttl = min(ttl, self.config.max_ttl)

            # Redis에 저장
            await self._client.setex(cache_key, ttl, value)

            logger.debug("캐시 저장 성공", namespace=namespace, key=key, ttl=ttl)
            return True

        except Exception as e:
            logger.warning("캐시 저장 실패", namespace=namespace, key=key, error=str(e))
            return False

    async def delete(self, namespace: str, key: str) -> bool:
        """
        캐시에서 특정 키 삭제

        지정된 네임스페이스와 키에 해당하는 캐시 항목을 Redis에서 삭제합니다.
        즉각적인 삭제로 메모리를 확보하고 오래된 데이터를 제거합니다.

        Args:
            namespace (str): 캐시 네임스페이스
                삭제할 항목이 속한 도메인 구분자
            key (str): 삭제할 캐시 키
                네임스페이스 내의 고유 식별자

        Returns:
            bool: 삭제 성공 여부
                True: 키가 존재했고 성공적으로 삭제됨
                False: 키가 존재하지 않았거나 삭제 실패

        삭제 과정:
            1. 연결 상태 확인
            2. 전체 캐시 키 생성 (prefix:namespace:key)
            3. Redis DELETE 명령 실행
            4. 삭제된 키 개수 확인 (>0이면 성공)

        사용 시나리오:
            - 데이터 업데이트 후 기존 캐시 무효화
            - 사용자별 세션 데이터 정리
            - 임시 캐시 수동 제거
            - 메모리 사용량 최적화

        오류 처리:
            - Redis 연결 끊김: False 반환
            - 존재하지 않는 키: False 반환 (정상 동작)
            - Redis 명령 실패: 로깅 후 False 반환

        Performance:
            - O(1) 시간 복잡도
            - 단일 Redis 명령으로 처리
        """
        if not self._connected or not self._client:
            return False

        try:
            cache_key = self._generate_key(namespace, key)
            result = await self._client.delete(cache_key)
            return result > 0
        except Exception as e:
            logger.warning("캐시 삭제 실패", namespace=namespace, key=key, error=str(e))
            return False

    async def clear_namespace(self, namespace: str) -> int:
        """
        특정 네임스페이스의 모든 캐시 데이터 삭제

        지정된 네임스페이스에 속한 모든 캐시 항목을 일괄 삭제합니다.
        SCAN 명령을 사용하여 메모리 효율적으로 처리하며, 대량 삭제에 적합합니다.

        Args:
            namespace (str): 삭제할 네임스페이스
                해당 도메인의 모든 캐시 항목이 삭제됨
                예: "retriever", "user_session", "api_response"

        Returns:
            int: 삭제된 키의 개수
                0: 삭제할 키가 없었거나 캐시 비활성화
                >0: 성공적으로 삭제된 키 개수

        삭제 과정:
            1. 연결 상태 확인
            2. 네임스페이스 패턴 생성 ({prefix}:{namespace}:*)
            3. SCAN을 사용하여 매칭되는 모든 키 조회
            4. 일괄 DELETE 명령으로 모든 키 삭제

        성능 특징:
            - SCAN 사용으로 메모리 효율적 키 탐색
            - 블로킹 없는 점진적 스캔 방식
            - 일괄 삭제로 네트워크 오버헤드 최소화
            - O(N) 시간 복잡도 (N: 매칭되는 키 개수)

        사용 시나리오:
            - 사용자 로그아웃 시 세션 캐시 정리
            - 특정 도메인 데이터 갱신 후 캐시 무효화
            - 메모리 정리 및 최적화
            - 테스트 환경에서 캐시 초기화

        주의사항:
            - 대량 삭제 시 Redis 성능에 일시적 영향 가능
            - 다른 네임스페이스에는 영향 없음
            - 삭제 중 새로 생성된 키는 삭제되지 않을 수 있음

        Example:
            ```python
            # 모든 검색 결과 캐시 삭제
            deleted_count = await cache.clear_namespace("retriever")
            print(f"삭제된 캐시 항목: {deleted_count}개")
            ```
        """
        if not self._connected or not self._client:
            return 0

        try:
            pattern = f"{self.config.key_prefix}:{namespace}:*"
            keys = []

            # SCAN을 사용하여 키 조회
            async for key in self._client.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                return await self._client.delete(*keys)
            return 0

        except Exception as e:
            logger.warning(
                "네임스페이스 캐시 삭제 실패", namespace=namespace, error=str(e)
            )
            return 0

    async def invalidate_pattern(self, pattern: str) -> int:
        """
        패턴과 일치하는 캐시 항목들 무효화

        주어진 패턴과 일치하는 모든 캐시 키를 검색하여 삭제합니다.
        glob 스타일 패턴 매칭을 지원하며, 세밀한 캐시 제어가 가능합니다.

        Args:
            pattern (str): 삭제할 키 패턴 (glob 스타일)
                와일드카드 지원:
                - *: 0개 이상의 임의 문자
                - ?: 정확히 1개의 임의 문자
                - [abc]: a, b, c 중 하나
                - [a-z]: a부터 z까지 중 하나
                예시:
                - "user:*": user로 시작하는 모든 키
                - "session:user_123_*": 특정 사용자 세션 키들
                - "cache_*_temp": 임시 캐시 키들

        Returns:
            int: 삭제된 키의 개수
                0: 패턴과 일치하는 키가 없었거나 캐시 비활성화
                >0: 성공적으로 삭제된 키 개수

        무효화 과정:
            1. 연결 상태 확인
            2. 키 접두사와 패턴 결합 ({prefix}:{pattern})
            3. SCAN_ITER로 패턴 매칭 키 점진적 조회
            4. 매칭된 키들을 일괄 DELETE 명령으로 삭제

        패턴 예시:
            - "user:session:*": 모든 사용자 세션
            - "api:response:*2024*": 2024년 API 응답 캐시
            - "temp:*": 모든 임시 데이터
            - "*:expired": 만료 예정 데이터

        성능 고려사항:
            - SCAN_ITER 사용으로 블로킹 방지
            - 패턴 복잡도에 따라 처리 시간 변동
            - 매칭되는 키가 많을수록 처리 시간 증가
            - 일괄 삭제로 네트워크 효율성 보장

        사용 시나리오:
            - 특정 기능 업데이트 후 관련 캐시 무효화
            - 시간 기반 데이터 정리 (날짜별, 시간별)
            - 사용자별 또는 그룹별 캐시 관리
            - 임시 캐시나 테스트 데이터 정리

        주의사항:
            - 패턴이 너무 광범위하면 성능 저하 가능
            - 실수로 중요한 캐시가 삭제되지 않도록 주의
            - 패턴 테스트 후 production 환경에서 사용 권장

        Example:
            ```python
            # 특정 사용자의 모든 캐시 삭제
            deleted = await cache.invalidate_pattern("user:12345:*")

            # 임시 캐시 정리
            deleted = await cache.invalidate_pattern("temp:*")

            # 만료된 세션 정리
            deleted = await cache.invalidate_pattern("session:*:expired")
            ```
        """
        if not self._connected or not self._client:
            return 0

        try:
            full_pattern = f"{self.config.key_prefix}:{pattern}"
            keys = []

            async for key in self._client.scan_iter(match=full_pattern):
                keys.append(key)

            if keys:
                return await self._client.delete(*keys)
            return 0

        except Exception as e:
            logger.warning("패턴 캐시 무효화 실패", pattern=pattern, error=str(e))
            return 0

    def cache_key_for_query(self, query: str, limit: int, **kwargs: Any) -> str:
        """
        검색 쿼리를 위한 고유한 캐시 키 생성

        쿼리 매개변수들을 조합하여 일관되고 고유한 캐시 키를 생성합니다.
        동일한 매개변수 조합은 항상 같은 키를 생성하여 캐시 히트를 보장합니다.

        Args:
            query (str): 검색 쿼리 문자열
                사용자가 입력한 검색어
            limit (int): 최대 결과 개수
                검색 결과 제한 수
            **kwargs: 추가 검색 매개변수
                리트리버별 고유한 옵션들
                예: domain_filter, score_threshold, search_depth

        Returns:
            str: JSON 직렬화된 캐시 키 문자열
                매개변수들이 정렬된 상태로 JSON 문자열화
                동일한 매개변수 조합 = 동일한 키 보장

        키 생성 알고리즘:
            1. 기본 매개변수 (query, limit) 설정
            2. 추가 매개변수 (**kwargs) 병합
            3. 키 기준으로 사전순 정렬 (일관성 보장)
            4. JSON 직렬화 (sort_keys=True)

        키 구조 예시:
            ```json
            {
                "domain_filter": ["example.com"],
                "limit": 10,
                "query": "python tutorial",
                "score_threshold": 0.8
            }
            ```

        일관성 보장:
            - 매개변수 순서에 관계없이 동일한 키 생성
            - 타입 안전성 (JSON 직렬화 가능한 값만 허용)
            - 특수문자와 유니코드 안전 처리

        성능 특징:
            - O(n log n) 시간 복잡도 (n: 매개변수 개수)
            - 메모리 효율적인 문자열 생성
            - 해시 충돌 최소화

        사용 예시:
            ```python
            # 기본 쿼리
            key1 = cache.cache_key_for_query("python", 10)

            # 추가 옵션 포함
            key2 = cache.cache_key_for_query(
                "python", 10,
                domain_filter=["stackoverflow.com"],
                score_threshold=0.5
            )

            # 매개변수 순서가 달라도 같은 키 생성
            key3 = cache.cache_key_for_query(
                query="python",
                limit=10,
                score_threshold=0.5,
                domain_filter=["stackoverflow.com"]
            )
            assert key2 == key3  # True
            ```

        Note:
            생성된 키는 _generate_key() 메서드에서 추가 처리됩니다.
            (네임스페이스 추가, 길이 제한 등)
        """
        # 쿼리 파라미터를 정렬하여 일관된 키 생성
        params = {"query": query, "limit": limit, **kwargs}

        # 정렬된 파라미터로 키 생성
        sorted_params = json.dumps(params, sort_keys=True)
        return sorted_params


# 캐시 데코레이터 함수
def cached(
    namespace: str, ttl: Optional[int] = None, key_func: Optional[Callable] = None
):
    """
    메서드 캐싱을 위한 데코레이터 팩토리

    비동기 메서드에 자동 캐싱 기능을 추가하는 데코레이터입니다.
    메서드 호출 시 캐시를 먼저 확인하고, 캐시 미스인 경우에만 실제 메서드를 실행합니다.

    Args:
        namespace (str): 캐시 네임스페이스
            캐시 도메인 구분을 위한 식별자
            예: "user_data", "api_response", "computed_result"
        ttl (Optional[int]): 캐시 유효 시간 (초 단위)
            None: RedisCache의 기본 TTL 사용
            정수: 지정된 시간 후 자동 만료
        key_func (Optional[Callable]): 커스텀 키 생성 함수
            None: 기본 키 생성 로직 사용 (함수명:args:kwargs)
            함수: 사용자 정의 키 생성 로직

    Returns:
        Callable: 실제 데코레이터 함수
            메서드를 캐싱 기능이 있는 래퍼로 변환

    데코레이터 동작 순서:
        1. 메서드 호출 시 캐시 존재 여부 확인
        2. 캐시 히트: 즉시 캐시된 값 반환
        3. 캐시 미스: 원본 메서드 실행
        4. 실행 결과를 캐시에 저장
        5. 결과 반환

    사용 조건:
        - 데코레이트된 클래스에 _cache 속성 필요
        - _cache는 RedisCache 인스턴스여야 함
        - 비동기 메서드에만 적용 가능

    키 생성 로직:
        - 기본: "{함수명}:{str(args)}:{str(kwargs)}"
        - 커스텀: key_func(*args, **kwargs) 결과 사용

    Example:
        ```python
        class UserService:
            def __init__(self):
                self._cache = RedisCache(cache_config)

            @cached("user_data", ttl=600)
            async def get_user_profile(self, user_id: str):
                # 실제 데이터베이스에서 사용자 정보 조회
                return await db.fetch_user(user_id)

            @cached("computed", key_func=lambda x, y: f"sum_{x}_{y}")
            async def expensive_calculation(self, x: int, y: int):
                # 복잡한 계산 수행
                return await complex_computation(x, y)
        ```

    성능 특징:
        - 캐시 히트 시 원본 메서드 실행 건너뛰기
        - 네트워크/데이터베이스 호출 최소화
        - 메모리 기반 고속 데이터 접근

    제한사항:
        - 캐시가 없거나 비활성화된 경우 원본 메서드 실행
        - 복잡한 객체의 경우 직렬화 문제 가능
        - 메서드 파라미터가 JSON 직렬화 가능해야 함

    주의사항:
        - 부작용이 있는 메서드에는 사용 금지
        - 자주 변경되는 데이터에는 짧은 TTL 설정
        - 메모리 사용량 고려하여 적절한 TTL 설정
    """

    def decorator(func):
        async def wrapper(self, *args, **kwargs):
            # 캐시가 없으면 함수 실행
            if not hasattr(self, "_cache") or not self._cache:
                return await func(self, *args, **kwargs)

            # 캐시 키 생성
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # 기본 키 생성
                cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"

            # 캐시 조회
            cached_value = await self._cache.get(namespace, cache_key)
            if cached_value is not None:
                logger.debug("캐시 히트", namespace=namespace, function=func.__name__)
                return cached_value

            # 함수 실행
            result = await func(self, *args, **kwargs)

            # 결과 캐싱
            await self._cache.set(namespace, cache_key, result, ttl)

            return result

        return wrapper

    return decorator
