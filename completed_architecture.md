# MCP Server Complete Architecture

## System Overview

MCP Server for Retriever는 다양한 데이터 소스(Web Search, Vector DB, RDB)를 통합하여 MCP(Model Context Protocol)를 통해 제공하는 마이크로서비스 아키텍처 시스템입니다.

## Architecture Diagram

```mermaid
graph TB
    subgraph "Client Layer"
        Client[MCP Client<br/>Claude/LLM]
    end

    subgraph "Gateway Layer"
        AuthGateway[Auth Gateway<br/>:8000<br/>JWT Auth & RBAC]
    end

    subgraph "Service Layer"
        MCPServer[MCP Server<br/>:8001<br/>FastMCP v2.10.6]
    end

    subgraph "Data Layer"
        subgraph "Cache"
            Redis[(Redis<br/>:6379<br/>Session & Cache)]
        end
        
        subgraph "Databases"
            PostgreSQL[(PostgreSQL<br/>:5432<br/>Users & Content)]
            Qdrant[(Qdrant<br/>:6333/6334<br/>Vector Store)]
        end
    end

    subgraph "External Services"
        Tavily[Tavily API<br/>Web Search]
    end

    %% Client connections
    Client -->|HTTP/SSE| AuthGateway
    
    %% Auth Gateway connections
    AuthGateway -->|Proxy MCP| MCPServer
    AuthGateway <-->|Auth Data| PostgreSQL
    AuthGateway <-->|Session| Redis
    
    %% MCP Server connections
    MCPServer <-->|Query| PostgreSQL
    MCPServer <-->|Vector Search| Qdrant
    MCPServer <-->|Cache| Redis
    MCPServer -->|Web Search| Tavily
    
    %% Network
    AuthGateway -.->|Docker Network<br/>172.20.0.0/16| MCPServer
    MCPServer -.->|Internal| Redis
    MCPServer -.->|Internal| PostgreSQL
    MCPServer -.->|Internal| Qdrant
```

## Component Details

### 1. Auth Gateway (Port 8000)
- **Technology**: FastAPI + Uvicorn
- **Features**:
  - JWT 기반 인증 (HS256)
  - 역할 기반 접근 제어 (RBAC)
  - MCP 요청 프록시
  - 사용자 관리 API
  - 상태 체크: `/health`

### 2. MCP Server (Port 8001)
- **Technology**: FastMCP v2.10.6
- **Transport**: Streamable HTTP
- **Features**:
  - 통합 검색 도구 제공
  - 컨텍스트 추적
  - 캐싱 지원
  - 구조화된 로깅

### 3. PostgreSQL (Port 5432)
- **Version**: 17-alpine
- **Database**: mcp_retriever
- **Functions**:
  - 사용자 인증 정보
  - 콘텐츠 저장소
  - 전문 검색 지원

### 4. Qdrant (Port 6333/6334)
- **Version**: latest
- **Functions**:
  - 벡터 임베딩 저장
  - 시맨틱 검색
  - gRPC 인터페이스 (6334)

### 5. Redis (Port 6379)
- **Version**: latest
- **Functions**:
  - 세션 관리
  - 검색 결과 캐싱
  - 분산 잠금

## Docker Compose Configuration

```yaml
services:
  postgres:
    image: postgres:17-alpine
    container_name: mcp-postgres
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U mcp_user -d mcp_retriever"]
    
  qdrant:
    image: qdrant/qdrant:latest
    container_name: mcp-qdrant
    ports:
      - "6333:6333"  # HTTP
      - "6334:6334"  # gRPC
    
  redis:
    image: redis:latest
    container_name: mcp-redis
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
    
  auth-gateway:
    build: ./docker/Dockerfile.auth
    container_name: mcp-auth-gateway
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    
  mcp-server:
    build: ./docker/Dockerfile.mcp
    container_name: mcp-server
    environment:
      MCP_PROFILE: DEV
      MCP_TRANSPORT: http
    depends_on:
      auth-gateway:
        condition: service_healthy

networks:
  mcp-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16
```

