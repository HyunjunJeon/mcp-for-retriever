# MCP for Retriever

웹 검색, 벡터 데이터베이스, 관계형 데이터베이스를 포함한 여러 리트리버 서비스를 통합하는 통합 MCP(Model Context Protocol) 서버입니다.

## 주요 기능

### 🔍 검색 기능

- **웹 검색**: Tavily를 통한 웹 콘텐츠 검색 통합
- **벡터 검색**: 의미론적 검색 기능을 갖춘 Qdrant 벡터 데이터베이스
- **데이터베이스 검색**: SQL 및 텍스트 검색을 지원하는 PostgreSQL 통합
- **동시 검색**: 모든 소스에서 동시에 검색 실행

### 🛡️ 보안 및 인증

- **JWT 인증**: 역할 기반 권한 제어를 통한 보안 액세스 제어
- **FastMCP Bearer Token**: FastMCP의 내장 인증 및 미들웨어 활용
- **서버 간 인증**: 안전한 내부 API 키 인증
- **사용자 관리**: 등록, 로그인, 검색, 관리자 기능

### 🚀 성능 및 확장성

- **비동기 우선**: 고성능을 위한 asyncio 기반 구현
- **Redis 캐싱**: 구성 가능한 TTL을 통한 성능 최적화
- **타입 안전성**: Python 3.12+ 기능을 활용한 완전한 타입 체킹
- **Docker 지원**: Docker Compose를 통한 완전한 컨테이너화

### 📊 모니터링 및 관찰성

- **OpenTelemetry**: 분산 추적 및 메트릭 수집
- **Sentry 통합**: 에러 추적 및 성능 모니터링
- **Prometheus 메트릭**: 시스템 모니터링을 위한 메트릭 엔드포인트
- **요청 추적**: 디버깅을 위한 고유 요청 ID 및 로그 상관관계

## 🆕 통합 서버 (New!)

### 개요

모든 서버 파일이 하나의 통합 서버로 리팩토링되었습니다! 이제 프로파일 기반 설정으로 필요한 기능만 활성화할 수 있습니다.

### 프로파일 사용

```bash
# 기본 서버 (최소 기능)
MCP_PROFILE=BASIC python -m src.server_unified

# 인증 서버
MCP_PROFILE=AUTH python -m src.server_unified

# 컨텍스트 추적 서버
MCP_PROFILE=CONTEXT python -m src.server_unified

# 캐싱 서버
MCP_PROFILE=CACHED python -m src.server_unified

# 완전 통합 서버 (모든 기능)
MCP_PROFILE=COMPLETE python -m src.server_unified
```

### 커스텀 설정

```bash
# 개별 기능 활성화/비활성화
MCP_PROFILE=CUSTOM \
  MCP_ENABLE_AUTH=true \
  MCP_ENABLE_CACHE=true \
  MCP_ENABLE_RATE_LIMIT=false \
  python -m src.server_unified
```

### 마이그레이션

기존 서버 파일에서 마이그레이션하는 경우 [마이그레이션 가이드](docs/migration-guide.md)를 참조하세요.

## 🚀 빠른 시작

### 🐳 Docker Compose (권장)

#### 1. 환경 설정

```bash
# 저장소 클론
git clone <repository-url>
cd make-mcp-server-vibe

# 환경 변수 설정
cp .env.example .env
# .env를 편집하여 TAVILY_API_KEY와 MCP_INTERNAL_API_KEY 추가
# 보안 키 생성: openssl rand -hex 32
```

#### 2. Docker Compose 실행

```bash
# 모든 서비스 시작
docker-compose up -d

# 이미지 재빌드가 필요한 경우
docker-compose build --no-cache
docker-compose up -d

# 로그 실시간 확인
docker-compose logs -f
```

#### 3. 서비스 상태 확인

```bash
# 모든 컨테이너 상태 확인
docker ps

# 헬스 체크 상태
curl http://localhost:8000/health  # Auth Gateway
curl http://localhost:8001/health  # MCP Server (내부에서만 접근 가능)
```

#### 3. 서비스 테스트

```bash
# 모든 서비스 상태 확인
./scripts/test-services.sh

# 통합 테스트 실행
./scripts/run-integration-tests.sh

# 인증 플로우 테스트
./scripts/test-auth-integration.sh

# Phase 2 기능 테스트
./scripts/test-phase2.sh
```

