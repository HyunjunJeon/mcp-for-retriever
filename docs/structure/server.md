# Server 파일 구조

MCP 서버 구현은 점진적으로 기능이 추가된 여러 버전으로 구성되어 있습니다.

## 서버 파일 개요

```mermaid
graph TD
    servers[서버 구현들]
    servers --> server[server.py<br/>기본 구현]
    servers --> server_cache[server_with_cache.py<br/>캐싱 추가]
    servers --> server_improved[server_improved.py<br/>개선된 버전]
    servers --> server_auth[server_auth.py<br/>인증 통합]
    
    server --> basic[기본 기능]
    server_cache --> cache_layer[캐시 레이어]
    server_improved --> context[컨텍스트 관리]
    server_auth --> full[전체 통합]
```

## 1. server.py - 기본 MCP 서버

### 구조

```mermaid
classDiagram
    class BasicMCPServer {
        +mcp: FastMCP
        +retrievers: Dict[str, Retriever]
        +create_mcp_server() FastMCP
        +search_web(query, limit, include_domains, exclude_domains)
        +search_vectors(query, collection, limit, score_threshold)
        +search_database(query, table, limit)
        +search_all(query, limit)
        +health_check()
    }
    
    class FastMCP {
        +name: str
        +version: str
        +tool(name, description)
        +run()
    }
    
    BasicMCPServer --> FastMCP
    BasicMCPServer --> Retriever
```

### 주요 기능

- FastMCP 서버 초기화
- 기본 도구 엔드포인트 정의
- 리트리버 직접 연결
- 동기/비동기 변환 처리

### 도구 정의

```python
@mcp.tool(
    name="search_web",
    description="웹에서 정보 검색"
)
async def search_web(
    query: str,
    limit: int = 10,
    include_domains: list[str] = [],
    exclude_domains: list[str] = []
) -> list[dict[str, Any]]:
    """Tavily를 사용한 웹 검색"""
```

## 2. server_with_cache.py - 캐싱이 추가된 서버

### 구조

```mermaid
graph LR
    subgraph "캐싱 레이어"
        request[요청] --> cache_check{캐시 확인}
        cache_check -->|히트| cached_response[캐시된 응답]
        cache_check -->|미스| retriever[리트리버 호출]
        retriever --> cache_save[캐시 저장]
        cache_save --> response[응답]
    end
```

### 추가된 기능

```mermaid
classDiagram
    class CachedMCPServer {
        +cache: RedisCache
        +cached_retrievers: Dict[str, CachedRetriever]
        -_setup_cached_retrievers()
        -_get_cache_config() CacheConfig
    }
    
    class CachedRetriever {
        -retriever: Retriever
        -cache: RedisCache
        -ttl: int
    }
    
    CachedMCPServer --> RedisCache
    CachedMCPServer --> CachedRetriever
    CachedRetriever --> Retriever
```

### 캐시 설정

- Redis 연결 초기화
- 리트리버별 TTL 설정
- 캐시 키 생성 전략

## 3. server_improved.py - 개선된 서버

### 구조

```mermaid
graph TD
    subgraph "개선 사항"
        context[컨텍스트 관리]
        error[에러 처리]
        logging[구조화된 로깅]
        metrics[메트릭 수집]
    end
    
    subgraph "새로운 기능"
        user_context[사용자 컨텍스트]
        request_tracking[요청 추적]
        retry_logic[재시도 로직]
    end
```

### 컨텍스트 관리

```python
class Context:
    """요청 컨텍스트"""
    request_id: str
    user_id: Optional[str]
    method: str
    timestamp: datetime
    metadata: Dict[str, Any]
```

### 에러 처리 개선

```mermaid
graph TD
    Error[에러 발생]
    Error --> Type{에러 타입}
    
    Type -->|RetrieverError| Specific[특정 에러 응답]
    Type -->|ValidationError| Validation[검증 에러 응답]
    Type -->|Exception| Generic[일반 에러 응답]
    
    Specific --> Format[JSON-RPC 포맷]
    Validation --> Format
    Generic --> Format
    
    Format --> Log[에러 로깅]
    Log --> Response[에러 응답]
```

## 4. server_auth.py - 인증이 통합된 서버

### 전체 아키텍처

```mermaid
graph TB
    subgraph "인증 레이어"
        bearer[Bearer Token]
        api_key[API Key]
    end
    
    subgraph "미들웨어 스택"
        observability[Observability]
        auth[Authentication]
        logging[Logging]
        validation[Validation]
        rate_limit[Rate Limiting]
        metrics[Metrics]
        error[Error Handling]
    end
    
    subgraph "핵심 기능"
        tools[도구 엔드포인트]
        context[컨텍스트 관리]
        cache[캐싱]
    end
    
    bearer --> auth
    api_key --> auth
    auth --> logging
    logging --> validation
    validation --> rate_limit
    rate_limit --> metrics
    metrics --> error
    error --> tools
    tools --> context
    tools --> cache
```

### FastMCP 인증 통합

