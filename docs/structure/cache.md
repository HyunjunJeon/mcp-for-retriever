# Cache 모듈 구조

캐싱 시스템은 Redis를 사용하여 리트리버 결과를 캐싱하고 성능을 최적화합니다.

## 모듈 구조

```mermaid
graph TD
    cache[cache/]
    cache --> init[__init__.py<br/>공개 인터페이스]
    cache --> redis_cache[redis_cache.py<br/>Redis 구현]
    
    redis_cache --> RedisCache[RedisCache 클래스]
    redis_cache --> CacheConfig[설정]
    redis_cache --> Serialization[직렬화]
```

## 주요 컴포넌트

### RedisCache 클래스

```mermaid
classDiagram
    class RedisCache {
        -redis_client: Redis
        -default_ttl: int
        -key_prefix: str
        -max_connections: int
        +connect() None
        +disconnect() None
        +get(key: str) Optional[Any]
        +set(key: str, value: Any, ttl: int) bool
        +delete(key: str) bool
        +exists(key: str) bool
        +clear(pattern: str) int
        +get_stats() Dict[str, Any]
    }
    
    class CacheConfig {
        +host: str = "localhost"
        +port: int = 6379
        +db: int = 0
        +password: Optional[str]
        +default_ttl: int = 300
        +key_prefix: str = "mcp"
        +max_connections: int = 50
    }
    
    class CacheError {
        +message: str
        +original_error: Exception
    }
    
    RedisCache --> CacheConfig
    RedisCache --> CacheError
```

## 캐싱 전략

### 1. 캐시 키 생성

```mermaid
graph LR
    subgraph "키 구성요소"
        prefix[Prefix<br/>mcp]
        retriever[Retriever<br/>tavily]
        query_hash[Query Hash<br/>md5]
        params_hash[Params Hash<br/>옵션]
    end
    
    prefix --> key[캐시 키]
    retriever --> key
    query_hash --> key
    params_hash --> key
    
    key --> result[mcp:tavily:a1b2c3:d4e5f6]
```

키 생성 알고리즘:
```python
def generate_cache_key(
    retriever_type: str,
    query: str,
    params: Dict[str, Any]
) -> str:
    # 쿼리 해시
    query_hash = hashlib.md5(query.encode()).hexdigest()[:8]
    
    # 파라미터 정렬 및 해시
    sorted_params = json.dumps(params, sort_keys=True)
    params_hash = hashlib.md5(sorted_params.encode()).hexdigest()[:8]
    
    return f"{prefix}:{retriever_type}:{query_hash}:{params_hash}"
```

### 2. TTL 관리

```mermaid
graph TD
    subgraph "TTL 정책"
        default[기본 TTL<br/>5분]
        web_search[웹 검색<br/>10분]
        vector_search[벡터 검색<br/>30분]
        db_search[DB 검색<br/>5분]
    end
    
    subgraph "TTL 조정"
        frequent[자주 사용<br/>TTL 연장]
        stale[오래된 데이터<br/>TTL 단축]
        realtime[실시간 데이터<br/>TTL 최소화]
    end
```

### 3. 캐시 무효화

```mermaid
sequenceDiagram
    participant App
    participant Cache
    participant Redis
    
    Note over App: 데이터 업데이트 발생
    
    App->>Cache: invalidate(pattern)
    Cache->>Redis: SCAN pattern*
    Redis-->>Cache: matching keys
    Cache->>Redis: DEL keys
    Redis-->>Cache: deleted count
    Cache-->>App: invalidation result
    
    Note over App: 관련 캐시 제거됨
```

## 직렬화 전략

### 지원하는 데이터 타입

```python
SERIALIZABLE_TYPES = {
    dict: json.dumps,
    list: json.dumps,
    str: str,
    int: str,
    float: str,
    bool: lambda x: "1" if x else "0",
    datetime: lambda x: x.isoformat()
}
```

### 직렬화 프로세스

```mermaid
graph LR
    Data[원본 데이터] --> Check{타입 확인}
    Check -->|Dict/List| JSON[JSON 직렬화]
    Check -->|String| Direct[직접 저장]
    Check -->|Number| String[문자열 변환]
    Check -->|Object| Pickle[Pickle 직렬화]
    
    JSON --> Compress{압축 필요?}
    Direct --> Store
    String --> Store
    Pickle --> Compress
    
    Compress -->|Yes| GZip[GZip 압축]
    Compress -->|No| Store[Redis 저장]
    GZip --> Store
```

## CachedRetriever 통합

```mermaid
classDiagram
    class CachedRetriever~T~ {
        -retriever: Retriever~T~
        -cache: RedisCache
        -ttl: int
        -cache_enabled: bool
        +retrieve(query: str, **kwargs) AsyncIterator[Dict]
        -_get_from_cache(key: str) Optional[List[Dict]]
        -_save_to_cache(key: str, results: List[Dict]) None
        -_should_cache(query: str) bool
    }
    
    class CacheStrategy {
        <<interface>>
        +should_cache(query: str, results: List) bool
        +get_ttl(query: str) int
        +get_key(query: str, params: Dict) str
    }
    
    class DefaultStrategy {
        +min_results: int = 1
        +max_query_length: int = 1000
        +excluded_patterns: List[str]
    }
    
    CachedRetriever --> RedisCache
    CachedRetriever --> CacheStrategy
    CacheStrategy <|-- DefaultStrategy
```