#### 4. 로그 확인

```bash
# 모든 서비스 로그
./scripts/logs-docker.sh

# 특정 서비스 로그
./scripts/logs-docker.sh auth-gateway
./scripts/logs-docker.sh mcp-server

# 실시간 로그 추적
./scripts/logs-docker.sh -f
./scripts/logs-docker.sh mcp-server -f

# 마지막 50줄만 보기
./scripts/logs-docker.sh -n 50
```

#### 5. 서비스 종료

```bash
# 컨테이너만 종료
./scripts/stop-docker.sh

# 볼륨도 함께 삭제 (데이터 초기화)
./scripts/stop-docker.sh --volumes
```

### 🏃 로컬 개발

#### 필수 조건

- Python 3.12 이상
- 종속성 관리를 위한 `uv`
- Docker (선택 사항, 데이터베이스용)

#### 설치

```bash
# 종속성 설치
uv sync

# 필수 환경 변수 설정
export TAVILY_API_KEY=your-tavily-api-key
export JWT_SECRET_KEY=your-secret-key-change-in-production
export MCP_INTERNAL_API_KEY=your-internal-api-key-change-in-production
export MCP_TRANSPORT=http
```

#### 서버 실행

```bash
# 옵션 1: 빠른 시작 스크립트 사용 (권장)
./scripts/quick-start.sh

# 옵션 2: 통합 서버 직접 실행
./scripts/run-unified-server.sh --profile COMPLETE --transport http

# 옵션 3: 수동 실행
# 터미널 1: 인증 게이트웨이 실행
uv run python -m src.auth.server

# 터미널 2: 통합 MCP 서버 실행 (HTTP 모드)
MCP_PROFILE=COMPLETE MCP_TRANSPORT=http uv run python -m src.server_unified

# 옵션 4: 로컬 테스트 스크립트 사용 (모든 서비스 자동 실행)
./scripts/test-local.sh

# 인증 통합 테스트
./scripts/test-auth-integration.sh
```

## 📋 서비스 구성

| 서비스 | 포트 | 설명 |
|--------|------|------|
| PostgreSQL | 5432 | 관계형 데이터베이스 |
| Qdrant | 6333, 6334 | 벡터 데이터베이스 |
| Redis | 6379 | 캐시 스토어 |
| Auth Gateway | 8000 | 인증/인가 API |
| MCP Server | 8001 | MCP 도구 서버 |

## MCP 클라이언트 설정 (mcp.json)

### Claude Desktop에서 사용하기

Claude Desktop에서 MCP 서버에 연결하려면 `mcp.json` 파일을 다음과 같이 설정하세요:

```json
{
  "mcpServers": {
    "mcp-retriever": {
      "url": "http://localhost:8001/",
      "transport": "http",
      "auth": {
        "type": "bearer",
        "token": "YOUR_JWT_TOKEN_HERE"
      },
      "description": "MCP Server for Web Search, Vector DB, and Database Queries"
    }
  }
}
```

> **참고**: 이제 클라이언트는 Auth Gateway(8000)를 거치지 않고 MCP Server(8001)에 직접 연결합니다.

### 인증 플로우

#### 1. 사용자 등록

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "your@email.com", "password": "YourPassword123!"}'
```

**응답 예시**:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "your@email.com",
  "created_at": "2025-07-31T10:00:00Z"
}
```

#### 2. 로그인 및 토큰 획듍

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "your@email.com", "password": "YourPassword123!"}'
```

**응답 예시**:

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

#### 3. 토큰으로 인증된 요청 보내기

```bash
# 사용자 정보 조회
curl -X GET http://localhost:8000/auth/me \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

# MCP 요청 프록시
curl -X POST http://localhost:8000/mcp/proxy \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/list",
    "id": 1
  }'