```python
# FastMCP Bearer 토큰 인증
mcp = FastMCP(
    name="mcp-retriever",
    auth=BearerTokenAuth(
        get_token=lambda: os.getenv("MCP_INTERNAL_API_KEY")
    )
)
```

### 미들웨어 통합

```python
def create_app():
    # 미들웨어 스택 구성
    app = FastAPI()
    
    # 미들웨어 추가 (실행 순서의 역순)
    app.add_middleware(ObservabilityMiddleware)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(ValidationMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(ErrorHandlingMiddleware)
    
    return app
```

## 서버 실행 플로우

### 1. 초기화 단계

```mermaid
sequenceDiagram
    participant Main
    participant Config
    participant Retrievers
    participant Cache
    participant Server
    
    Main->>Config: 환경 변수 로드
    Config-->>Main: 설정 완료
    
    Main->>Retrievers: 리트리버 생성
    loop 각 리트리버
        Retrievers->>Retrievers: connect()
    end
    Retrievers-->>Main: 연결 완료
    
    Main->>Cache: Redis 연결
    Cache-->>Main: 캐시 준비
    
    Main->>Server: FastMCP 생성
    Server->>Server: 도구 등록
    Server->>Server: 미들웨어 설정
    Server-->>Main: 서버 준비 완료
    
    Main->>Server: run()
```

### 2. 요청 처리 플로우

```mermaid
sequenceDiagram
    participant Client
    participant Server
    participant Middleware
    participant Tool
    participant Retriever
    
    Client->>Server: JSON-RPC 요청
    Server->>Middleware: 미들웨어 체인 시작
    
    loop 각 미들웨어
        Middleware->>Middleware: 전처리
    end
    
    Middleware->>Tool: 도구 실행
    Tool->>Retriever: 데이터 검색
    Retriever-->>Tool: 검색 결과
    Tool-->>Middleware: 도구 응답
    
    loop 각 미들웨어 (역순)
        Middleware->>Middleware: 후처리
    end
    
    Middleware-->>Server: 최종 응답
    Server-->>Client: JSON-RPC 응답
```

## 설정 및 환경 변수

### 공통 설정

```bash
# MCP 서버
MCP_SERVER_NAME=mcp-retriever
MCP_SERVER_VERSION=1.0.0
MCP_TRANSPORT=stdio  # stdio | http

# 리트리버
TAVILY_API_KEY=your-key
POSTGRES_DSN=postgresql://...
QDRANT_HOST=localhost
```

### 서버별 추가 설정

#### server_with_cache.py
```bash
REDIS_HOST=localhost
REDIS_PORT=6379
CACHE_TTL_SECONDS=300
```

#### server_auth.py
```bash
MCP_INTERNAL_API_KEY=your-internal-key
JWT_SECRET_KEY=your-jwt-secret
RATE_LIMIT_REQUESTS_PER_MINUTE=60
```

## 서버 선택 가이드

### 사용 시나리오

```mermaid
graph TD
    Start[시작] --> Need{요구사항?}
    
    Need -->|기본 기능만| Basic[server.py]
    Need -->|성능 필요| Cache{캐싱 필요?}
    Need -->|프로덕션| Auth[server_auth.py]
    
    Cache -->|Yes| WithCache[server_with_cache.py]
    Cache -->|No| Improved[server_improved.py]
    
    Basic --> Dev[개발/테스트]
    WithCache --> Performance[성능 중시]
    Improved --> Features[기능 중시]
    Auth --> Production[프로덕션]
```

### 기능 비교

| 기능 | server.py | server_with_cache.py | server_improved.py | server_auth.py |
|------|-----------|---------------------|-------------------|----------------|
| 기본 도구 | ✅ | ✅ | ✅ | ✅ |
| Redis 캐싱 | ❌ | ✅ | ❌ | ✅ |
| 컨텍스트 관리 | ❌ | ❌ | ✅ | ✅ |
| 에러 처리 | 기본 | 기본 | 향상 | 완전 |
| 인증 | ❌ | ❌ | ❌ | ✅ |
| 미들웨어 | ❌ | ❌ | 부분 | ✅ |
| 관찰성 | ❌ | ❌ | 부분 | ✅ |

## 확장 포인트

### 1. 새로운 도구 추가

```python
@mcp.tool(
    name="my_new_tool",
    description="새로운 도구 설명"
)
async def my_new_tool(param1: str, param2: int = 10) -> dict:
    """도구 구현"""
    # 구현 내용
    return {"result": "success"}
```

### 2. 커스텀 미들웨어 추가

```python
class MyMiddleware:
    async def __call__(self, request, call_next):
        # 전처리
        response = await call_next(request)
        # 후처리
        return response
```

### 3. 리트리버 확장

```python
# 새로운 리트리버 추가
retrievers["my_retriever"] = MyRetriever(config)
```

## 성능 최적화

### 1. 비동기 처리
- 모든 I/O 작업을 비동기로 처리
- asyncio.gather()를 사용한 동시 실행

### 2. 연결 풀링
- 데이터베이스 연결 풀 사용
- HTTP 클라이언트 재사용

### 3. 캐싱 전략
- 적절한 TTL 설정
- 캐시 워밍
- 캐시 무효화 정책