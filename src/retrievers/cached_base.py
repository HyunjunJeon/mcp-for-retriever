"""
캐싱이 통합된 리트리버 기본 클래스

이 모듈은 Redis 캐싱 기능이 통합된 리트리버 추상 클래스를 제공합니다.
Template Method 패턴과 Decorator 패턴을 결합하여 모든 리트리버에
투명한 캐싱 기능을 제공합니다.

주요 기능:
    - Redis 기반 자동 캐싱
    - 캐시 키 자동 생성 및 관리
    - TTL(Time To Live) 기반 만료 관리
    - 네임스페이스별 캐시 무효화
    - 캐시 실패 시 Graceful Degradation

디자인 패턴:
    - Template Method Pattern: 캐싱 로직은 공통, 검색 로직은 하위 클래스 구현
    - Decorator Pattern: 기존 리트리버에 캐싱 기능 추가
    - Strategy Pattern: 캐시 정책을 설정으로 변경 가능

성능 최적화:
    - 메모리 효율적인 스트리밍 결과 처리
    - 캐시 히트 시 네트워크/DB 액세스 건너뛰기
    - 배치 캐싱으로 Redis 호출 최소화
"""

from typing import AsyncIterator, Any, Optional
from abc import abstractmethod

from src.retrievers.base import Retriever, QueryResult, RetrieverConfig
from src.cache import RedisCache, CacheConfig