```

#### 4. 토큰 갱신

액세스 토큰이 만료되면 (30분) 리프레시 토큰으로 갱신:

```bash
curl -X POST http://localhost:8000/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "YOUR_REFRESH_TOKEN"}'
```

#### 5. mcp.json 업데이트

획듍한 액세스 토큰을 `mcp.json`의 `token` 필드에 입력:

```json
{
  "mcpServers": {
    "mcp-retriever": {
      "url": "http://localhost:8000/mcp/proxy",
      "transport": "sse",
      "auth": {
        "type": "bearer",
        "token": "YOUR_ACCESS_TOKEN_HERE"  // 여기에 토큰 입력
      }
    }
  }
}
```

### Auth Gateway API 엔드포인트

| 엔드포인트 | 메소드 | 설명 | 인증 필요 |
|-----------|--------|------|----------|
| `/auth/register` | POST | 새 사용자 등록 | ❌ |
| `/auth/login` | POST | 로그인 및 토큰 발급 | ❌ |
| `/auth/refresh` | POST | 토큰 갱신 | ❌ |
| `/auth/me` | GET | 현재 사용자 정보 | ✅ |
| `/mcp/proxy` | POST | MCP 요청 프록시 | ✅ |
| `/api/v1/users/search` | GET | 사용자 검색 | ✅ |
| `/api/v1/users/{user_id}` | GET | 특정 사용자 조회 | ✅ |
| `/health` | GET | 서비스 상태 확인 | ❌ |
| `/docs` | GET | Swagger API 문서 | ❌ |

### 대체 설정 (개발용)

개발 환경에서 빠른 테스트를 위해 MCP 서버에 직접 연결:

```json
{
  "mcpServers": {
    "mcp-retriever-direct": {
      "url": "http://localhost:8001/mcp/",
      "transport": "sse",
      "auth": {
        "type": "bearer",
        "token": "YOUR_MCP_INTERNAL_API_KEY"
      },
      "description": "Direct MCP Server Connection (Dev Only)"
    }
  }
}
```

⚠️ **주의**: 직접 연결은 개발 환경에서만 사용하세요. 프로덕션에서는 항상 Auth Gateway를 통해 접속하세요.

## 사용 가능한 도구

1. **search_web**: Tavily를 사용한 웹 검색
   - 매개변수: query, limit, include_domains, exclude_domains
   - 반환: 제목, URL, 내용, 점수가 포함된 웹 검색 결과

2. **search_vectors**: Qdrant를 사용한 벡터 데이터베이스 검색
   - 매개변수: query, collection, limit, score_threshold
   - 반환: 점수 및 메타데이터가 포함된 유사한 문서

3. **search_database**: PostgreSQL 데이터베이스 검색
   - 매개변수: query (SQL 또는 텍스트), table, limit
   - 반환: 쿼리와 일치하는 데이터베이스 레코드

4. **search_all**: 모든 소스에서 동시에 검색
   - 매개변수: query, limit
   - 반환: 모든 리트리버의 결합된 결과

5. **health_check**: 모든 리트리버의 상태 확인
   - 반환: 서비스 상태 및 리트리버 연결성

## 개발

### 테스트 실행

```bash
# 모든 테스트 실행
uv run pytest

# 커버리지와 함께 실행
uv run pytest --cov=src --cov-report=html

# 특정 테스트 파일 실행
uv run pytest tests/unit/test_server.py

# 미들웨어 테스트 실행
uv run pytest tests/unit/test_middleware/

# 관찰성 통합 테스트 실행
uv run pytest tests/integration/test_observability_integration.py

# 전체 시스템 시나리오 테스트 실행
uv run pytest tests/integration/test_full_system_scenarios.py

# Docker 관찰성 테스트 실행 (Docker 필요)
uv run pytest tests/integration/test_docker_observability.py -m docker
```

### 코드 품질

```bash
# 타입 체킹
uv run ty check src/

