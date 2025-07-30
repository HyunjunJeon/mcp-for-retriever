# Retrievers 모듈 구조

리트리버 시스템은 다양한 데이터 소스에서 정보를 검색하는 통합 인터페이스를 제공합니다.

## 모듈 구조

```mermaid
graph TD
    retrievers[retrievers/]
    retrievers --> base[base.py<br/>추상 인터페이스]
    retrievers --> tavily[tavily.py<br/>웹 검색]
    retrievers --> qdrant[qdrant.py<br/>벡터 DB]
    retrievers --> postgres[postgres.py<br/>RDB]
    retrievers --> factory[factory.py<br/>팩토리 패턴]
    retrievers --> cached_base[cached_base.py<br/>캐싱 래퍼]
    
    base --> RetrieverABC[Retriever ABC]
    base --> RetrieverConfig[RetrieverConfig]
    
    tavily --> TavilyRetriever
    qdrant --> QdrantRetriever  
    postgres --> PostgresRetriever
    
    cached_base --> CachedRetriever
    factory --> RetrieverFactory
```

## 핵심 컴포넌트

### 1. base.py - 추상 인터페이스

```mermaid
classDiagram
    class RetrieverConfig {
        <<abstract>>
        +model_config: ConfigDict
    }
    
    class Retriever~T~ {
        <<abstract>>
        +config: T
        +__init__(config: T)
        +connect()* AsyncContextManager
        +disconnect()* None
        +retrieve(query: str, **kwargs)* AsyncIterator
        +health_check()* dict
    }
    
    class RetrieverType {
        <<enumeration>>
        TAVILY
        QDRANT
        POSTGRES
    }
    
    RetrieverConfig <|-- TavilyConfig
    RetrieverConfig <|-- QdrantConfig
    RetrieverConfig <|-- PostgresConfig
    
    Retriever <|-- TavilyRetriever
    Retriever <|-- QdrantRetriever
    Retriever <|-- PostgresRetriever
```

### 2. tavily.py - 웹 검색 구현

```mermaid
graph LR
    subgraph "TavilyRetriever"
        config[TavilyConfig]
        client[TavilyClient]
        
        search[search 메서드]
        retry[재시도 로직]
        filter[도메인 필터링]
    end
    
    subgraph "기능"
        web_search[웹 검색]
        news_search[뉴스 검색]
        context_search[컨텍스트 검색]
    end
    
    search --> retry
    retry --> client
    client --> web_search
    client --> news_search
    client --> context_search
```

**주요 기능:**
- 웹 페이지 검색
- 도메인 포함/제외 필터
- 검색 깊이 설정 (basic/advanced)
- 자동 재시도 (지수 백오프)
- 결과 점수 기반 필터링

### 3. qdrant.py - 벡터 데이터베이스 구현

```mermaid
graph TD
    subgraph "QdrantRetriever"
        config[QdrantConfig]
        client[QdrantClient]
        
        subgraph "작업"
            create_collection[컬렉션 생성]
            search_vectors[벡터 검색]
            upsert_points[포인트 추가]
            delete_points[포인트 삭제]
        end
    end
    
    subgraph "설정"
        embedding_size[임베딩 크기]
        distance_metric[거리 메트릭]
        collection_config[컬렉션 설정]
    end
    
    config --> embedding_size
    config --> distance_metric
    client --> create_collection
    client --> search_vectors
```

**주요 기능:**
- 동적 컬렉션 생성
- 다양한 거리 메트릭 지원 (Cosine, Euclidean, Dot)
- 메타데이터 필터링
- 페이로드 저장 및 검색
- 배치 작업 지원

### 4. postgres.py - 관계형 데이터베이스 구현

```mermaid
graph LR
    subgraph "PostgresRetriever"
        config[PostgresConfig]
        pool[AsyncPG Pool]
        
        subgraph "검색 유형"
            sql_search[SQL 쿼리]
            text_search[텍스트 검색]
            json_search[JSON 검색]
        end
    end
    
    subgraph "기능"
        full_text[전문 검색]
        fuzzy_search[유사 검색]
        aggregation[집계 쿼리]
    end
    
    pool --> sql_search
    pool --> text_search
    text_search --> full_text
    text_search --> fuzzy_search
```

**주요 기능:**
- 직접 SQL 쿼리 실행
- PostgreSQL 전문 검색
- JSON/JSONB 컬럼 검색
- 연결 풀링
- 트랜잭션 지원

### 5. factory.py - 팩토리 패턴

```mermaid
graph TD
    Factory[RetrieverFactory]
    Factory --> create_retriever
    
    create_retriever --> check_type{리트리버 타입?}
    check_type -->|TAVILY| create_tavily[TavilyRetriever 생성]
    check_type -->|QDRANT| create_qdrant[QdrantRetriever 생성]
    check_type -->|POSTGRES| create_postgres[PostgresRetriever 생성]
    
    create_tavily --> validate_config1[설정 검증]
    create_qdrant --> validate_config2[설정 검증]
    create_postgres --> validate_config3[설정 검증]
```

### 6. cached_base.py - 캐싱 래퍼