class CachedRetriever(Retriever):
    """
    Redis 캐싱이 통합된 리트리버 추상 클래스

    모든 검색 요청에 대해 자동으로 캐싱을 적용하는 베이스 클래스입니다.
    하위 클래스는 실제 검색 로직만 구현하면 캐싱 기능을 자동으로 획득합니다.

    캐싱 동작 순서:
        1. 쿼리를 기반으로 캐시 키 생성
        2. Redis에서 캐시된 결과 조회
        3. 캐시 히트: 즉시 결과 반환
        4. 캐시 미스: 실제 검색 수행 후 결과 캐싱

    사용 예시:
        ```python
        class MyRetriever(CachedRetriever):
            async def _connect_impl(self):
                # 실제 연결 로직
                pass

            async def _retrieve_impl(self, query, limit, **kwargs):
                # 실제 검색 로직
                pass
        ```

    Attributes:
        _cache (RedisCache): Redis 캐시 인스턴스
        _use_cache (bool): 캐시 사용 여부 (설정으로 제어)
    """

    def __init__(self, config: RetrieverConfig):
        """
        캐싱 리트리버 초기화

        기본 리트리버 기능과 함께 Redis 캐시 기능을 설정합니다.
        캐시 설정은 리트리버별로 독립적으로 관리됩니다.

        Args:
            config (RetrieverConfig): 리트리버 설정 딕셔너리
                추가 캐시 관련 설정:
                - redis_url (str): Redis 연결 URL (기본값: "redis://localhost:6379/0")
                - cache_ttl (int): 기본 캐시 TTL (초 단위, 기본값: 300 = 5분)
                - use_cache (bool): 캐시 사용 여부 (기본값: True)
        """
        super().__init__(config)

        # Redis 캐시 설정 초기화
        cache_config = CacheConfig(
            redis_url=config.get("redis_url", "redis://localhost:6379/0"),
            default_ttl=config.get("cache_ttl", 300),  # 5분 기본 TTL
            key_prefix=f"mcp_{self.__class__.__name__.lower()}",  # 클래스별 고유 접두사
        )

        # 캐시 인스턴스 생성
        self._cache = RedisCache(cache_config)

        # 캐시 사용 여부 (설정으로 제어 가능)
        self._use_cache = config.get("use_cache", True)

    async def connect(self) -> None:
        """
        리트리버 및 캐시 연결

        하위 클래스의 실제 연결 로직을 실행한 후 Redis 캐시에도 연결합니다.
        캐시 연결에 실패해도 리트리버 자체는 사용 가능하도록 Graceful Degradation을 적용합니다.

        연결 순서:
            1. 하위 클래스의 실제 연결 로직 (_connect_impl)
            2. Redis 캐시 연결
            3. 캐시 연결 실패 시 캐시 비활성화

        Raises:
            ConnectionError: 하위 클래스의 연결이 실패한 경우
                캐시 연결 실패는 예외를 발생시키지 않음
        """
        # 하위 클래스의 실제 연결 로직 실행 (필수)
        await self._connect_impl()

        # Redis 캐시 연결 (선택적)
        if self._use_cache:
            try:
                await self._cache.connect()
                self._log_operation("cache_connect", status="success")
            except Exception as e:
                # 캐시 연결 실패 로깅
                self._log_operation("cache_connect", status="failed", error=str(e))
                # 캐시 연결 실패해도 리트리버 자체는 사용 가능하도록 설정
                # 이는 Graceful Degradation 패턴의 적용
                self._use_cache = False

    async def disconnect(self) -> None:
        """
        리트리버 및 캐시 연결 해제

        하위 클래스의 실제 연결 해제 로직을 실행한 후 Redis 캐시 연결도 해제합니다.
        리소스 정리를 위해 모든 연결을 안전하게 종료합니다.

        해제 순서:
            1. 하위 클래스의 실제 연결 해제 로직 (_disconnect_impl)
            2. Redis 캐시 연결 해제

        예외 처리:
            각 단계에서 예외가 발생해도 다른 리소스 정리가 계속되도록 합니다.
        """
        # 하위 클래스의 실제 연결 해제 로직
        await self._disconnect_impl()

        # Redis 캐시 연결 해제
        # 캐시가 존재하고 연결되어 있는 경우에만 해제
        if self._cache and self._cache._connected:
            await self._cache.disconnect()

    async def retrieve(
        self, query: str, limit: int = 10, **kwargs: Any
    ) -> AsyncIterator[QueryResult]:
        """
        캐싱이 적용된 검색 실행

        캐시를 먼저 확인하고, 캐시 미스인 경우 실제 검색을 수행합니다.
        검색 결과는 스트리밍으로 반환되며 동시에 캐시에 저장됩니다.

        캐싱 흐름:
            1. 쿼리 매개변수로 캐시 키 생성
            2. Redis에서 캐시된 결과 조회
            3. 캐시 히트: 즉시 결과 스트리밍 반환
            4. 캐시 미스: 실제 검색 수행하며 결과를 스트리밍과 동시에 수집
            5. 검색 완료 후 결과를 캐시에 저장

        Args:
            query (str): 검색 쿼리
            limit (int): 최대 결과 수 (기본값: 10)
            **kwargs: 추가 검색 매개변수
                - cache_ttl (int): 개별 요청의 캐시 TTL (선택사항)
                - 기타 하위 클래스별 매개변수

        Yields:
            QueryResult: 검색 결과 (캐시 또는 실제 검색)
                캐시된 결과와 실제 검색 결과의 형식은 동일

        Note:
            스트리밍 방식으로 결과를 반환하므로 메모리 효율적입니다.
            캐시 미스 시에도 결과가 나오는 즉시 yield됩니다.
        """
        # 쿼리와 매개변수를 조합하여 고유한 캐시 키 생성
        cache_key = self._cache.cache_key_for_query(query, limit, **kwargs)

        # 캐시 조회 시도 (캐시가 활성화된 경우)
        if self._use_cache:
            cached_results = await self._cache.get(
                self._get_cache_namespace(), cache_key
            )

            # 캐시 히트: 저장된 결과 즉시 반환
            if cached_results is not None:
                self._log_operation(
                    "cache_hit",
                    query=query[:50],  # 긴 쿼리는 50자로 잘라서 로깅
                    namespace=self._get_cache_namespace(),
                )
                # 캐시된 결과를 하나씩 yield
                for result in cached_results:
                    yield result
                return  # 캐시 히트 시 실제 검색 건너뛰기

        # 캐시 미스 - 하위 클래스의 실제 검색 로직 호출
        results = []  # 캐싱을 위해 모든 결과 수집
        async for result in self._retrieve_impl(query, limit, **kwargs):
            results.append(result)  # 캐싱용 수집
            yield result  # 즉시 스트리밍 반환

        # 검색 결과를 캐시에 저장 (결과가 있고 캐시가 활성화된 경우)
        if self._use_cache and results:
            # 개별 요청별 TTL 설정 (없으면 기본값 사용)
            ttl = kwargs.get("cache_ttl", None)

            await self._cache.set(self._get_cache_namespace(), cache_key, results, ttl)

            # 캐시 저장 성공 로깅
            self._log_operation(
                "cache_set",
                query=query[:50],
                count=len(results),
                namespace=self._get_cache_namespace(),
            )

    async def invalidate_cache(self, pattern: Optional[str] = None) -> int:
        """
        캐시 무효화 실행

        특정 패턴이나 전체 네임스페이스의 캐시를 무효화합니다.
        데이터가 변경되었거나 강제로 최신 결과를 가져와야 할 때 사용합니다.

        Args:
            pattern (Optional[str]): 무효화할 캐시 키 패턴
                None: 현재 리트리버의 모든 캐시 무효화
                문자열: 해당 패턴과 일치하는 캐시만 무효화
                예: "search_*", "user_123_*"

        Returns:
            int: 무효화된 키의 개수
                캐시가 비활성화된 경우 0 반환

        Example:
            ```python
            # 모든 캐시 무효화
            count = await retriever.invalidate_cache()

            # 특정 사용자의 캐시만 무효화
            count = await retriever.invalidate_cache("user_123_*")
            ```
        """
        # 캐시가 비활성화된 경우 무효화할 것이 없음
        if not self._use_cache:
            return 0

        if pattern:
            # 특정 패턴의 키들만 무효화
            # 네임스페이스와 패턴을 조합하여 정확한 범위 지정
            full_pattern = f"{self._get_cache_namespace()}:{pattern}"
            return await self._cache.invalidate_pattern(full_pattern)
        else:
            # 현재 리트리버의 전체 네임스페이스 무효화
            # 다른 리트리버의 캐시에는 영향을 주지 않음
            return await self._cache.clear_namespace(self._get_cache_namespace())

    def _get_cache_namespace(self) -> str:
        """
        캐시 네임스페이스 생성

        클래스별로 고유한 캐시 네임스페이스를 생성합니다.
        이를 통해 서로 다른 리트리버의 캐시가 충돌하지 않도록 격리합니다.

        Returns:
            str: 소문자로 변환된 클래스 이름
                예: TavilyRetriever -> "tavilyretriever"
                    PostgresRetriever -> "postgresretriever"

        Note:
            Redis 키 패턴: {namespace}:{cache_key}
            예: "tavilyretriever:search_python_10_abc123"
        """
        return self.__class__.__name__.lower()

    @abstractmethod
    async def _connect_impl(self) -> None:
        """
        하위 클래스에서 구현할 실제 연결 로직

        각 리트리버별 고유한 연결 절차를 구현합니다.
        이 메서드는 connect() 메서드에서 캐시 연결 전에 호출됩니다.

        구현 예시:
            - API 클라이언트 초기화
            - 데이터베이스 연결 풀 생성
            - 인증 토큰 획득
            - 연결 상태 검증

        Raises:
            ConnectionError: 연결 실패 시 발생시켜야 함
        """
        pass

    @abstractmethod
    async def _disconnect_impl(self) -> None:
        """
        하위 클래스에서 구현할 실제 연결 해제 로직

        각 리트리버별 고유한 연결 해제 절차를 구현합니다.
        이 메서드는 disconnect() 메서드에서 캐시 해제 전에 호출됩니다.

        구현 예시:
            - API 클라이언트 종료
            - 데이터베이스 연결 풀 해제
            - 임시 파일 정리
            - 리소스 해제

        Note:
            예외가 발생해도 다른 리소스 해제에 영향을 주지 않도록
            적절한 예외 처리를 구현해야 합니다.
        """
        pass

    @abstractmethod
    async def _retrieve_impl(
        self, query: str, limit: int = 10, **kwargs: Any
    ) -> AsyncIterator[QueryResult]:
        """
        하위 클래스에서 구현할 실제 검색 로직

        캐싱 없이 순수한 검색 기능만 구현합니다.
        캐싱은 부모 클래스에서 자동으로 처리됩니다.

        Args:
            query (str): 검색 쿼리
            limit (int): 최대 결과 수
            **kwargs: 리트리버별 추가 매개변수

        Yields:
            QueryResult: 검색 결과 딕셔너리
                표준 형식을 따라야 함 (source 필드 포함 권장)

        구현 가이드라인:
            - 비동기 스트리밍으로 결과 반환
            - 메모리 효율성을 위해 한 번에 하나씩 yield
            - 에러 발생 시 적절한 예외 발생
            - 결과가 없으면 아무것도 yield하지 않음

        Example:
            ```python
            async def _retrieve_impl(self, query, limit, **kwargs):
                for i, result in enumerate(api_search(query)):
                    if i >= limit:
                        break
                    yield {"title": result.title, "url": result.url, "source": "myapi"}
            ```
        """
        pass