# 린팅 및 포맷팅
uv run ruff check src/
uv run ruff format src/
```

## 아키텍처

### 시스템 개요

MCP Server for Retriever는 다양한 데이터 소스(Web Search, Vector DB, RDB)를 통합하여 MCP(Model Context Protocol)를 통해 제공하는 마이크로서비스 아키텍처 시스템입니다.

### 아키텍처 다이어그램

```mermaid
graph TB
    subgraph "Client Layer"
        Client[MCP Client<br/>Claude/LLM]
    end

    subgraph "Auth Service"
        AuthGateway[Auth Gateway<br/>:8000<br/>JWT Issuer & User Management]
    end

    subgraph "MCP Service"
        MCPServer[MCP Server<br/>:8001<br/>FastMCP v2.10.6<br/>with JWT Validation]
    end

    subgraph "Data Layer"
        subgraph "Cache"
            Redis[(Redis<br/>:6379<br/>Session & Cache)]
        end
        
        subgraph "Databases"
            PostgreSQL[(PostgreSQL<br/>:5432<br/>Users & Permissions)]
            Qdrant[(Qdrant<br/>:6333/6334<br/>Vector Store)]
        end
    end

    subgraph "External Services"
        Tavily[Tavily API<br/>Web Search]
    end

    %% Client flows (새로운 아키텍처)
    Client -->|1. Login| AuthGateway
    AuthGateway -->|2. JWT Token| Client
    Client -->|3. Direct Request<br/>with JWT| MCPServer
    
    %% Auth Gateway connections (인증 서비스만)
    AuthGateway <-->|User/Permission Data| PostgreSQL
    AuthGateway <-->|Session| Redis
    
    %% MCP Server connections
    MCPServer -->|JWT Validation| MCPServer
    MCPServer <-->|Query| PostgreSQL
    MCPServer <-->|Vector Search| Qdrant
    MCPServer <-->|Cache| Redis
    MCPServer -->|Web Search| Tavily
    
    %% Network
    Client -.->|Docker Network<br/>172.20.0.0/16| AuthGateway
    Client -.->|Docker Network<br/>172.20.0.0/16| MCPServer
    MCPServer -.->|Internal| Redis
    MCPServer -.->|Internal| PostgreSQL
    MCPServer -.->|Internal| Qdrant
```

### 컴포넌트 상세

#### 1. Auth Gateway (Port 8000)

- **Technology**: FastAPI + Uvicorn + FastHTML
- **Primary Role**: 인증 서비스 및 사용자 관리
- **Features**:
  - JWT 토큰 발급 (로그인 시)
  - 사용자 등록 및 관리
  - 권한 관리 CRUD API
  - 웹 기반 관리자 인터페이스
  - 역할 기반 접근 제어 (RBAC) 설정
  - API: `/auth/login`, `/auth/register`, `/auth/refresh`
  - Admin UI: `/admin`, `/admin/users`, `/admin/permissions`

#### 2. MCP Server (Port 8001)

- **Technology**: FastMCP v2.10.6
- **Transport**: Streamable HTTP
- **Authentication**: JWT Bearer Token (직접 검증)
- **Features**:
  - JWT 미들웨어를 통한 토큰 검증
  - 권한 기반 도구 접근 제어
  - 통합 검색 도구 제공
  - 컨텍스트 추적
  - 캐싱 지원
  - 구조화된 로깅

#### 3. PostgreSQL (Port 5432)

- **Version**: 17-alpine
- **Database**: mcp_retriever
- **Functions**:
  - 사용자 인증 정보
  - 콘텐츠 저장소
  - 전문 검색 지원

#### 4. Qdrant (Port 6333/6334)

- **Version**: latest
- **Functions**:
  - 벡터 임베딩 저장
  - 시맨틱 검색
  - gRPC 인터페이스 (6334)

#### 5. Redis (Port 6379)

- **Version**: latest
- **Functions**:
  - 세션 관리
  - 검색 결과 캐싱
  - 분산 잠금

자세한 설계 정보는 [아키텍처 문서](/reference_docs/architecture.md)를 참조하세요.

## Docker Compose 구성

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

## 프로젝트 상태

### ✅ Phase 1 - 핵심 기능 및 인증 (완료)

- 비동기 지원을 포함한 기본 리트리버 인터페이스
- 모든 리트리버 구현:
  - 재시도 로직을 포함한 Tavily 웹 검색 리트리버
  - 컬렉션 관리를 포함한 Qdrant 벡터 데이터베이스 리트리버
  - SQL 및 텍스트 검색을 포함한 PostgreSQL 데이터베이스 리트리버
- 의존성 주입을 위한 리트리버 팩토리
- Context 지원과 개선된 오류 처리를 포함한 FastMCP 서버
- 모든 검색 도구 (웹, 벡터, 데이터베이스, 전체)
- RBAC를 포함한 JWT 인증 게이트웨이
- FastMCP bearer token 인증 통합
- 내부 API 키를 사용한 서버 간 인증
- 사용자 관리 기능 (검색, 조회, 관리자 엔드포인트)
- TTL 구성을 포함한 Redis 캐싱 레이어
- 헬스 체크를 포함한 Docker Compose 설정
- 포괄적인 테스트 커버리지:
  - 단위 테스트: 190개 이상의 테스트 통과
  - FastMCP 클라이언트를 사용한 통합 테스트
  - Docker 환경 테스트
  - 인증 흐름 통합 테스트

### ✅ Phase 2 - 고급 기능 (완료)

- 향상된 컨텍스트 기반 사용자 정보 전파
- 고급 미들웨어 구현:
  - JWT 검증을 포함한 인증 미들웨어
  - 민감한 데이터 수정을 포함한 요청/응답 로깅
  - Rate limiting (분당 60개, 시간당 1000개 요청)
  - 요청 검증 및 권한 확인
  - 성능 메트릭 수집
  - 포괄적인 오류 처리
- 더 나은 오류 관리를 위한 사용자 정의 예외 계층 구조
- 고유 ID를 사용한 요청 추적
- 도구 사용 통계 및 모니터링
- 동시 요청 처리 최적화
- 모든 미들웨어 컴포넌트에 대한 단위 테스트
- OpenTelemetry 통합:
  - W3C Trace Context를 사용한 분산 추적
  - FastAPI, HTTPX, AsyncPG, Redis를 위한 자동 계측
  - MCP 작업을 위한 사용자 정의 메트릭
  - Prometheus 메트릭 내보내기 엔드포인트
  - Jaeger/Tempo를 위한 OTLP 내보내기 지원
- Sentry 통합:
  - 오류 추적 및 성능 모니터링
  - 사용자 컨텍스트 전파
  - 민감한 데이터 삭제
  - 트랜잭션 수준 성능 추적
- 관찰성 미들웨어:
  - 통합 추적 및 오류 캡처
  - 컨텍스트를 위한 Baggage 전파
  - 요청 수준 추적 상관관계

### 🚧 Phase 3 - 프로덕션 준비 (예정)

- [ ] API 버전 관리 지원
- [ ] 모니터링을 위한 관리자 대시보드
- [ ] 자동 백업 및 복구
- [ ] 다중 지역 배포 지원
- [ ] 분산 캐시를 통한 수평적 확장
- [ ] 외부 서비스를 위한 서킷 브레이커 패턴

## API 예제

### MCP 도구 사용 (Auth Gateway 경유)

```bash
# 먼저 액세스 토큰 획득
TOKEN=$(curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "Test123!"}' | jq -r .access_token)

