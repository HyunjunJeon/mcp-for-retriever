"""
리트리버 기본 인터페이스 모듈

이 모듈은 모든 데이터 소스(웹, 벡터 DB, RDB 등)에서 정보를 검색하는
통합 인터페이스를 정의합니다. 모든 리트리버 구현체는 이 인터페이스를
상속받아 구현해야 합니다.

주요 구성요소:
    - Retriever: 추상 기본 클래스로 모든 리트리버가 구현해야 하는 인터페이스
    - RetrieverHealth: 리트리버의 상태 정보를 담는 모델
    - RetrieverError: 리트리버 관련 예외의 기본 클래스
    - ConnectionError: 연결 실패 시 발생하는 예외
    - QueryError: 쿼리 실행 실패 시 발생하는 예외

사용 예제:
    ```python
    from src.retrievers.base import Retriever
    
    class MyRetriever(Retriever):
        async def connect(self) -> None:
            # 데이터 소스 연결
            pass
            
        async def retrieve(self, query: str) -> AsyncIterator[dict[str, Any]]:
            # 쿼리 실행 및 결과 반환
            yield {"result": "data"}
    ```

작성일: 2024-01-30
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Any, Self
from pydantic import BaseModel, Field
import structlog
from datetime import datetime, timezone

# Python 3.12+ 타입 별칭 정의
# QueryResult: 검색 결과를 담는 딕셔너리 타입
# RetrieverConfig: 리트리버 설정을 담는 딕셔너리 타입
type QueryResult = dict[str, Any]
type RetrieverConfig = dict[str, Any]


class RetrieverHealth(BaseModel):
    """
    리트리버 상태 정보 모델
    
    리트리버의 현재 상태를 나타내는 데이터 모델입니다.
    서비스의 건강 상태, 연결 상태, 에러 정보 등을 포함합니다.
    
    Attributes:
        healthy (bool): 서비스의 정상 작동 여부
        service_name (str): 리트리버 서비스 이름
        details (dict[str, Any] | None): 추가 상태 정보 (선택사항)
        error (str | None): 에러 메시지 (에러 발생 시)
        checked_at (datetime): 상태 확인 시각 (UTC)
    """

    healthy: bool
    service_name: str
    details: dict[str, Any] | None = Field(default=None)
    error: str | None = Field(default=None)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RetrieverError(Exception):
    """
    리트리버 예외의 기본 클래스
    
    모든 리트리버 관련 예외의 부모 클래스입니다.
    리트리버 이름과 상세 정보를 포함하여 디버깅을 용이하게 합니다.
    
    Attributes:
        message (str): 에러 메시지
        retriever_name (str): 예외가 발생한 리트리버 이름
        details (dict[str, Any]): 추가 디버깅 정보
    """

    def __init__(
        self, message: str, retriever_name: str, details: dict[str, Any] | None = None
    ):
        """리트리버 예외 초기화
        
        Args:
            message: 에러 메시지
            retriever_name: 예외가 발생한 리트리버 이름
            details: 추가 디버깅 정보 (선택사항)
        """
        super().__init__(message)
        self.retriever_name = retriever_name
        self.details = details or {}


class ConnectionError(RetrieverError):
    """
    데이터 소스 연결 실패 예외
    
    데이터 소스에 연결할 수 없거나 연결이 끊어진 경우 발생합니다.
    네트워크 문제, 인증 실패, 서비스 중단 등의 경우에 사용됩니다.
    """

    pass


class QueryError(RetrieverError):
    """
    쿼리 실행 실패 예외
    
    쿼리 실행 중 발생하는 에러를 나타냅니다.
    잘못된 쿼리 형식, 타임아웃, 결과 처리 오류 등의 경우에 사용됩니다.
    """

    pass


class Retriever(ABC):
    """
    모든 리트리버의 추상 기본 클래스
    
    이 클래스는 다양한 데이터 소스에서 정보를 검색하는 통합된 인터페이스를
    제공합니다. 모든 구체적인 리트리버 구현체는 이 클래스를 상속받아
    필수 메서드들을 구현해야 합니다.
    
    비동기 컨텍스트 매니저를 지원하여 리소스의 안전한 관리를 보장합니다.
    with 구문을 사용하면 자동으로 연결과 해제가 처리됩니다.
    
    Attributes:
        config (RetrieverConfig): 리트리버 설정 딕셔너리
        logger (structlog.BoundLogger): 구조화된 로거 인스턴스
        _connected (bool): 데이터 소스 연결 상태
        
    주요 메서드:
        connect(): 데이터 소스에 연결
        disconnect(): 연결 종료
        retrieve(): 쿼리 실행 및 결과 반환
        health_check(): 서비스 상태 확인
        
    사용 예제:
        ```python
        # 컨텍스트 매니저로 사용
        async with MyRetriever(config) as retriever:
            async for result in retriever.retrieve("검색어"):
                print(result)
                
        # 수동 연결 관리
        retriever = MyRetriever(config)
        await retriever.connect()
        try:
            async for result in retriever.retrieve("검색어"):
                print(result)
        finally:
            await retriever.disconnect()
        ```
    """

    def __init__(self, config: RetrieverConfig) -> None:
        """
        리트리버 초기화
        
        설정 정보를 받아 리트리버를 초기화합니다.
        각 리트리버 구현체는 자신만의 설정 구조를 정의할 수 있습니다.

        Args:
            config: 리트리버별 설정 딕셔너리
                - 각 리트리버마다 필요한 설정이 다름
                - 예: API 키, 연결 URL, 타임아웃 설정 등
        """
        self.config = config
        # 클래스 이름을 로거 이름으로 사용하여 로그 추적 용이
        self.logger = structlog.get_logger(self.__class__.__name__)
        self._connected = False

    @property
    def connected(self) -> bool:
        """
        데이터 소스 연결 상태 확인
        
        Returns:
            bool: 연결되어 있으면 True, 아니면 False
        """
        return self._connected

    @abstractmethod
    async def connect(self) -> None:
        """
        데이터 소스에 연결
        
        이 메서드는 데이터 소스와의 연결을 설정하는 모든 작업을 처리해야 합니다:
        - 연결 풀 생성 (데이터베이스, HTTP 클라이언트 등)
        - 서비스 인증 (API 키, OAuth 토큰 등)
        - 설정 유효성 검증
        - 초기 연결 테스트
        
        구현 시 고려사항:
        - 재시도 로직 구현 권장
        - 연결 타임아웃 설정
        - 리소스 제한 고려

        Raises:
            ConnectionError: 연결을 설정할 수 없는 경우
                - 네트워크 오류
                - 인증 실패  
                - 잘못된 설정
                - 서비스 이용 불가
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """
        연결 종료 및 리소스 정리
        
        이 메서드는 모든 정리 작업을 처리해야 합니다:
        - 연결 풀 닫기
        - 할당된 리소스 해제 
        - 진행 중인 작업 취소
        - 연결 종료 로깅
        
        구현 시 고려사항:
        - 예외가 발생해도 리소스 정리 보장
        - 이미 종료된 연결 처리
        - 정리 작업의 타임아웃 설정
        """
        pass

    @abstractmethod
    async def retrieve(
        self, query: str, limit: int = 10, **kwargs: Any
    ) -> AsyncIterator[QueryResult]:
        """
        주어진 쿼리로 정보를 검색하고 결과를 스트리밍으로 반환
        
        이 메서드는 데이터 소스에서 쿼리와 관련된 정보를 비동기적으로 검색합니다.
        결과는 AsyncIterator로 반환되어 대용량 결과도 메모리 효율적으로 처리할 수 있습니다.
        
        Args:
            query (str): 검색할 쿼리 문자열
            limit (int): 반환할 최대 결과 수 (기본값: 10)
            **kwargs: 리트리버별 추가 매개변수
                - filters (dict): 필터링 조건
                - timeout (float): 검색 타임아웃 (초)
                - include_metadata (bool): 메타데이터 포함 여부
                - sort_by (str): 정렬 기준
        
        Yields:
            QueryResult: 검색 결과 딕셔너리
                - id (str): 결과 고유 식별자
                - content (str): 검색된 내용
                - score (float): 관련성 점수 (0.0 ~ 1.0)
                - metadata (dict): 추가 메타데이터
                - source (str): 데이터 출처
        
        Raises:
            QueryError: 쿼리 실행 중 오류 발생 시
                - 잘못된 쿼리 형식
                - 검색 타임아웃
                - 결과 처리 오류
            ConnectionError: 연결이 끊어진 경우
            
        Example:
            ```python
            async for result in retriever.retrieve("파이썬 비동기", limit=5):
                if result['score'] > 0.8:
                    print(f"높은 관련성: {result['content']}")
            ```
        """
        pass

    @abstractmethod
    async def health_check(self) -> RetrieverHealth:
        """
        서비스 상태 확인
        
        이 메서드는 리트리버와 데이터 소스의 전반적인 상태를 확인합니다:
        - 연결 활성 상태 확인
        - 서비스 응답 여부 확인
        - 기본 기능 작동 테스트 (예: 간단한 쿼리 실행)
        - 리소스 사용량 확인 (선택사항)
        
        구현 시 고려사항:
        - 빠른 응답을 위해 간단한 작업만 수행
        - 타임아웃 설정으로 무한 대기 방지
        - 상세한 디버깅 정보 포함

        Returns:
            RetrieverHealth: 현재 상태 정보
                - healthy: 정상 작동 여부
                - service_name: 서비스 이름
                - details: 추가 상태 정보 (응답 시간, 버전 등)
                - error: 에러 메시지 (문제 발생 시)
                - checked_at: 확인 시각
        """
        pass

    async def __aenter__(self) -> Self:
        """
        비동기 컨텍스트 매니저 진입
        
        async with 구문 사용 시 자동으로 연결을 설정합니다.
        
        Returns:
            Self: 연결된 리트리버 인스턴스
            
        Raises:
            ConnectionError: 연결 실패 시
        """
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """
        비동기 컨텍스트 매니저 종료
        
        async with 구문을 벗어날 때 자동으로 연결을 종료합니다.
        예외가 발생해도 항상 정리 작업이 수행됩니다.
        
        Args:
            exc_type: 발생한 예외의 타입 (없으면 None)
            exc_val: 발생한 예외 인스턴스 (없으면 None)
            exc_tb: 예외 트레이스백 (없으면 None)
        """
        # 예외 발생 여부와 관계없이 항상 연결 종료
        await self.disconnect()

    def _log_operation(self, operation: str, **kwargs: Any) -> None:
        """
        리트리버 작업 로깅
        
        구조화된 로깅을 사용하여 리트리버 작업을 기록합니다.
        모든 로그에 리트리버 타입과 작업 정보가 포함됩니다.
        
        Args:
            operation: 작업 이름 (예: "connect", "retrieve", "disconnect")
            **kwargs: 추가 로깅 컨텍스트
                - query: 검색 쿼리
                - duration_ms: 작업 소요 시간
                - result_count: 결과 개수
                - error: 에러 정보
        """
        self.logger.info(
            "retriever_operation",
            operation=operation,
            retriever_type=self.__class__.__name__,
            **kwargs,
        )
