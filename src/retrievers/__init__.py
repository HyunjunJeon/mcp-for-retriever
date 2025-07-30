"""
MCP 서버용 다양한 데이터 소스 리트리버 구현체 모듈

이 모듈은 MCP(Model Context Protocol) 서버에서 사용하는 다양한 데이터 소스에서 
정보를 검색하는 리트리버(Retriever) 시스템을 제공합니다. 각 리트리버는 
특정 데이터 소스(웹, 벡터DB, RDB)에 특화된 검색 기능을 구현합니다.

시스템 아키텍처:
    - 통합 인터페이스: 모든 리트리버는 동일한 Retriever 인터페이스 구현
    - 다형성 지원: 팩토리 패턴으로 런타임에 리트리버 타입 결정
    - 비동기 처리: 모든 I/O 작업은 async/await로 처리
    - 스트리밍 결과: 메모리 효율적인 결과 반환
    - 에러 처리: 계층화된 예외 시스템으로 안전한 오류 관리

리트리버 구현체:
    TavilyRetriever: 웹 검색 엔진
        - Tavily API를 통한 실시간 웹 검색
        - 도메인 필터링 및 결과 스코어링
        - 재시도 로직과 rate limiting 지원
        - 검색 깊이와 결과 품질 제어
        
    PostgresRetriever: 관계형 데이터베이스 검색
        - PostgreSQL 전문 검색 (FTS) 지원
        - 비동기 연결 풀링으로 고성능 처리
        - SQL 쿼리와 JSON 필드 검색
        - 트랜잭션 지원과 안전한 쿼리 실행
        
    QdrantRetriever: 벡터 데이터베이스 검색
        - 의미적 유사도 기반 검색
        - 임베딩 벡터 생성 및 저장
        - 동적 컬렉션 관리
        - 스코어 임계값 기반 결과 필터링

핵심 컴포넌트:
    Retriever: 모든 리트리버의 추상 기반 클래스
        - connect(), disconnect(), retrieve(), health_check() 메서드
        - 비동기 컨텍스트 매니저 지원
        - 구조화된 로깅과 메트릭 수집
        
    RetrieverFactory: 리트리버 인스턴스 생성 팩토리
        - 설정 기반 동적 객체 생성
        - 타입 안전성과 검증
        - 확장 가능한 등록 시스템
        
    예외 계층: 구조화된 에러 처리
        - RetrieverError: 기본 리트리버 예외
        - ConnectionError: 연결 관련 오류
        - QueryError: 쿼리 실행 오류

데이터 타입:
    QueryResult: 검색 결과 표준 형식
        - source: 데이터 소스 식별자
        - title, content, url 등 필수 필드
        - metadata: 추가 정보 (스코어, 타임스탬프 등)
        
    RetrieverConfig: 리트리버 설정 타입
        - 각 리트리버별 고유한 설정 매개변수
        - 연결 정보, API 키, 성능 튜닝 옵션
        
    RetrieverHealth: 건강 상태 정보
        - status: 서비스 상태 (healthy, degraded, unhealthy)
        - details: 구체적인 상태 정보

사용 예시:
    ```python
    from src.retrievers import RetrieverFactory, TavilyRetriever
    
    # 팩토리를 통한 생성
    factory = RetrieverFactory.get_default()
    config = {"type": "tavily", "api_key": "your-key"}
    retriever = factory.create(config)
    
    # 직접 생성
    tavily_config = {"api_key": "your-key"}
    retriever = TavilyRetriever(tavily_config)
    
    # 검색 실행
    async with retriever:
        async for result in retriever.retrieve("Python tutorial", limit=10):
            print(f"{result['title']}: {result['url']}")
    ```

확장성:
    - 새로운 데이터 소스 추가 시 Retriever 인터페이스만 구현
    - 팩토리에 새 리트리버 등록으로 시스템 통합
    - 설정 기반으로 리트리버 동작 커스터마이징
    - 플러그인 아키텍처로 런타임 확장 가능

성능 최적화:
    - 연결 풀링으로 리소스 효율성
    - 비동기 처리로 높은 동시성
    - 스트리밍으로 메모리 사용량 최적화
    - 캐싱 레이어 통합 지원

작성일: 2024-01-30
"""

# 기본 인터페이스와 타입 정의
from src.retrievers.base import (
    Retriever,               # 리트리버 추상 기반 클래스
    RetrieverHealth,         # 건강 상태 정보 타입
    RetrieverError,          # 기본 리트리버 예외
    ConnectionError,         # 연결 관련 예외
    QueryError,             # 쿼리 실행 예외
    QueryResult,            # 검색 결과 타입 힌트
    RetrieverConfig,        # 리트리버 설정 타입 힌트
)

# 구체적인 리트리버 구현체들
from src.retrievers.tavily import TavilyRetriever      # Tavily 웹 검색 API
from src.retrievers.postgres import PostgresRetriever  # PostgreSQL 데이터베이스
from src.retrievers.qdrant import QdrantRetriever     # Qdrant 벡터 데이터베이스

# 팩토리 패턴 구현체
from src.retrievers.factory import RetrieverFactory, RetrieverFactoryError

# 외부에서 사용 가능한 공개 API 정의
__all__ = [
    # 기본 클래스와 타입들 (인터페이스 계층)
    "Retriever",            # 모든 리트리버의 기반 추상 클래스
    "RetrieverHealth",      # 서비스 건강 상태 정보
    "RetrieverError",       # 리트리버 계층 기본 예외
    "ConnectionError",      # 데이터 소스 연결 실패 예외
    "QueryError",          # 쿼리 실행 실패 예외
    "QueryResult",         # 검색 결과 표준 형식
    "RetrieverConfig",     # 리트리버 설정 딕셔너리 타입
    
    # 구현체들 (비즈니스 로직 계층)
    "TavilyRetriever",     # Tavily API 기반 웹 검색
    "PostgresRetriever",   # PostgreSQL 기반 데이터베이스 검색
    "QdrantRetriever",     # Qdrant 기반 벡터 유사도 검색
    
    # 팩토리 패턴 (객체 생성 계층)
    "RetrieverFactory",    # 리트리버 인스턴스 생성 팩토리
    "RetrieverFactoryError", # 팩토리 관련 예외
]