# auth gateway를 통해 사용 가능한 도구 나열
curl -X POST http://localhost:8000/mcp/proxy \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}'

# auth gateway를 통한 웹 검색
curl -X POST http://localhost:8000/mcp/proxy \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "search_web",
      "arguments": {"query": "FastMCP documentation"}
    },
    "id": 2
  }'
```

### MCP 서버 직접 액세스 (내부 사용 전용)

다른 서비스에서 MCP 서버에 직접 액세스할 때는 내부 API 키를 사용합니다:

```bash
# 내부 API 키를 사용한 직접 액세스
curl -X POST http://localhost:8001/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MCP_INTERNAL_API_KEY" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}'
```

## 관찰성

### OpenTelemetry 설정

시스템은 OpenTelemetry를 통한 포괄적인 관찰성을 포함합니다:

```bash
# 추적 내보내기를 위한 OTLP 엔드포인트 구성
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# OpenTelemetry 활성화로 실행
uv run python -m src.server_unified
```

기능:

- FastAPI, HTTPX, AsyncPG, Redis를 위한 자동 계측
- MCP 작업을 위한 사용자 정의 메트릭
- W3C Trace Context 전파
- `/metrics`의 Prometheus 메트릭 엔드포인트

### Sentry 구성

오류 추적 및 성능 모니터링을 위해:

```bash
# Sentry DSN 설정
export SENTRY_DSN=https://xxx@xxx.ingest.sentry.io/xxx
export ENVIRONMENT=production
export RELEASE_VERSION=1.0.0