### 캐싱 플로우

```mermaid
sequenceDiagram
    participant Client
    participant CachedRetriever
    participant Cache
    participant Retriever
    
    Client->>CachedRetriever: retrieve(query)
    CachedRetriever->>CachedRetriever: generate_key(query)
    CachedRetriever->>Cache: get(key)
    
    alt 캐시 히트
        Cache-->>CachedRetriever: cached_results
        CachedRetriever-->>Client: yield results
    else 캐시 미스
        CachedRetriever->>Retriever: retrieve(query)
        Retriever-->>CachedRetriever: results
        CachedRetriever->>CachedRetriever: should_cache?
        opt 캐싱 가능
            CachedRetriever->>Cache: set(key, results, ttl)
        end
        CachedRetriever-->>Client: yield results
    end
```

## 성능 최적화

### 1. 연결 풀링

```python
# Redis 연결 풀 설정
connection_pool = redis.ConnectionPool(
    host=config.host,
    port=config.port,
    db=config.db,
    password=config.password,
    max_connections=config.max_connections,
    socket_keepalive=True,
    socket_keepalive_options={
        1: 1,  # TCP_KEEPIDLE
        2: 1,  # TCP_KEEPINTVL
        3: 3,  # TCP_KEEPCNT
    }
)
```

### 2. 파이프라이닝

```python
# 여러 작업을 파이프라인으로 처리
async def batch_get(keys: List[str]) -> List[Optional[Any]]:
    pipe = redis_client.pipeline()
    for key in keys:
        pipe.get(key)
    results = await pipe.execute()
    return [deserialize(r) if r else None for r in results]
```

### 3. 메모리 관리

```mermaid
graph TD
    subgraph "메모리 정책"
        maxmemory[최대 메모리<br/>4GB]
        policy[제거 정책<br/>allkeys-lru]
    end
    
    subgraph "모니터링"
        used[사용 메모리]
        hit_rate[히트율]
        evictions[제거 수]
    end
    
    maxmemory --> monitor[모니터링]
    policy --> monitor
    monitor --> used
    monitor --> hit_rate
    monitor --> evictions
```

## 캐시 통계

### 수집 메트릭

```python
class CacheStats:
    hits: int = 0          # 캐시 히트 수
    misses: int = 0        # 캐시 미스 수
    sets: int = 0          # 저장 작업 수
    deletes: int = 0       # 삭제 작업 수
    errors: int = 0        # 에러 수
    
    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0
```

### 통계 리포트

```json
{
    "cache_stats": {
        "hit_rate": 0.85,
        "total_hits": 12500,
        "total_misses": 2200,
        "total_sets": 2180,
        "total_deletes": 150,
        "total_errors": 5,
        "avg_get_time_ms": 1.2,
        "avg_set_time_ms": 2.5,
        "memory_usage_mb": 125.4,
        "key_count": 3450
    }
}
```

## 에러 처리

### 에러 유형

```mermaid
graph TD
    Error[캐시 에러]
    Error --> Connection[연결 에러]
    Error --> Timeout[타임아웃]
    Error --> Memory[메모리 부족]
    Error --> Serialization[직렬화 에러]
    
    Connection --> Retry[재시도]
    Timeout --> Skip[캐시 건너뛰기]
    Memory --> Evict[오래된 키 제거]
    Serialization --> Log[로그 & 건너뛰기]
```

### 에러 복구 전략

```python
async def get_with_fallback(key: str) -> Optional[Any]:
    try:
        # 캐시 조회 시도
        return await cache.get(key)
    except redis.ConnectionError:
        # 연결 에러 시 재연결 시도
        await cache.reconnect()
        return None
    except redis.TimeoutError:
        # 타임아웃 시 None 반환
        logger.warning(f"Cache timeout for key: {key}")
        return None
    except Exception as e:
        # 기타 에러는 로그만
        logger.error(f"Cache error: {e}")
        return None
```

## 환경 변수 설정

```bash
# Redis 연결
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your-password

# 캐시 설정
CACHE_DEFAULT_TTL=300
CACHE_KEY_PREFIX=mcp
CACHE_MAX_CONNECTIONS=50
CACHE_SOCKET_TIMEOUT=5
CACHE_RETRY_ON_TIMEOUT=true

# 성능 튜닝
CACHE_COMPRESSION_THRESHOLD=1024  # bytes
CACHE_ENABLE_PIPELINE=true
CACHE_PIPELINE_SIZE=100
```

## 모범 사례

### 1. 캐시 키 설계
- 의미 있는 네임스페이스 사용
- 버전 정보 포함
- 쿼리 파라미터 정규화

### 2. TTL 설정
- 데이터 특성에 따른 적절한 TTL
- 비즈니스 요구사항 고려
- 캐시 스탬피드 방지

### 3. 모니터링
- 히트율 추적
- 응답 시간 모니터링
- 메모리 사용량 관찰

### 4. 에러 처리
- 캐시 장애 시 서비스 지속
- 적절한 폴백 메커니즘
- 에러 로깅 및 알림