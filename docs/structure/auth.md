# Auth 모듈 구조

인증/인가 시스템은 JWT 기반 사용자 인증과 RBAC(역할 기반 접근 제어)를 제공합니다.

## 모듈 구조

```mermaid
graph TD
    auth[auth/]
    auth --> models[models.py<br/>데이터 모델]
    auth --> database[database.py<br/>DB 스키마]
    auth --> server[server.py<br/>FastAPI 서버]
    auth --> services[services/<br/>비즈니스 로직]
    auth --> repositories[repositories/<br/>데이터 접근]
    auth --> dependencies[dependencies.py<br/>의존성 주입]
    
    services --> auth_service[auth_service.py<br/>인증 로직]
    services --> jwt_service[jwt_service.py<br/>JWT 관리]
    services --> rbac_service[rbac_service.py<br/>권한 관리]
    services --> permission_service[permission_service.py<br/>세밀한 권한]
    
    repositories --> user_repo[user_repository.py<br/>사용자 저장소]
```

## 주요 컴포넌트

### 1. models.py - 데이터 모델

```mermaid
classDiagram
    class UserRole {
        <<enumeration>>
        USER
        ADMIN
        SERVICE
    }
    
    class User {
        +id: str
        +email: str
        +password_hash: str
        +role: UserRole
        +created_at: datetime
        +updated_at: datetime
        +is_active: bool
    }
    
    class TokenData {
        +sub: str
        +email: str
        +role: str
        +exp: datetime
    }
    
    class LoginRequest {
        +email: str
        +password: str
    }
    
    class RegisterRequest {
        +email: str
        +password: str
        +role: UserRole
    }
    
    class TokenResponse {
        +access_token: str
        +refresh_token: str
        +token_type: str
        +expires_in: int
    }
```

### 2. database.py - 데이터베이스 스키마

SQLAlchemy 기반 데이터베이스 스키마:

- **users 테이블**: 사용자 정보 저장
- **refresh_tokens 테이블**: 리프레시 토큰 관리
- **audit_logs 테이블**: 인증 이벤트 로깅

### 3. server.py - FastAPI 서버

```mermaid
graph LR
    subgraph "API Endpoints"
        register[POST /auth/register]
        login[POST /auth/login]
        refresh[POST /auth/refresh]
        logout[POST /auth/logout]
        me[GET /auth/me]
        users[GET /api/v1/users]
        proxy[POST /mcp/proxy]
    end
    
    subgraph "Services"
        auth_svc[AuthService]
        user_svc[UserService]
        mcp_svc[MCPProxy]
    end
    
    register --> auth_svc
    login --> auth_svc
    refresh --> auth_svc
    logout --> auth_svc
    me --> user_svc
    users --> user_svc
    proxy --> mcp_svc
```

### 4. services/ - 비즈니스 로직

#### auth_service.py
- **사용자 등록**: 이메일 중복 확인, 비밀번호 해싱
- **로그인**: 자격 증명 확인, 토큰 발급
- **토큰 갱신**: 리프레시 토큰으로 새 액세스 토큰 발급
- **로그아웃**: 리프레시 토큰 무효화

#### jwt_service.py
- **토큰 생성**: 액세스/리프레시 토큰 생성
- **토큰 검증**: 서명 및 만료 시간 확인
- **토큰 디코딩**: 페이로드 추출

#### rbac_service.py
- **권한 확인**: 사용자 역할별 접근 권한 관리
- **리소스 접근 제어**: MCP 도구별 권한 설정

#### mcp_proxy.py
- **요청 프록시**: Auth Gateway에서 MCP 서버로 요청 전달
- **컨텍스트 주입**: 사용자 정보를 요청에 추가
- **응답 필터링**: 권한에 따른 응답 필터링

### 5. repositories/ - 데이터 접근 계층

#### user_repository.py
- **CRUD 작업**: 사용자 생성, 조회, 수정, 삭제
- **쿼리 메서드**: 이메일로 조회, 역할별 조회
- **트랜잭션 관리**: 데이터베이스 트랜잭션 처리

## 인증 플로우

```mermaid
sequenceDiagram
    participant Client
    participant AuthGateway
    participant AuthService
    participant JWTService
    participant Database
    participant MCPServer
    
    %% 로그인 플로우
    Client->>AuthGateway: POST /auth/login
    AuthGateway->>AuthService: authenticate(email, password)
    AuthService->>Database: get_user_by_email()
    Database-->>AuthService: User
    AuthService->>AuthService: verify_password()
    AuthService->>JWTService: create_tokens()
    JWTService-->>AuthService: access_token, refresh_token
    AuthService->>Database: save_refresh_token()
    AuthService-->>AuthGateway: TokenResponse
    AuthGateway-->>Client: 200 OK + tokens
    
    %% API 요청 플로우
    Client->>AuthGateway: POST /mcp/proxy + Bearer token
    AuthGateway->>JWTService: decode_token()
    JWTService-->>AuthGateway: TokenData
    AuthGateway->>AuthGateway: check_permissions()
    AuthGateway->>MCPServer: Forward request + user context
    MCPServer-->>AuthGateway: Response
    AuthGateway-->>Client: Response
```

## 보안 고려사항

### 1. 비밀번호 보안
- bcrypt를 사용한 비밀번호 해싱
- 솔트 자동 생성
- 적절한 작업 팩터 설정

### 2. JWT 보안
- RS256 또는 HS256 알고리즘 사용
- 짧은 액세스 토큰 만료 시간 (30분)
- 긴 리프레시 토큰 만료 시간 (7일)
- 토큰 블랙리스트 구현

### 3. RBAC 정책

```mermaid
graph TD
    subgraph "역할별 권한"
        USER[USER<br/>- search_web<br/>- search_vectors<br/>- search_database]
        ADMIN[ADMIN<br/>- 모든 USER 권한<br/>- health_check<br/>- user_management]
        SERVICE[SERVICE<br/>- 모든 도구<br/>- 내부 API 전용]
    end
```

## 환경 변수

```bash
# JWT 설정
JWT_SECRET_KEY=your-secret-key
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# 데이터베이스
AUTH_DATABASE_URL=postgresql://user:pass@localhost/auth

# MCP 서버
MCP_SERVER_URL=http://localhost:8001
MCP_INTERNAL_API_KEY=internal-api-key

# 보안
BCRYPT_ROUNDS=12
ALLOWED_ORIGINS=http://localhost:3000,https://app.example.com
```

## 에러 처리

인증 관련 에러 코드:

- `401 Unauthorized`: 인증 실패
- `403 Forbidden`: 권한 부족
- `409 Conflict`: 이메일 중복
- `422 Unprocessable Entity`: 유효성 검사 실패

## 확장 포인트

### 1. OAuth2 통합
- Google, GitHub 등 소셜 로그인 추가

### 2. 2FA (Two-Factor Authentication)
- TOTP 기반 2차 인증

### 3. API 키 관리
- 장기 실행 서비스를 위한 API 키

### 4. 감사 로깅
- 모든 인증 이벤트 기록