# Sentry가 자동으로 캡처:
# - 처리되지 않은 예외
# - 성능 트랜잭션
# - JWT 토큰의 사용자 컨텍스트
```

### 모니터링 엔드포인트

- `/health` - 서비스 헬스 체크
- `/metrics` - Prometheus 메트릭 (OpenTelemetry가 활성화된 경우)

### 추적 컨텍스트 전파

시스템은 HTTP 헤더를 통해 추적 컨텍스트를 전파합니다:

```bash
# 추적 컨텍스트 예제
curl -X POST http://localhost:8001/ \
  -H "traceparent: 00-0123456789abcdef0123456789abcdef-0123456789abcdef-01" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}'
```

## 보안

### 인증 아키텍처

시스템은 분리된 인증 아키텍처를 구현합니다:

1. **Auth Gateway (포트 8000)**:
   - JWT 토큰 발급 및 관리
   - 사용자 등록 및 인증
   - 역할 및 권한 관리 (RBAC)
   - 웹 기반 관리자 인터페이스
   - 권한 관리 CRUD API

2. **MCP 서버 (포트 8001)**:
   - JWT Bearer Token 직접 검증
   - 미들웨어를 통한 토큰 검증
   - 도구별 권한 확인
   - 사용자 컨텍스트 유지

### 보안 모범 사례

- 프로덕션에서는 항상 HTTPS 사용
- 강력한 무작위 키 생성: `openssl rand -hex 32`
- JWT 시크릿 및 API 키를 정기적으로 교체
- 프로덕션에서 rate limiting 활성화
- 인증 실패 모니터링

### 환경 변수

```bash
# 프로덕션 필수
JWT_SECRET_KEY=<strong-random-key>
MCP_INTERNAL_API_KEY=<strong-random-key>
TAVILY_API_KEY=<your-tavily-api-key>

# 데이터베이스 연결
POSTGRES_DSN=postgresql://user:pass@localhost:5432/dbname
QDRANT_HOST=localhost
QDRANT_PORT=6333
REDIS_HOST=localhost
REDIS_PORT=6379

# 관찰성 (선택 사항)
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317  # OpenTelemetry collector
SENTRY_DSN=https://xxx@xxx.ingest.sentry.io/xxx    # Sentry error tracking
ENVIRONMENT=production                               # 환경 이름
RELEASE_VERSION=1.0.0                               # 릴리스 버전

# 성능 튜닝
RATE_LIMIT_REQUESTS_PER_MINUTE=60
RATE_LIMIT_BURST_SIZE=10
CACHE_TTL_SECONDS=300
```

## 📜 주요 스크립트

### 빠른 시작 및 실행

- `./scripts/quick-start.sh` - 대화형 서버 실행 도구 (프로파일, 전송 모드 선택)
- `./scripts/run-unified-server.sh` - 통합 서버 실행 (옵션: --profile, --transport, --port)
- `./scripts/test-local.sh` - Docker 없이 로컬에서 전체 시스템 실행

### Docker 관련

- `./scripts/start-docker.sh` - Docker Compose로 모든 서비스 시작
- `./scripts/stop-docker.sh` - 서비스 중지 (--volumes로 데이터 초기화)
- `./scripts/logs-docker.sh` - 서비스 로그 확인 (-f로 실시간 추적)

### 테스트 및 상태 확인

- `./scripts/test-services.sh` - 모든 서비스 헬스체크
- `./scripts/run-integration-tests.sh` - Docker 환경에서 통합 테스트 실행
- `./scripts/test-auth-integration.sh` - 인증 플로우 테스트
- `./scripts/test-phase2.sh` - Phase 2 기능 테스트

## 🐳 Docker 명령어

```bash
# 컨테이너 상태 확인
docker-compose ps

# 특정 컨테이너 접속
docker exec -it mcp-postgres psql -U mcp_user -d mcp_retriever
docker exec -it mcp-redis redis-cli
docker exec -it mcp-auth-gateway /bin/sh
docker exec -it mcp-server /bin/sh

# 이미지 재빌드
docker-compose build

# 전체 시스템 재시작
docker-compose restart

# 로그 확인
docker logs mcp-server --tail 50
docker logs mcp-auth-gateway --tail 50
```

## 🔍 문제 해결

### 포트 충돌

이미 사용 중인 포트가 있다면 `docker-compose.yml`에서 포트 매핑을 변경하세요:

```yaml
services:
  postgres:
    ports:
      - "15432:5432"  # 호스트 포트를 15432로 변경