```mermaid
classDiagram
    class CachedRetriever~T~ {
        -retriever: Retriever~T~
        -cache: RedisCache
        -ttl: int
        +retrieve(query: str, **kwargs) AsyncIterator
        -_get_cache_key(query: str, kwargs: dict) str
        -_serialize_result(result: dict) str
        -_deserialize_result(data: str) dict
    }
    
    Retriever <|-- CachedRetriever
    CachedRetriever o-- RedisCache
    CachedRetriever o-- Retriever
```

## 데이터 흐름

```mermaid
sequenceDiagram
    participant Client
    participant Factory
    participant Retriever
    participant DataSource
    participant Cache
    
    Client->>Factory: create_retriever(type, config)
    Factory->>Retriever: __init__(config)
    Factory-->>Client: retriever instance
    
    Client->>Retriever: connect()
    Retriever->>DataSource: establish connection
    
    Client->>Retriever: retrieve(query)
    
    alt 캐싱 활성화
        Retriever->>Cache: check cache
        alt 캐시 히트
            Cache-->>Retriever: cached results
            Retriever-->>Client: results
        else 캐시 미스
            Retriever->>DataSource: execute query
            DataSource-->>Retriever: raw results
            Retriever->>Retriever: process results
            Retriever->>Cache: store in cache
            Retriever-->>Client: results
        end
    else 캐싱 비활성화
        Retriever->>DataSource: execute query
        DataSource-->>Retriever: raw results
        Retriever->>Retriever: process results
        Retriever-->>Client: results
    end
    
    Client->>Retriever: disconnect()
    Retriever->>DataSource: close connection
```

## 리트리버 설정

### TavilyConfig
```python
class TavilyConfig(RetrieverConfig):
    api_key: str
    search_depth: str = "basic"  # basic | advanced
    max_results: int = 10
    include_domains: List[str] = []
    exclude_domains: List[str] = []
    retry_attempts: int = 3
    retry_delay: float = 1.0
```

### QdrantConfig
```python
class QdrantConfig(RetrieverConfig):
    host: str = "localhost"
    port: int = 6333
    grpc_port: int = 6334
    api_key: Optional[str] = None
    use_grpc: bool = False
    collection_name: str = "default"
    embedding_size: int = 384
    distance_metric: str = "Cosine"
```

### PostgresConfig
```python
class PostgresConfig(RetrieverConfig):
    dsn: str  # postgresql://user:pass@host:port/db
    min_pool_size: int = 10
    max_pool_size: int = 20
    command_timeout: float = 60.0
    default_search_limit: int = 100
```

## 새로운 리트리버 추가하기

### 1. 설정 클래스 정의

```python
from src.retrievers.base import RetrieverConfig

class MyRetrieverConfig(RetrieverConfig):
    endpoint: str
    api_key: str
    timeout: float = 30.0
```

### 2. 리트리버 구현

```python
from src.retrievers.base import Retriever
from typing import AsyncIterator, Dict, Any

class MyRetriever(Retriever[MyRetrieverConfig]):
    async def connect(self) -> None:
        # 연결 초기화
        self.client = MyClient(self.config.endpoint)
        
    async def disconnect(self) -> None:
        # 연결 종료
        await self.client.close()
        
    async def retrieve(
        self, 
        query: str, 
        **kwargs
    ) -> AsyncIterator[Dict[str, Any]]:
        # 검색 구현
        results = await self.client.search(query)
        for result in results:
            yield {
                "id": result.id,
                "content": result.content,
                "metadata": result.metadata
            }
            
    async def health_check(self) -> Dict[str, Any]:
        # 상태 확인
        return {
            "status": "healthy",
            "connected": self.client.is_connected
        }
```

### 3. 팩토리에 등록

```python
# factory.py에 추가
RetrieverType.MY_RETRIEVER: MyRetriever
```

## 성능 최적화

### 1. 연결 풀링
- PostgreSQL: asyncpg 연결 풀 사용
- Qdrant: HTTP/gRPC 연결 재사용

### 2. 배치 처리
- 여러 쿼리를 배치로 처리
- 벡터 검색 시 배치 임베딩

### 3. 캐싱 전략
- 자주 검색되는 쿼리 캐싱
- TTL 기반 자동 만료
- 캐시 워밍 지원

### 4. 비동기 처리
- AsyncIterator로 스트리밍 결과
- 동시 다중 검색 지원

## 에러 처리

```mermaid
graph TD
    Error[RetrieverError]
    Error --> ConnectionError[연결 실패]
    Error --> QueryError[쿼리 실패]
    Error --> TimeoutError[시간 초과]
    Error --> RateLimitError[요청 제한]
    
    ConnectionError --> Retry{재시도?}
    Retry -->|Yes| Reconnect[재연결]
    Retry -->|No| Fail[실패 반환]
```

## 모니터링 메트릭

- **요청 수**: 리트리버별 요청 카운트
- **응답 시간**: 평균, P95, P99 레이턴시
- **에러율**: 리트리버별 에러 비율
- **캐시 히트율**: 캐시 효율성
- **연결 상태**: 데이터 소스 연결 상태