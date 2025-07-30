# 전체 아키텍처 구성도

```mermaid
flowchart LR
 subgraph serverGroup["MCP Server Spec 구현(fastmcp)<br>도구 집합 Server"]
    direction TB
        server["MCP Server"]
        rdb[("RDB")]
        vdb[("VDB")]
        web[("Web Search")]
  end
    server --- rdb & vdb & web
    client("MCP Client") -- Request<br>(Token1) --> gateway("MCP Gateway<br><br>1) 인증/인가<br>2) 적절한 MCP 도구 리스트 제공")
    gateway -- Response --> client
    gateway -- Request<br>(Token2) --> serverGroup
    serverGroup -- Response --> gateway

    style serverGroup fill:#FFD600
```

## 1. MCP Gateway(Authentication/Authorization)

### FastAPI 기반 인증 서버

- JWT 토큰 기반 인증/인가
- MCP 도구 권한 관리
- Rate Limiting & Request Validation

주요 컴포넌트

- Authentication Service (JWT)
- Authorization Service (RBAC)
- MCP Tool Registry
- Request Router

## 2. MCP Server (FastMCP Library Implementation)

### FastMCP 라이브러리 기반 MCP 서버

- 다중 Retriever 도구 통합
- 비동기 처리
- 상태 관리

도구별 서비스:

- RDB Tool Service

 > tool list, search-query
 > MUST **Elicitation**: create, delete, update

- VDB Tool Service  

 > tool list, search-query
 > MUST **Elicitation**: create, delete, update

- Web Search Tool Service

 > tool list, search-query

## 데이터 아키텍처

### PostgreSQL 데이터베이스 스키마

```sql
-- 사용자 데이터
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- MCP 토큰 관리
CREATE TABLE mcp_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 도구 사용 권한
CREATE TABLE user_tool_permissions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    tool_name VARCHAR(100) NOT NULL,
    is_allowed BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 검색 히스토리 및 로그
CREATE TABLE search_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    tool_used VARCHAR(100) NOT NULL,
    query TEXT NOT NULL,
    response_size INTEGER,
    execution_time_ms INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 문서 메타데이터 (벡터DB와 연결)
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    title VARCHAR(500),
    content_type VARCHAR(100),
    file_path TEXT,
    vector_id VARCHAR(255), -- Qdrant의 point ID
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### Qdrant 벡터DB 스키마

1. Collection 구성

collection_config = {
    "vectors": {
        "size": 1536,  # OpenAI ada-002 embedding size
        "distance": "Cosine"
    },
    "payload_schema": {
        "user_id": "integer",
        "document_id": "integer",
        "title": "text",
        "content": "text",
        "metadata": {
            "source": "text",
            "created_at": "datetime",
            "tags": ["text"]
        }
    }
}

2. 인덱스 전략

- user_id 필드에 인덱스 생성 (사용자별 격리)
- 계층적 네비게이션을 위한 HNSW 인덱스
- 필터링을 위한 payload 인덱스

## 상세한 컴포넌트 아키텍처

```mermaid
flowchart TB
    subgraph "MCP Gateway (Port: 8000)"
        direction TB
        auth["Authentication Service<br/>JWT 토큰 발급/검증"]
        authz["Authorization Service<br/>도구별 권한 검사"]
        router["Request Router<br/>적절한 MCP 서버로 라우팅"]
        registry["Tool Registry<br/>사용 가능한 도구 목록 관리"]
    end

    subgraph "MCP Server (Port: 8001)"
        direction TB
        mcpCore["FastMCP Core<br/>MCP 프로토콜 구현"]
        
        subgraph "Tool Services"
            rdbTool["RDB Tool<br/>SQL 쿼리 실행"]
            vdbTool["VDB Tool<br/>벡터 검색 수행"]
            webTool["Web Search Tool<br/>Tavily API 호출"]
        end
        
        subgraph "Data Access Layer"
            pgPool["PostgreSQL<br/>Connection Pool"]
            qdrantClient["Qdrant Client<br/>Vector Operations"]
            tavilyClient["Tavily Client<br/>Web Search API"]
        end
    end
    
    subgraph "Data Layer"
        postgres[("PostgreSQL<br/>Port: 5432<br/>- 사용자 데이터<br/>- 권한 관리<br/>- 검색 로그<br/>- 문서 메타데이터")]
        qdrant[("Qdrant<br/>Port: 6333<br/>- 벡터 임베딩<br/>- 유사도 검색<br/>- 사용자별 컬렉션")]
        tavily[("Tavily API<br/>- 웹 검색<br/>- 실시간 정보")]
    end
    
    client["MCP Client<br/>(Claude, VS Code, etc.)"] --> auth
    auth --> authz
    authz --> router
    router --> registry
    router --> mcpCore
    
    mcpCore --> rdbTool
    mcpCore --> vdbTool
    mcpCore --> webTool
    
    rdbTool --> pgPool
    vdbTool --> qdrantClient
    webTool --> tavilyClient
    
    pgPool --> postgres
    qdrantClient --> qdrant
    tavilyClient --> tavily
```