```

### Docker 빌드 캐시 문제

빌드 캐시로 인해 변경사항이 반영되지 않을 때:

```bash
# 빌드 캐시 완전 제거
docker builder prune -af

# 캐시 없이 재빌드
docker-compose build --no-cache
docker-compose up -d
```

### 권한 문제

스크립트 실행 권한이 없다면:

```bash
chmod +x scripts/*.sh
```

### 서비스 연결 실패

서비스가 시작되는 데 시간이 걸릴 수 있습니다. 다음 명령으로 상태를 확인하세요:

```bash
# 헬스체크 상태 확인
docker-compose -f docker-compose.local.yml ps

# 서비스별 로그 확인
./scripts/logs-docker.sh [서비스명]
```

## 🚀 배포 현황

### ✅ 성공적으로 배포된 서비스

1. **PostgreSQL**: Healthy, 스키마 초기화 완료
2. **Qdrant**: Running, 벡터 작업 준비 완료
3. **Redis**: Healthy, 연결 수락 중
4. **Auth Gateway**: Healthy, JWT 인증 운영 중
5. **MCP Server**: Healthy, 모든 도구 사용 가능

### 🔧 사용된 구성

- **Profile**: DEV (개발 모드)
- **Transport**: HTTP (Streamable)
- **Rate Limiting**: 개발용으로 비활성화
- **Caching**: Redis로 활성화
- **Authentication**: 내부 API 키와 함께 JWT

### 📊 리소스 할당

- **Network**: Bridge 네트워크 (172.20.0.0/16)
- **Volumes**: 모든 데이터베이스의 영구 저장소
- **Health Checks**: 모든 서비스에 구성됨
- **Restart Policy**: unless-stopped

## API 플로우

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

    %% Direct MCP Tool Call (새로운 플로우)
    C->>MS: POST /<br/>Authorization: Bearer {token}
    MS->>MS: Validate JWT locally
    MS->>MS: Check permissions
    
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
    MS-->>C: Tool response
```

## 문서

- [완성된 아키텍처](completed_architecture.md) - 현재 배포된 시스템의 전체 아키텍처
- [아키텍처](/reference_docs/architecture.md) - 시스템 설계 및 구성 요소
- [보안 및 성능](/reference_docs/security_performance_monitoring.md) - 프로덕션 고려 사항
- [API 레퍼런스](http://localhost:8000/docs) - 대화형 API 문서 (실행 중일 때)
- [보안 분석](/docs/security-analysis.md) - 보안 취약점 및 완화 방법

### 📚 프로젝트 구조 문서

프로젝트의 구조와 각 모듈의 역할에 대한 자세한 문서는 다음을 참조하세요:

- [프로젝트 구조 개요](/docs/structure/README.md) - 전체 프로젝트 구조 및 아키텍처
- [src 폴더 구조](/docs/structure/src.md) - 소스 코드 구조 및 모듈 설명
- [auth 모듈](/docs/structure/auth.md) - 인증/인가 시스템 구조
- [retrievers 모듈](/docs/structure/retrievers.md) - 리트리버 구현체 구조
- [middleware 모듈](/docs/structure/middleware.md) - 미들웨어 스택 구조
- [observability 모듈](/docs/structure/observability.md) - 관찰성 구현 구조
- [cache 모듈](/docs/structure/cache.md) - 캐싱 시스템 구조
- [tests 구조](/docs/structure/tests.md) - 테스트 구조 및 전략

각 문서는 Mermaid 다이어그램을 포함하여 시각적으로 구조를 이해할 수 있도록 도와줍니다.

## 참고 자료

- [FastMCP 문서](https://gofastmcp.com)
- [MCP 프로토콜 사양](https://modelcontextprotocol.io)
- [Tavily Search API](https://docs.tavily.com)
- [Qdrant 벡터 데이터베이스](https://qdrant.tech/documentation/concepts/)
- [PostgreSQL 문서](https://www.postgresql.org/docs/)

## 기여하기

1. TDD 접근 방식 따르기 - 먼저 테스트 작성
2. 모든 테스트가 통과하는지 확인
3. 타입 체킹 및 린팅 실행
4. 필요에 따라 문서 업데이트

## 라이선스

MIT
