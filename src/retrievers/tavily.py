"""
Tavily 웹 검색 리트리버 구현

이 모듈은 Tavily API를 사용하여 웹 검색 기능을 제공하는 리트리버를 구현합니다.
Tavily는 AI 최적화 검색 결과를 제공하는 전문 검색 API입니다.

주요 기능:
    - 비동기 웹 검색
    - 속도 제한 처리 및 자동 재시도
    - 도메인 포함/제외 필터링
    - 검색 깊이 설정 (basic/advanced)
    - 결과 점수 기반 정렬

환경 변수:
    TAVILY_API_KEY: Tavily API 키 (필수)
"""

from typing import AsyncIterator, Any
import httpx
import asyncio

from src.retrievers.base import (
    Retriever,
    RetrieverHealth,
    ConnectionError,
    QueryError,
    QueryResult,
    RetrieverConfig,
)
from src.utils.connection_manager import HTTPSessionManager


class TavilyRetriever(Retriever):
    """
    Tavily 웹 검색 API를 사용하는 리트리버 구현체

    Tavily API를 통해 AI 최적화된 웹 검색 결과를 제공합니다.
    각 검색 결과는 관련성 점수와 함께 제공되며, 비동기 스트리밍으로
    효율적으로 처리됩니다.

    Attributes:
        BASE_URL (str): Tavily API 기본 URL
        api_key (str): API 인증 키
        max_results (int): 최대 결과 수
        search_depth (str): 검색 깊이 ('basic' 또는 'advanced')
        timeout (int): 요청 타임아웃 (초)
    """

    BASE_URL = "https://api.tavily.com"  # Tavily API 엔드포인트

    def __init__(self, config: RetrieverConfig):
        """
        Tavily 리트리버 초기화

        설정 정보를 받아 Tavily API 클라이언트를 초기화합니다.

        Args:
            config: 설정 딕셔너리
                - api_key (str): Tavily API 키 (필수)
                - max_results (int): 검색당 최대 결과 수 (기본값: 10)
                - search_depth (str): 검색 깊이 'basic' 또는 'advanced' (기본값: 'basic')
                    - basic: 빠른 검색, 기본 결과
                    - advanced: 심층 검색, 더 많은 컨텍스트
                - timeout (int): 요청 타임아웃 (초 단위, 기본값: 30)

        Raises:
            ValueError: api_key가 제공되지 않은 경우
        """
        super().__init__(config)

        # 설정 추출 및 검증
        self.api_key = config.get("api_key")
        if not self.api_key:
            raise ValueError("api_key is required for TavilyRetriever")

        self.max_results = config.get("max_results", 10)
        self.search_depth = config.get("search_depth", "basic")
        self.timeout = config.get("timeout", 30)

        # HTTP 세션 매니저 설정
        session_config = {
            "max_connections": config.get("max_connections", 100),
            "max_keepalive_connections": config.get("max_keepalive_connections", 20),
            "keepalive_expiry": config.get("keepalive_expiry", 30),
            "timeout": self.timeout,
            "retries": config.get("retries", 3),
        }

        self._session_manager = HTTPSessionManager(session_config)

    async def connect(self) -> None:
        """
        Tavily API에 연결

        비동기 HTTP 클라이언트를 생성하고 연결을 테스트합니다.
        연결 풀을 사용하여 효율적인 HTTP 통신을 지원합니다.

        Raises:
            ConnectionError: Tavily API 연결 실패 시
                - 네트워크 오류
                - 잘못된 API 키
                - 서비스 이용 불가
        """
        try:
            # HTTP 세션 매니저 초기화
            await self._session_manager.initialize()

            # 연결 테스트
            await self._test_connection()

            self._connected = True
            self._log_operation(
                "connect",
                status="success",
                reuse_rate=self._session_manager.metrics.calculate_reuse_rate(),
            )

        except Exception as e:
            self._connected = False
            self._log_operation("connect", status="failed", error=str(e))
            raise ConnectionError(
                f"Failed to connect to Tavily API: {e}", "TavilyRetriever"
            )

    async def disconnect(self) -> None:
        """
        Tavily API 연결 종료

        HTTP 클라이언트를 닫고 리소스를 정리합니다.
        예외가 발생해도 연결 상태를 초기화합니다.
        """
        await self._session_manager.close()

        self._connected = False
        self._log_operation(
            "disconnect",
            total_requests=self._session_manager.metrics.total_requests,
            reuse_rate=self._session_manager.metrics.calculate_reuse_rate(),
        )

    async def retrieve(
        self, query: str, limit: int = 10, **kwargs: Any
    ) -> AsyncIterator[QueryResult]:
        """
        Tavily API를 사용한 웹 검색

        주어진 쿼리로 웹을 검색하고 결과를 비동기 스트리밍으로 반환합니다.
        각 결과는 개별적으로 yield되어 메모리 효율성을 보장합니다.

        Args:
            query (str): 검색 쿼리 문자열
            limit (int): 반환할 최대 결과 수 (기본값: 10)
            **kwargs: 추가 검색 매개변수
                - include_domains (list[str]): 포함할 도메인 목록
                - exclude_domains (list[str]): 제외할 도메인 목록
                - include_answer (bool): AI 요약 답변 포함 여부
                - include_raw_content (bool): 원본 컨텐츠 포함 여부

        Yields:
            QueryResult: 검색 결과 딕셔너리
                - title: 결과 제목
                - url: 웹 페이지 URL
                - content: 요약된 컨텐츠
                - score: 관련성 점수 (0.0 ~ 1.0)
                - published_date: 게시일
                - source: 소스 이름 ("tavily")
                - metadata: 추가 메타데이터

        Raises:
            ConnectionError: 연결되지 않은 경우
            QueryError: 검색 실패 시
        """
        if not self._connected:
            raise ConnectionError("Not connected to Tavily API", "TavilyRetriever")

        try:
            # API 검색 수행
            response_data = await self._search(query, limit, **kwargs)

            # 결과를 하나씩 yield
            results = response_data.get("results", [])
            for i, result in enumerate(results):
                if i >= limit:
                    break

                yield self._format_result(result)

        except httpx.HTTPError as e:
            self._log_operation("retrieve", status="failed", error=str(e))
            raise QueryError(f"Search failed: {e}", "TavilyRetriever")

    async def health_check(self) -> RetrieverHealth:
        """
        Tavily API 상태 확인

        API 연결 상태와 서비스 가용성을 확인합니다.

        Returns:
            RetrieverHealth: 현재 상태 정보
                - healthy: 정상 작동 여부
                - service_name: "TavilyRetriever"
                - details: 연결 상태, API 엔드포인트, 타임아웃 설정
                - error: 에러 메시지 (문제 발생 시)
        """
        if not self._connected:
            return RetrieverHealth(
                healthy=False,
                service_name="TavilyRetriever",
                details={"connected": False},
                error="Not connected",
            )

        try:
            # 세션 매니저의 health check 사용
            session_health = await self._session_manager.health_check()

            return RetrieverHealth(
                healthy=session_health["status"] == "healthy",
                service_name="TavilyRetriever",
                details={
                    "connected": True,
                    "api_endpoint": self.BASE_URL,
                    "timeout": self.timeout,
                    "total_requests": session_health.get("total_requests", 0),
                    "connection_errors": session_health.get("connection_errors", 0),
                    "reuse_rate": session_health.get("reuse_rate", 0),
                },
            )

        except Exception as e:
            return RetrieverHealth(
                healthy=False,
                service_name="TavilyRetriever",
                details={"connected": self._connected},
                error=str(e),
            )

    async def _test_connection(self) -> bool:
        """
        API 연결 테스트

        Tavily API 연결을 확인합니다.
        Tavily API는 별도의 테스트 엔드포인트가 없고 HEAD 메서드를 지원하지 않으므로,
        실제 검색 요청을 보내는 대신 API 키가 설정되어 있는지만 확인합니다.

        Returns:
            bool: 연결이 정상이면 True

        Raises:
            Exception: API 키가 없을 때
        """
        # API 키 확인
        if not self.config.get("api_key"):
            raise ValueError("Tavily API key is not configured")

        # Tavily는 실제 검색 요청에서만 API 키 유효성을 확인하므로
        # 여기서는 키 존재 여부만 확인
        return True

    async def _search(self, query: str, limit: int, **kwargs: Any) -> dict[str, Any]:
        """
        실제 API 검색 요청 수행

        Tavily API에 POST 요청을 보내고 결과를 받아옵니다.
        속도 제한(429) 에러에 대해 자동 재시도를 수행합니다.

        Args:
            query (str): 검색 쿼리
            limit (int): 결과 제한
            **kwargs: 추가 검색 매개변수

        Returns:
            dict[str, Any]: API 응답 데이터
                - results: 검색 결과 리스트
                - answer: AI 요약 답변 (선택사항)
                - query: 원본 쿼리

        Raises:
            httpx.HTTPError: API 요청 실패 시
            RuntimeError: 클라이언트 초기화 오류
        """
        # 검색 매개변수 준비
        search_params = {
            "api_key": self.api_key,
            "query": query,
            "max_results": min(limit, self.max_results),
            "search_depth": self.search_depth,
            **kwargs,
        }

        # 속도 제한 처리를 위한 재시도 로직
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with self._session_manager.session() as session:
                    response = await session.post(
                        f"{self.BASE_URL}/search", json=search_params
                    )
                    response.raise_for_status()
                    return response.json()

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:  # 속도 제한
                    if attempt < max_retries - 1:
                        # Retry-After 헤더에서 대기 시간 추출 (기본값: 1초)
                        retry_after = int(e.response.headers.get("Retry-After", "1"))
                        self._log_operation(
                            "search",
                            status="rate_limited",
                            retry_after=retry_after,
                            attempt=attempt + 1,
                        )
                        # 지정된 시간만큼 대기 후 재시도
                        await asyncio.sleep(retry_after)
                        continue
                raise

        # 여기에 도달할 수 없지만 타입 체커를 위해 포함
        raise RuntimeError("Failed to get response from API")

    def _format_result(self, result: dict[str, Any]) -> QueryResult:
        """
        API 결과를 표준 QueryResult 형식으로 변환

        Tavily API의 응답 형식을 MCP 서버의 표준 결과 형식으로
        변환합니다. 모든 리트리버가 동일한 형식을 사용하도록 합니다.

        Args:
            result (dict[str, Any]): Tavily API의 원본 결과

        Returns:
            QueryResult: 표준화된 결과 딕셔너리
                - title: 검색 결과 제목
                - url: 웹 페이지 URL
                - content: 요약된 컨텐츠
                - score: 관련성 점수 (0.0 ~ 1.0)
                - published_date: 게시일
                - source: 데이터 출처 ("tavily" 고정)
                - metadata: 추가 메타데이터 (도메인, 저자 등)
        """
        return {
            "title": result.get("title", ""),
            "url": result.get("url", ""),
            "content": result.get("content", ""),
            "score": result.get("score", 0.0),
            "published_date": result.get("published_date"),
            "source": "tavily",
            "metadata": {
                "domain": result.get("domain"),
                "author": result.get("author"),
            },
        }