## API Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant AG as Auth Gateway
    participant MS as MCP Server
    participant R as Redis
    participant PG as PostgreSQL
    participant Q as Qdrant
    participant T as Tavily

    %% Authentication Flow
    C->>AG: POST /auth/login
    AG->>PG: Verify credentials
    PG-->>AG: User data
    AG->>R: Store session
    AG-->>C: JWT token

    %% MCP Tool Call Flow
    C->>AG: POST /mcp/<br/>Authorization: Bearer {token}
    AG->>AG: Validate JWT
    AG->>MS: Proxy MCP request
    
    alt search_web
        MS->>T: Search query
        T-->>MS: Web results
    else search_vectors
        MS->>Q: Vector query
        Q-->>MS: Similar documents
    else search_database
        MS->>PG: SQL query
        PG-->>MS: Query results
    else search_all
        MS->>T: Concurrent
        MS->>Q: searches
        MS->>PG: 
        T-->>MS: Combined
        Q-->>MS: results
        PG-->>MS: 
    end
    
    MS->>R: Cache results
    MS-->>AG: Tool response
    AG-->>C: MCP response
```

## MCP Tools Available

```mermaid
graph LR
    subgraph "MCP Tools"
        SW[search_web<br/>Tavily API]
        SV[search_vectors<br/>Qdrant]
        SD[search_database<br/>PostgreSQL]
        SA[search_all<br/>Combined]
        HC[health_check<br/>System Status]
    end
    
    subgraph "Parameters"
        SW --> |query, limit| SW1[Web Results]
        SV --> |query, collection, limit| SV1[Vector Results]
        SD --> |query, table, limit| SD1[DB Results]
        SA --> |query, limit| SA1[All Results]
        HC --> |none| HC1[Health Status]
    end
```

## Security Architecture

```mermaid
graph TB
    subgraph "Security Layers"
        JWT[JWT Authentication<br/>HS256 Algorithm]
        RBAC[Role-Based Access<br/>Control]
        API[Internal API Key<br/>Validation]
        HTTPS[HTTPS/TLS<br/>In Production]
    end
    
    subgraph "Security Flow"
        JWT --> RBAC
        RBAC --> API
        API --> HTTPS
    end
    
    subgraph "Token Lifecycle"
        Access[Access Token<br/>30 min]
        Refresh[Refresh Token<br/>7 days]
        Access -.->|Expires| Refresh
        Refresh -.->|Renew| Access
    end
```

## Deployment Status

### ✅ Successfully Deployed Services
1. **PostgreSQL**: Healthy, initialized with schema
2. **Qdrant**: Running, ready for vector operations
3. **Redis**: Healthy, accepting connections
4. **Auth Gateway**: Healthy, JWT auth operational
5. **MCP Server**: Healthy, all tools available

### 🔧 Configuration Used
- **Profile**: DEV (development mode)
- **Transport**: HTTP (Streamable)
- **Rate Limiting**: Disabled for development
- **Caching**: Enabled with Redis
- **Authentication**: JWT with internal API key

### 📊 Resource Allocation
- **Network**: Bridge network (172.20.0.0/16)
- **Volumes**: Persistent storage for all databases
- **Health Checks**: Configured for all services
- **Restart Policy**: unless-stopped

## Monitoring and Observability

```mermaid
graph LR
    subgraph "Logging"
        SL[Structured Logging<br/>JSON Format]
        RL[Request Logging<br/>with Request ID]
        EL[Error Logging<br/>with Traceback]
    end
    
    subgraph "Metrics"
        RT[Response Time]
        RR[Request Rate]
        ER[Error Rate]
        CH[Cache Hit Rate]
    end
    
    subgraph "Health Checks"
        HC1[/health endpoints]
        HC2[Docker healthcheck]
        HC3[Service dependencies]
    end
```

## Future Enhancements

1. **Production Ready**:
   - Enable HTTPS/TLS
   - Implement rate limiting
   - Add API Gateway (Kong/Traefik)

2. **Scalability**:
   - Kubernetes deployment
   - Horizontal pod autoscaling
   - Database read replicas

3. **Monitoring**:
   - Prometheus metrics
   - Grafana dashboards
   - ELK stack for logs

4. **Security**:
   - OAuth2/OIDC support
   - API key rotation
   - WAF integration