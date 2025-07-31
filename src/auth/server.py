"""
JWT 기반 인증 및 권한 관리 서버

이 모듈은 JWT 기반 사용자 인증과 권한 관리를 담당하는 FastAPI 서버를 구현합니다.
단순히 저장된 DB의 인증 정보를 관리하고, 자원에 대한 인가 정보를 관리하는
CRUD Admin Page와 API를 제공합니다.

주요 기능:
    사용자 인증:
        - JWT 기반 회원가입/로그인 시스템
        - 액세스 토큰과 리프레시 토큰 관리
        - 비밀번호 해싱과 안전한 저장
        - 계정 활성화 상태 관리
        
    권한 관리:
        - 역할 기반 접근 제어 (RBAC)
        - 도구별 세밀한 권한 설정
        - 관리자 전용 기능 분리
        - 사용자별 접근 로그 기록
        
    사용자 관리:
        - 사용자 검색 및 조회
        - 관리자용 사용자 목록 및 통계
        - 사용자 프로필 관리
        - 최근 가입자 조회
        
    권한 관리 CRUD API:
        - 자원에 대한 인가 정보 관리
        - Admin Page를 위한 API 제공

API 엔드포인트:
    인증 관련:
        - POST /auth/register: 회원가입
        - POST /auth/login: 로그인  
        - POST /auth/refresh: 토큰 갱신
        - GET /auth/me: 현재 사용자 정보 조회
        
    사용자 검색:
        - GET /api/v1/users/search: 사용자 검색
        - GET /api/v1/users/{user_id}: ID로 사용자 조회
        
    관리자 전용:
        - GET /api/v1/admin/users: 전체 사용자 목록
        - GET /api/v1/admin/users/stats: 사용자 통계

보안 특징:
    - JWT 토큰 기반 stateless 인증
    - bcrypt를 사용한 비밀번호 해싱
    - CORS 설정으로 도메인 제한
    - 요청별 구조화된 로깅
    - 예외 상황 안전 처리
    - 민감한 정보 응답에서 제외

아키텍처:
    - 의존성 주입으로 서비스 계층 분리
    - 싱글톤 패턴으로 서비스 인스턴스 관리
    - 계층화된 예외 처리
    - 구조화된 로깅으로 관찰 가능성 향상

환경 변수:
    - JWT_SECRET_KEY: JWT 서명용 비밀 키 (필수)
    - LOG_LEVEL: 로그 레벨 (DEBUG, INFO, WARNING, ERROR)

서버 실행:
    ```bash
    # 개발 모드 (자동 재로드)
    python -m src.auth.server
    
    # 또는 uvicorn으로 직접 실행
    uvicorn src.auth.server:app --host 0.0.0.0 --port 8000 --reload
    ```

작성일: 2024-01-30
"""

from contextlib import asynccontextmanager
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import FastAPI, Depends, HTTPException, status, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fasthtml.common import *
from fastcore.xml import to_xml
import structlog
import uvicorn

from .models import (
    UserCreate,
    UserLogin,
    UserResponse,
    AuthTokens,
    ResourcePermissionCreate,
    ResourcePermissionUpdate,
    ResourcePermissionResponse,
    RoleCreate,
    RoleUpdate,
    RoleResponse,
    ResourceType,
    ActionType,
)
from .services import (
    AuthService,
    AuthenticationError,
)
from .dependencies import (
    get_auth_service,
    get_current_user,
    get_current_active_user,
    require_admin,
    get_permission_service,
    get_rbac_service,
)
from .database import get_db
from .services.auth_service_sqlite import SQLiteAuthService
from .services.jwt_service import JWTService
from .repositories.sqlite_user_repository import SQLiteUserRepository


# SQLite 기반 AuthService 의존성
_sqlite_auth_service = None

def get_sqlite_auth_service() -> SQLiteAuthService:
    """SQLite 기반 AuthService 싱글톤"""
    global _sqlite_auth_service
    if _sqlite_auth_service is None:
        import os
        jwt_secret = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
        jwt_service = JWTService(secret_key=jwt_secret)
        _sqlite_auth_service = SQLiteAuthService(jwt_service)
    return _sqlite_auth_service


# 로거 설정
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 애플리케이션 수명주기 관리
    
    애플리케이션 시작과 종료 시 필요한 작업들을 처리합니다.
    데이터베이스 연결, 서비스 초기화, 리소스 정리 등을 담당합니다.
    
    시작 시 작업:
        - SQLite 데이터베이스 초기화
        - 테이블 생성 및 마이그레이션
        - 초기 관리자 계정 생성
        - 서버 시작 로그 기록
        
    종료 시 작업:
        - 데이터베이스 연결 종료
        - 리소스 해제
        - 종료 로그 기록
        
    Args:
        app (FastAPI): FastAPI 애플리케이션 인스턴스
        
    Yields:
        None: 애플리케이션 실행 중에는 제어권을 양보
    """
    # 시작 시
    logger.info("인증 게이트웨이 서버 시작", port=8000)
    
    # 데이터베이스 초기화
    from .database import init_db, engine, async_session_maker
    from .repositories.sqlite_user_repository import SQLiteUserRepository
    from .services.auth_service_sqlite import SQLiteAuthService
    from .services.jwt_service import JWTService
    from .models import UserCreate
    import os
    
    logger.info("데이터베이스 초기화 시작")
    await init_db()
    logger.info("데이터베이스 테이블 생성 완료")
    
    # 초기 관리자 계정 생성
    try:
        async with async_session_maker() as session:
            repository = SQLiteUserRepository(session)
            
            # 관리자 계정이 이미 있는지 확인
            admin_email = "admin@example.com"
            existing_admin = await repository.get_by_email(admin_email)
            
            if not existing_admin:
                # JWT 서비스 생성
                jwt_secret = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
                jwt_service = JWTService(secret_key=jwt_secret)
                
                # Auth 서비스 생성
                auth_service = SQLiteAuthService(jwt_service)
                
                # 관리자 계정 생성
                admin_data = UserCreate(
                    email=admin_email,
                    password="Admin123!",
                    username="admin",
                    roles=["admin", "user"]
                )
                
                await auth_service.register(admin_data, session)
                logger.info("초기 관리자 계정 생성 완료", email=admin_email)
            else:
                logger.info("관리자 계정이 이미 존재합니다", email=admin_email)
                
    except Exception as e:
        logger.error("초기 관리자 계정 생성 실패", error=str(e))
    
    yield
    
    # 종료 시
    await engine.dispose()
    logger.info("인증 게이트웨이 서버 종료")


# FastAPI 앱 생성
app = FastAPI(
    title="JWT Auth & Permission Management Server",
    description="JWT 기반 인증 및 권한 관리 서버 - 사용자 인증과 자원 권한 관리를 위한 CRUD API 제공",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 운영 환경에서는 특정 도메인만 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === 인증 엔드포인트 ===



@app.post("/auth/register", response_model=UserResponse)
async def register(
    user_create: UserCreate,
    auth_service: Annotated[SQLiteAuthService, Depends(get_sqlite_auth_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    새 사용자 계정 등록
    
    제공된 사용자 정보로 새로운 계정을 생성합니다.
    이메일 중복 검사, 비밀번호 해싱, 기본 역할 할당을 수행합니다.
    
    Args:
        user_create (UserCreate): 사용자 등록 정보
            - email: 이메일 주소 (고유해야 함)
            - password: 평문 비밀번호 (최소 8자, 복잡도 요구사항)
            - 기타 선택적 프로필 정보
        auth_service (AuthService): 인증 서비스 인스턴스
        
    Returns:
        UserResponse: 생성된 사용자 정보 (비밀번호 제외)
            - id, email, roles, is_active, created_at 등
            
    Raises:
        HTTPException 400: 등록 실패 시
            - 이메일 중복
            - 비밀번호 복잡도 미충족
            - 필수 필드 누락
            
    보안 특징:
        - 비밀번호 bcrypt 해싱
        - 이메일 정규화 및 중복 검사
        - 기본 'user' 역할 자동 할당
        - 등록 시도 로깅
    """
    try:
        user = await auth_service.register(user_create, db)
        logger.info("사용자 등록 성공", email=user.email)
        return user
    except AuthenticationError as e:
        logger.warning("사용자 등록 실패", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/auth/login", response_model=AuthTokens)
async def login(
    user_login: UserLogin,
    auth_service: Annotated[SQLiteAuthService, Depends(get_sqlite_auth_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
    response: Response,
):
    """
    사용자 로그인 및 JWT 토큰 발급
    
    이메일과 비밀번호를 검증하여 액세스 토큰과 리프레시 토큰을 발급합니다.
    성공 시 사용자가 MCP 서버의 기능에 접근할 수 있는 인증 토큰을 제공합니다.
    
    Args:
        user_login (UserLogin): 로그인 정보
            - email: 등록된 이메일 주소
            - password: 평문 비밀번호
        auth_service (AuthService): 인증 서비스 인스턴스
        
    Returns:
        AuthTokens: JWT 토큰 쌍
            - access_token: API 요청용 단기 토큰 (30분 유효)
            - refresh_token: 토큰 갱신용 장기 토큰 (7일 유효) 
            - token_type: "Bearer"
            - expires_in: 액세스 토큰 만료 시간(초)
            
    Raises:
        HTTPException 401: 로그인 실패 시
            - 잘못된 이메일 또는 비밀번호
            - 계정 비활성화 상태
            - 계정 잠금 상태
            
    보안 특징:
        - bcrypt 비밀번호 검증
        - JWT 토큰 서명 및 만료 시간 설정
        - 로그인 시도 로깅 (성공/실패)
        - 민감한 정보 응답에서 제외
        - WWW-Authenticate 헤더 포함
    """
    try:
        tokens = await auth_service.login(user_login, db)
        logger.info("로그인 성공", email=user_login.email)
        
        # JWT 토큰을 쿠키에도 저장 (웹 UI용)
        response.set_cookie(
            key="access_token",
            value=tokens.access_token,
            httponly=True,  # JavaScript에서 접근 불가 (XSS 방지)
            secure=False,   # HTTPS가 아닌 환경에서도 동작 (개발용)
            samesite="lax", # CSRF 방지
            max_age=tokens.expires_in,  # 토큰 만료 시간과 동일
        )
        
        return tokens
    except AuthenticationError as e:
        logger.warning("로그인 실패", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.post("/auth/refresh", response_model=AuthTokens)
async def refresh_tokens(
    refresh_token: str,
    auth_service: Annotated[SQLiteAuthService, Depends(get_sqlite_auth_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """토큰 갱신"""
    try:
        tokens = await auth_service.refresh_tokens(refresh_token)
        logger.info("토큰 갱신 성공")
        return tokens
    except AuthenticationError as e:
        logger.warning("토큰 갱신 실패", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.get("/auth/me", response_model=UserResponse)
async def get_me(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
):
    """현재 사용자 정보 조회"""
    return current_user


# === HTML UI 페이지 엔드포인트 (E2E 테스트용) ===

@app.get("/auth/register-page", response_class=HTMLResponse)
async def register_page():
    """회원가입 페이지 (E2E 테스트용)"""
    html_content = """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>MCP 회원가입</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 500px; margin: 50px auto; padding: 20px; }
            .form-group { margin-bottom: 15px; }
            label { display: block; margin-bottom: 5px; font-weight: bold; }
            input { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
            button { background-color: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; }
            button:hover { background-color: #0056b3; }
            .error { color: red; margin-top: 10px; }
            .success { color: green; margin-top: 10px; }
        </style>
    </head>
    <body>
        <h1>MCP 회원가입</h1>
        <form id="registerForm">
            <div class="form-group">
                <label for="email">이메일:</label>
                <input type="email" id="email" name="email" required>
            </div>
            <div class="form-group">
                <label for="password">비밀번호:</label>
                <input type="password" id="password" name="password" required minlength="6">
            </div>
            <button type="submit">회원가입</button>
        </form>
        <div id="message"></div>
        <p>이미 계정이 있으신가요? <a href="/auth/login-page">로그인</a></p>
        
        <script>
            document.getElementById('registerForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const messageDiv = document.getElementById('message');
                
                const formData = {
                    email: document.getElementById('email').value,
                    password: document.getElementById('password').value
                };
                
                try {
                    const response = await fetch('/auth/register', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(formData)
                    });
                    
                    const data = await response.json();
                    
                    if (response.ok) {
                        messageDiv.innerHTML = '<p class="success">회원가입 성공! <a href="/auth/login-page">로그인 페이지</a>로 이동하세요.</p>';
                        document.getElementById('registerForm').reset();
                    } else {
                        const errorMessage = data.detail || data.message || JSON.stringify(data);
                        messageDiv.innerHTML = `<p class="error">오류: ${errorMessage}</p>`;
                    }
                } catch (error) {
                    messageDiv.innerHTML = '<p class="error">네트워크 오류가 발생했습니다.</p>';
                }
            });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.get("/auth/login-page", response_class=HTMLResponse)
async def login_page():
    """로그인 페이지 (E2E 테스트용)"""
    html_content = """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>MCP 로그인</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 500px; margin: 50px auto; padding: 20px; }
            .form-group { margin-bottom: 15px; }
            label { display: block; margin-bottom: 5px; font-weight: bold; }
            input { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
            button { background-color: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; }
            button:hover { background-color: #0056b3; }
            .error { color: red; margin-top: 10px; }
            .success { color: green; margin-top: 10px; }
            .token-info { background-color: #f8f9fa; padding: 15px; border-radius: 4px; margin-top: 20px; word-break: break-all; }
        </style>
    </head>
    <body>
        <h1>MCP 로그인</h1>
        <form id="loginForm">
            <div class="form-group">
                <label for="email">이메일:</label>
                <input type="email" id="email" name="email" required>
            </div>
            <div class="form-group">
                <label for="password">비밀번호:</label>
                <input type="password" id="password" name="password" required>
            </div>
            <button type="submit">로그인</button>
        </form>
        <div id="message"></div>
        <div id="tokenInfo" style="display: none;">
            <h3>인증 토큰 정보</h3>
            <div class="token-info">
                <strong>Access Token:</strong>
                <p id="accessToken"></p>
                <strong>Refresh Token:</strong>
                <p id="refreshToken"></p>
            </div>
            <button onclick="testAuthMe()">현재 사용자 정보 조회</button>
        </div>
        <p>계정이 없으신가요? <a href="/auth/register-page">회원가입</a></p>
        
        <script>
            let currentAccessToken = null;
            
            document.getElementById('loginForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const messageDiv = document.getElementById('message');
                const tokenInfoDiv = document.getElementById('tokenInfo');
                
                const formData = {
                    email: document.getElementById('email').value,
                    password: document.getElementById('password').value
                };
                
                try {
                    const response = await fetch('/auth/login', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(formData)
                    });
                    
                    const data = await response.json();
                    
                    if (response.ok) {
                        messageDiv.innerHTML = '<p class="success">로그인 성공!</p>';
                        document.getElementById('loginForm').reset();
                        
                        // 토큰 정보 표시
                        currentAccessToken = data.access_token;
                        document.getElementById('accessToken').textContent = data.access_token;
                        document.getElementById('refreshToken').textContent = data.refresh_token;
                        tokenInfoDiv.style.display = 'block';
                        
                        // 로컬 스토리지에 토큰 저장 (E2E 테스트용)
                        localStorage.setItem('access_token', data.access_token);
                        localStorage.setItem('refresh_token', data.refresh_token);
                        
                        // 로그인 성공 후 admin 페이지로 리다이렉트
                        messageDiv.innerHTML = '<p class="success">로그인 성공! 잠시 후 관리자 페이지로 이동합니다...</p>';
                        setTimeout(() => {
                            window.location.href = '/admin';
                        }, 1500);
                    } else {
                        const errorMessage = data.detail || data.message || JSON.stringify(data);
                        messageDiv.innerHTML = `<p class="error">오류: ${errorMessage}</p>`;
                        tokenInfoDiv.style.display = 'none';
                    }
                } catch (error) {
                    messageDiv.innerHTML = '<p class="error">네트워크 오류가 발생했습니다.</p>';
                    tokenInfoDiv.style.display = 'none';
                }
            });
            
            async function testAuthMe() {
                const messageDiv = document.getElementById('message');
                
                if (!currentAccessToken) {
                    messageDiv.innerHTML = '<p class="error">먼저 로그인하세요.</p>';
                    return;
                }
                
                try {
                    const response = await fetch('/auth/me', {
                        headers: { 'Authorization': `Bearer ${currentAccessToken}` }
                    });
                    
                    if (response.ok) {
                        const userData = await response.json();
                        messageDiv.innerHTML = `<p class="success">사용자 정보: ${JSON.stringify(userData, null, 2)}</p>`;
                    } else {
                        messageDiv.innerHTML = '<p class="error">인증 실패: 토큰이 유효하지 않습니다.</p>';
                    }
                } catch (error) {
                    messageDiv.innerHTML = '<p class="error">네트워크 오류가 발생했습니다.</p>';
                }
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)




# === 권한 관리 API (Admin Page용) ===

@app.get("/api/v1/permissions/resources", response_model=list[ResourcePermissionResponse])
async def list_resource_permissions(
    current_user: Annotated[UserResponse, Depends(require_admin)],
    permission_service: Annotated["PermissionService", Depends(get_permission_service)],
    resource_type: Optional[ResourceType] = None,
    resource_name: Optional[str] = None,
    user_id: Optional[int] = None,
    role_name: Optional[str] = None,
    skip: int = 0,
    limit: int = 50
):
    """리소스 권한 목록 조회 (관리자 전용)"""
    if not permission_service.db_conn:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="데이터베이스 연결이 필요합니다"
        )
    
    # 쿼리 조건 구성
    conditions = []
    params = []
    
    if resource_type:
        conditions.append(f"resource_type = ${len(params) + 1}")
        params.append(resource_type.value)
    
    if resource_name:
        conditions.append(f"resource_name ILIKE ${len(params) + 1}")
        params.append(f"%{resource_name}%")
    
    if user_id:
        conditions.append(f"user_id = ${len(params) + 1}")
        params.append(user_id)
    
    if role_name:
        conditions.append(f"role_name = ${len(params) + 1}")
        params.append(role_name)
    
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    
    query = f"""
        SELECT id, user_id, role_name, resource_type, resource_name, 
               actions, conditions, granted_at, granted_by, expires_at
        FROM resource_permissions
        {where_clause}
        ORDER BY granted_at DESC
        LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
    """
    params.extend([limit, skip])
    
    try:
        rows = await permission_service.db_conn.fetch(query, *params)
        
        permissions = []
        for row in rows:
            perm = ResourcePermissionResponse(
                id=row["id"],
                user_id=row["user_id"],
                role_name=row["role_name"],
                resource_type=ResourceType(row["resource_type"]),
                resource_name=row["resource_name"],
                actions=[ActionType(a) for a in row["actions"]],
                conditions=row["conditions"],
                granted_at=row["granted_at"],
                granted_by=row["granted_by"],
                expires_at=row["expires_at"]
            )
            permissions.append(perm)
        
        return permissions
        
    except Exception as e:
        logger.error("권한 목록 조회 실패", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="권한 목록 조회에 실패했습니다"
        )


@app.post("/api/v1/permissions/resources", response_model=ResourcePermissionResponse)
async def create_resource_permission(
    permission_data: ResourcePermissionCreate,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    permission_service: Annotated["PermissionService", Depends(get_permission_service)],
):
    """리소스 권한 생성 (관리자 전용)"""
    if not permission_service.db_conn:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="데이터베이스 연결이 필요합니다"
        )
    
    # user_id와 role_name 중 하나는 필수
    if not permission_data.user_id and not permission_data.role_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_id 또는 role_name 중 하나는 필수입니다"
        )
    
    try:
        await permission_service.grant_permission(
            user_id=permission_data.user_id,
            role_name=permission_data.role_name,
            resource_type=permission_data.resource_type,
            resource_name=permission_data.resource_name,
            actions=permission_data.actions,
            granted_by=current_user.id
        )
        
        # 생성된 권한 조회하여 반환
        query = """
            SELECT id, user_id, role_name, resource_type, resource_name, 
                   actions, conditions, granted_at, granted_by, expires_at
            FROM resource_permissions
            WHERE resource_type = $1 AND resource_name = $2
              AND (user_id = $3 OR role_name = $4)
            ORDER BY granted_at DESC
            LIMIT 1
        """
        
        row = await permission_service.db_conn.fetchrow(
            query,
            permission_data.resource_type.value,
            permission_data.resource_name,
            permission_data.user_id,
            permission_data.role_name
        )
        
        if not row:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="권한 생성 후 조회에 실패했습니다"
            )
        
        return ResourcePermissionResponse(
            id=row["id"],
            user_id=row["user_id"],
            role_name=row["role_name"],
            resource_type=ResourceType(row["resource_type"]),
            resource_name=row["resource_name"],
            actions=[ActionType(a) for a in row["actions"]],
            conditions=row["conditions"],
            granted_at=row["granted_at"],
            granted_by=row["granted_by"],
            expires_at=row["expires_at"]
        )
        
    except Exception as e:
        logger.error("권한 생성 실패", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"권한 생성에 실패했습니다: {str(e)}"
        )


@app.put("/api/v1/permissions/resources/{permission_id}", response_model=ResourcePermissionResponse)
async def update_resource_permission(
    permission_id: int,
    permission_data: ResourcePermissionUpdate,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    permission_service: Annotated["PermissionService", Depends(get_permission_service)],
):
    """리소스 권한 수정 (관리자 전용)"""
    if not permission_service.db_conn:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="데이터베이스 연결이 필요합니다"
        )
    
    try:
        # 기존 권한 확인
        existing_query = """
            SELECT id, user_id, role_name, resource_type, resource_name, 
                   actions, conditions, granted_at, granted_by, expires_at
            FROM resource_permissions
            WHERE id = $1
        """
        
        existing_row = await permission_service.db_conn.fetchrow(existing_query, permission_id)
        if not existing_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="권한을 찾을 수 없습니다"
            )
        
        # 업데이트할 필드들 구성
        update_fields = []
        params = []
        
        if permission_data.actions is not None:
            update_fields.append(f"actions = ${len(params) + 1}")
            params.append([a.value for a in permission_data.actions])
        
        if permission_data.conditions is not None:
            update_fields.append(f"conditions = ${len(params) + 1}")
            params.append(permission_data.conditions)
        
        if permission_data.expires_at is not None:
            update_fields.append(f"expires_at = ${len(params) + 1}")
            params.append(permission_data.expires_at)
        
        update_fields.append(f"granted_by = ${len(params) + 1}")
        params.append(current_user.id)
        
        update_fields.append(f"granted_at = ${len(params) + 1}")
        params.append("NOW()")
        
        if not update_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="업데이트할 필드가 없습니다"
            )
        
        # 업데이트 쿼리 실행
        update_query = f"""
            UPDATE resource_permissions
            SET {', '.join(update_fields)}
            WHERE id = ${len(params) + 1}
            RETURNING id, user_id, role_name, resource_type, resource_name, 
                      actions, conditions, granted_at, granted_by, expires_at
        """
        params.append(permission_id)
        
        updated_row = await permission_service.db_conn.fetchrow(update_query, *params)
        
        # 캐시 클리어
        if existing_row["user_id"]:
            permission_service.clear_cache(existing_row["user_id"])
        
        return ResourcePermissionResponse(
            id=updated_row["id"],
            user_id=updated_row["user_id"],
            role_name=updated_row["role_name"],
            resource_type=ResourceType(updated_row["resource_type"]),
            resource_name=updated_row["resource_name"],
            actions=[ActionType(a) for a in updated_row["actions"]],
            conditions=updated_row["conditions"],
            granted_at=updated_row["granted_at"],
            granted_by=updated_row["granted_by"],
            expires_at=updated_row["expires_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("권한 수정 실패", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"권한 수정에 실패했습니다: {str(e)}"
        )


@app.delete("/api/v1/permissions/resources/{permission_id}")
async def delete_resource_permission(
    permission_id: int,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    permission_service: Annotated["PermissionService", Depends(get_permission_service)],
):
    """리소스 권한 삭제 (관리자 전용)"""
    if not permission_service.db_conn:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="데이터베이스 연결이 필요합니다"
        )
    
    try:
        # 기존 권한 확인 및 사용자 ID 가져오기
        check_query = """
            SELECT user_id, role_name, resource_type, resource_name
            FROM resource_permissions
            WHERE id = $1
        """
        
        existing_row = await permission_service.db_conn.fetchrow(check_query, permission_id)
        if not existing_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="권한을 찾을 수 없습니다"
            )
        
        # 권한 삭제
        delete_query = "DELETE FROM resource_permissions WHERE id = $1"
        await permission_service.db_conn.execute(delete_query, permission_id)
        
        # 캐시 클리어
        if existing_row["user_id"]:
            permission_service.clear_cache(existing_row["user_id"])
        
        logger.info(
            "권한 삭제 완료",
            permission_id=permission_id,
            admin_id=current_user.id,
            user_id=existing_row["user_id"],
            role_name=existing_row["role_name"]
        )
        
        return {"message": "권한이 성공적으로 삭제되었습니다"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("권한 삭제 실패", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"권한 삭제에 실패했습니다: {str(e)}"
        )


# === 사용자별 권한 관리 API ===

@app.get("/api/v1/users/{user_id}/permissions", response_model=list[ResourcePermissionResponse])
async def get_user_permissions(
    user_id: int,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    permission_service: Annotated["PermissionService", Depends(get_permission_service)],
):
    """사용자의 리소스 권한 조회 (관리자 전용)"""
    if not permission_service.db_conn:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="데이터베이스 연결이 필요합니다"
        )
    
    try:
        # 사용자 존재 확인
        auth_service = get_auth_service()
        user = await auth_service.get_user_by_id(str(user_id))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="사용자를 찾을 수 없습니다"
            )
        
        query = """
            SELECT id, user_id, role_name, resource_type, resource_name, 
                   actions, conditions, granted_at, granted_by, expires_at
            FROM resource_permissions
            WHERE user_id = $1
            ORDER BY granted_at DESC
        """
        
        rows = await permission_service.db_conn.fetch(query, user_id)
        
        permissions = []
        for row in rows:
            perm = ResourcePermissionResponse(
                id=row["id"],
                user_id=row["user_id"],
                role_name=row["role_name"],
                resource_type=ResourceType(row["resource_type"]),
                resource_name=row["resource_name"],
                actions=[ActionType(a) for a in row["actions"]],
                conditions=row["conditions"],
                granted_at=row["granted_at"],
                granted_by=row["granted_by"],
                expires_at=row["expires_at"]
            )
            permissions.append(perm)
        
        return permissions
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("사용자 권한 조회 실패", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="사용자 권한 조회에 실패했습니다"
        )


@app.post("/api/v1/users/{user_id}/permissions", response_model=ResourcePermissionResponse)
async def grant_user_permission(
    user_id: int,
    permission_data: ResourcePermissionCreate,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    permission_service: Annotated["PermissionService", Depends(get_permission_service)],
):
    """사용자에게 권한 부여 (관리자 전용)"""
    if not permission_service.db_conn:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="데이터베이스 연결이 필요합니다"
        )
    
    try:
        # 사용자 존재 확인
        auth_service = get_auth_service()
        user = await auth_service.get_user_by_id(str(user_id))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="사용자를 찾을 수 없습니다"
            )
        
        # 사용자 ID 강제 설정 (URL 파라미터 우선)
        permission_data.user_id = user_id
        permission_data.role_name = None
        
        await permission_service.grant_permission(
            user_id=user_id,
            role_name=None,
            resource_type=permission_data.resource_type,
            resource_name=permission_data.resource_name,
            actions=permission_data.actions,
            granted_by=current_user.id
        )
        
        # 생성된 권한 조회하여 반환
        query = """
            SELECT id, user_id, role_name, resource_type, resource_name, 
                   actions, conditions, granted_at, granted_by, expires_at
            FROM resource_permissions
            WHERE user_id = $1 AND resource_type = $2 AND resource_name = $3
            ORDER BY granted_at DESC
            LIMIT 1
        """
        
        row = await permission_service.db_conn.fetchrow(
            query,
            user_id,
            permission_data.resource_type.value,
            permission_data.resource_name
        )
        
        if not row:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="권한 생성 후 조회에 실패했습니다"
            )
        
        return ResourcePermissionResponse(
            id=row["id"],
            user_id=row["user_id"],
            role_name=row["role_name"],
            resource_type=ResourceType(row["resource_type"]),
            resource_name=row["resource_name"],
            actions=[ActionType(a) for a in row["actions"]],
            conditions=row["conditions"],
            granted_at=row["granted_at"],
            granted_by=row["granted_by"],
            expires_at=row["expires_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("사용자 권한 부여 실패", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"사용자 권한 부여에 실패했습니다: {str(e)}"
        )


# === 역할 관리 API ===

@app.get("/api/v1/roles", response_model=list[RoleResponse])
async def list_roles(
    current_user: Annotated[UserResponse, Depends(require_admin)],
    rbac_service: Annotated["RBACService", Depends(get_rbac_service)],
):
    """역할 목록 조회 (관리자 전용)"""
    try:
        roles = []
        for role_name, permissions in rbac_service.role_permissions.items():
            role = RoleResponse(
                name=role_name,
                description=f"{role_name} 역할",
                permissions=permissions
            )
            roles.append(role)
        
        return roles
        
    except Exception as e:
        logger.error("역할 목록 조회 실패", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="역할 목록 조회에 실패했습니다"
        )


@app.post("/api/v1/roles", response_model=RoleResponse)
async def create_role(
    role_data: RoleCreate,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    rbac_service: Annotated["RBACService", Depends(get_rbac_service)],
):
    """새 역할 생성 (관리자 전용)"""
    try:
        if role_data.name in rbac_service.role_permissions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"역할 '{role_data.name}'이 이미 존재합니다"
            )
        
        # 새 역할 생성
        permissions = role_data.permissions or []
        rbac_service.role_permissions[role_data.name] = permissions
        
        logger.info(
            "새 역할 생성",
            role_name=role_data.name,
            admin_id=current_user.id,
            permissions_count=len(permissions)
        )
        
        return RoleResponse(
            name=role_data.name,
            description=role_data.description,
            permissions=permissions
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("역할 생성 실패", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"역할 생성에 실패했습니다: {str(e)}"
        )


@app.put("/api/v1/roles/{role_name}", response_model=RoleResponse)
async def update_role(
    role_name: str,
    role_data: RoleUpdate,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    rbac_service: Annotated["RBACService", Depends(get_rbac_service)],
):
    """역할 수정 (관리자 전용)"""
    try:
        if role_name not in rbac_service.role_permissions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"역할 '{role_name}'을 찾을 수 없습니다"
            )
        
        # 권한 업데이트
        if role_data.permissions is not None:
            rbac_service.role_permissions[role_name] = role_data.permissions
        
        logger.info(
            "역할 수정 완료",
            role_name=role_name,
            admin_id=current_user.id
        )
        
        return RoleResponse(
            name=role_name,
            description=role_data.description,
            permissions=rbac_service.role_permissions[role_name]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("역할 수정 실패", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"역할 수정에 실패했습니다: {str(e)}"
        )


@app.delete("/api/v1/roles/{role_name}")
async def delete_role(
    role_name: str,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    rbac_service: Annotated["RBACService", Depends(get_rbac_service)],
):
    """역할 삭제 (관리자 전용)"""
    try:
        if role_name not in rbac_service.role_permissions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"역할 '{role_name}'을 찾을 수 없습니다"
            )
        
        # 기본 역할 삭제 방지
        if role_name in ["admin", "user", "guest"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"기본 역할 '{role_name}'은 삭제할 수 없습니다"
            )
        
        # 역할 삭제
        del rbac_service.role_permissions[role_name]
        
        logger.info(
            "역할 삭제 완료",
            role_name=role_name,
            admin_id=current_user.id
        )
        
        return {"message": f"역할 '{role_name}'이 성공적으로 삭제되었습니다"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("역할 삭제 실패", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"역할 삭제에 실패했습니다: {str(e)}"
        )



# === 사용자 검색 엔드포인트 ===

@app.get("/api/v1/users/search", response_model=list[UserResponse])
async def search_users(
    current_user: Annotated[UserResponse, Depends(get_current_active_user)],
    auth_service: Annotated[SQLiteAuthService, Depends(get_sqlite_auth_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
    q: str = "",
    limit: int = 10
):
    """사용자 검색 (이메일 또는 이름으로 검색)
    
    Args:
        q: 검색 쿼리 (이메일 또는 이름)
        limit: 결과 개수 제한 (기본값: 10, 최대: 50)
        current_user: 현재 인증된 사용자
        auth_service: 인증 서비스
        
    Returns:
        검색된 사용자 목록 (민감한 정보는 제외)
    """
    if limit > 50:
        limit = 50
    
    if not q.strip():
        # 빈 쿼리인 경우 최근 가입한 사용자들 반환
        return await auth_service.get_recent_users(limit)
    
    return await auth_service.search_users(q.strip(), limit)


@app.get("/api/v1/users/{user_id}", response_model=UserResponse)
async def get_user_by_id(
    user_id: str,
    current_user: Annotated[UserResponse, Depends(get_current_active_user)],
    auth_service: Annotated[SQLiteAuthService, Depends(get_sqlite_auth_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """ID로 사용자 조회
    
    Args:
        user_id: 조회할 사용자 ID
        current_user: 현재 인증된 사용자
        auth_service: 인증 서비스
        
    Returns:
        사용자 정보 (민감한 정보는 제외)
    """
    user = await auth_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다"
        )
    return user


# === 초기화 엔드포인트 (개발/테스트용) ===

@app.post("/api/v1/init/admin", response_model=UserResponse)
async def init_admin(
    auth_service: Annotated[SQLiteAuthService, Depends(get_sqlite_auth_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    초기 관리자 계정 생성 (개발/테스트 전용)
    
    주의: 이 엔드포인트는 프로덕션에서 비활성화해야 합니다!
    관리자가 없을 때만 작동하며, 이미 관리자가 있으면 실패합니다.
    
    Returns:
        UserResponse: 생성된 관리자 계정 정보
        
    Raises:
        HTTPException 400: 이미 관리자가 존재함
    """
    # 기존 관리자 확인
    all_users = await auth_service.list_all_users(skip=0, limit=1000)
    for user in all_users:
        if "admin" in user.roles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="이미 관리자가 존재합니다"
            )
    
    # 관리자 계정 생성
    try:
        # 1. 사용자 생성
        user_create = UserCreate(
            email="superadmin@mcp.com",
            password="SuperAdmin123!"
        )
        user = await auth_service.register(user_create)
        
        # 2. admin 역할 부여
        updated_user = await auth_service.user_repository.update(
            user.id,
            {"roles": ["admin"]}
        )
        
        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="관리자 역할 설정 실패"
            )
        
        logger.info("초기 관리자 생성 완료", user_id=user.id)
        return UserResponse(**updated_user.model_dump())
        
    except AuthenticationError as e:
        # 이미 존재하는 경우 역할만 업데이트
        existing_user = await auth_service.user_repository.get_by_email("superadmin@mcp.com")
        if existing_user:
            updated_user = await auth_service.user_repository.update(
                existing_user.id,
                {"roles": ["admin"]}
            )
            if updated_user:
                logger.info("기존 사용자를 관리자로 승격", user_id=existing_user.id)
                return UserResponse(**updated_user.model_dump())
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# === 관리자 엔드포인트 ===

@app.put("/api/v1/admin/users/{user_id}/roles", response_model=UserResponse)
async def update_user_roles(
    user_id: str,
    roles: list[str],
    current_user: Annotated[UserResponse, Depends(require_admin)],
    auth_service: Annotated[SQLiteAuthService, Depends(get_sqlite_auth_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """사용자 역할 업데이트 (관리자 전용)
    
    지정된 사용자의 역할을 업데이트합니다.
    
    Args:
        user_id: 업데이트할 사용자 ID
        roles: 새로운 역할 목록
        current_user: 현재 관리자 사용자
        auth_service: 인증 서비스 인스턴스
        
    Returns:
        UserResponse: 업데이트된 사용자 정보
        
    Raises:
        HTTPException 404: 사용자를 찾을 수 없음
        HTTPException 403: 관리자 권한 없음
    """
    # 사용자 조회
    user = await auth_service.user_repository.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"사용자를 찾을 수 없습니다: {user_id}"
        )
    
    # 역할 업데이트
    updated_user = await auth_service.user_repository.update(
        user_id,
        {"roles": roles}
    )
    
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="사용자 역할 업데이트 실패"
        )
    
    logger.info(
        "사용자 역할 업데이트",
        admin_id=current_user.id,
        user_id=user_id,
        new_roles=roles,
        old_roles=user.roles
    )
    
    return UserResponse(**updated_user.model_dump())


@app.get("/api/v1/admin/users", response_model=list[UserResponse])
async def list_users(
    current_user: Annotated[UserResponse, Depends(require_admin)],
    auth_service: Annotated[SQLiteAuthService, Depends(get_sqlite_auth_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = 0,
    limit: int = 50
):
    """모든 사용자 목록 조회 (관리자 전용)
    
    Args:
        skip: 건너뛸 사용자 수
        limit: 결과 개수 제한 (최대 100)
        current_user: 현재 관리자 사용자
        auth_service: 인증 서비스
    """
    if limit > 100:
        limit = 100
    
    return await auth_service.list_all_users(skip=skip, limit=limit)


@app.get("/api/v1/admin/users/stats")
async def get_user_stats(
    current_user: Annotated[UserResponse, Depends(require_admin)],
    auth_service: Annotated[SQLiteAuthService, Depends(get_sqlite_auth_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """사용자 통계 조회 (관리자 전용)"""
    return await auth_service.get_user_statistics()


# === 헬스체크 ===

@app.get("/health")
async def health_check():
    """
    서비스 상태 확인용 헬스체크 엔드포인트
    
    로드 밸런서나 모니터링 시스템에서 서비스 가용성을 확인하는 데 사용됩니다.
    인증이 필요 없는 공개 엔드포인트로, 서버의 기본적인 동작 상태를 반환합니다.
    
    Returns:
        dict: 서비스 상태 정보
            - status: "healthy" (정상 동작 시)
            - service: "auth-gateway" (서비스 식별자)
            - version: "1.0.0" (서비스 버전)
            
    HTTP 상태 코드:
        - 200 OK: 서비스 정상 동작
        - 5xx: 서비스 오류 (예외 발생 시)
        
    사용 시나리오:
        - 쿠버네티스 liveness/readiness probe
        - 로드 밸런서 상태 확인
        - 모니터링 시스템 ping
        - 서비스 배포 후 동작 확인
    """
    return {
        "status": "healthy",
        "service": "auth-gateway",
        "version": "1.0.0",
    }


# === FastHTML 관리 웹 페이지 ===

def create_layout(title: str, content, current_user=None):
    """공통 레이아웃 템플릿"""
    # FastHTML에서는 to_xml()을 직접 호출하지 않고 객체를 반환
    # FastAPI HTMLResponse와 함께 사용시 자동으로 변환됨
    return Html(
        Head(
            Title(f"{title} - MCP Auth Gateway"),
            Meta(charset="utf-8"),
            Meta(name="viewport", content="width=device-width, initial-scale=1"),
            # Tailwind CSS CDN
            Link(rel="stylesheet", href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css"),
            # Alpine.js for interactivity
            Script(src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js", defer=True)
        ),
        Body(
            # Navigation
            Nav(
                Div(
                    Div(
                        H1("MCP Auth Gateway", cls="text-xl font-bold text-white"),
                        cls="container mx-auto px-4 py-3 flex justify-between items-center"
                    ),
                    cls="bg-blue-600"
                ),
                Div(
                    Div(
                        A("대시보드", href="/admin", cls="px-3 py-2 text-sm font-medium text-gray-700 hover:text-blue-600"),
                        A("사용자 관리", href="/admin/users", cls="px-3 py-2 text-sm font-medium text-gray-700 hover:text-blue-600"),
                        A("권한 관리", href="/admin/permissions", cls="px-3 py-2 text-sm font-medium text-gray-700 hover:text-blue-600"),
                        A("역할 관리", href="/admin/roles", cls="px-3 py-2 text-sm font-medium text-gray-700 hover:text-blue-600"),
                        cls="container mx-auto px-4 flex space-x-4"
                    ),
                    cls="bg-gray-100 border-b"
                )
            ),
            # Main content
            Main(
                Div(
                    content,
                    cls="container mx-auto px-4 py-8"
                )
            ),
            cls="min-h-screen bg-gray-50"
        )
    )


@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(
    current_user: Annotated[UserResponse, Depends(require_admin)],
    auth_service: Annotated[SQLiteAuthService, Depends(get_sqlite_auth_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """관리자 대시보드"""
    try:
        # 사용자 통계 조회
        from .repositories.sqlite_user_repository import SQLiteUserRepository
        repository = SQLiteUserRepository(db)
        stats = await repository.get_user_stats()
        
        content = Div(
            H1("관리자 대시보드", cls="text-3xl font-bold text-gray-900 mb-8"),
            
            # 통계 카드들
            Div(
                # 총 사용자 수
                Div(
                    Div(
                        H3("총 사용자", cls="text-lg font-semibold text-gray-700"),
                        P(str(stats.get("total_users", 0)), cls="text-3xl font-bold text-blue-600"),
                        cls="p-6"
                    ),
                    cls="bg-white rounded-lg shadow-md"
                ),
                
                # 활성 사용자 수
                Div(
                    Div(
                        H3("활성 사용자", cls="text-lg font-semibold text-gray-700"),
                        P(str(stats.get("active_users", 0)), cls="text-3xl font-bold text-green-600"),
                        cls="p-6"
                    ),
                    cls="bg-white rounded-lg shadow-md"
                ),
                
                # 관리자 수
                Div(
                    Div(
                        H3("관리자", cls="text-lg font-semibold text-gray-700"),
                        P(str(stats.get("admin_users", 0)), cls="text-3xl font-bold text-purple-600"),
                        cls="p-6"
                    ),
                    cls="bg-white rounded-lg shadow-md"
                ),
                
                # 오늘 가입
                Div(
                    Div(
                        H3("오늘 가입", cls="text-lg font-semibold text-gray-700"),
                        P(str(stats.get("today_registrations", 0)), cls="text-3xl font-bold text-orange-600"),
                        cls="p-6"
                    ),
                    cls="bg-white rounded-lg shadow-md"
                ),
                
                cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8"
            ),
            
            # 빠른 액션
            Div(
                H2("빠른 액션", cls="text-2xl font-bold text-gray-900 mb-4"),
                Div(
                    A(
                        "사용자 관리",
                        href="/admin/users",
                        cls="inline-block bg-blue-500 hover:bg-blue-600 text-white font-medium py-2 px-4 rounded-lg mr-4 mb-2"
                    ),
                    A(
                        "권한 설정",
                        href="/admin/permissions", 
                        cls="inline-block bg-green-500 hover:bg-green-600 text-white font-medium py-2 px-4 rounded-lg mr-4 mb-2"
                    ),
                    A(
                        "역할 관리",
                        href="/admin/roles",
                        cls="inline-block bg-purple-500 hover:bg-purple-600 text-white font-medium py-2 px-4 rounded-lg mr-4 mb-2"
                    ),
                    A(
                        "API 문서",
                        href="/docs",
                        cls="inline-block bg-gray-500 hover:bg-gray-600 text-white font-medium py-2 px-4 rounded-lg mr-4 mb-2"
                    )
                ),
                cls="bg-white rounded-lg shadow-md p-6"
            )
        )
        
        page = create_layout("대시보드", content, current_user)
        # FastHTML 객체를 HTML 문자열로 변환
        html_content = to_xml(page)
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error("대시보드 로딩 실패", error=str(e))
        error_content = Div(
            H1("오류", cls="text-3xl font-bold text-red-600 mb-4"),
            P(f"대시보드를 로드하는 중 오류가 발생했습니다: {str(e)}", cls="text-gray-700")
        )
        page = create_layout("오류", error_content, current_user)
        html_content = to_xml(page)
        return HTMLResponse(content=html_content)


@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(
    current_user: Annotated[UserResponse, Depends(require_admin)],
    auth_service: Annotated[SQLiteAuthService, Depends(get_sqlite_auth_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """사용자 관리 페이지"""
    try:
        # 사용자 목록 조회
        from .repositories.sqlite_user_repository import SQLiteUserRepository
        repository = SQLiteUserRepository(db)
        users = await repository.list_all(skip=0, limit=50)
        
        content = Div(
            H1("사용자 관리", cls="text-3xl font-bold text-gray-900 mb-8"),
            
            # 사용자 목록 테이블
            Div(
                Table(
                    Thead(
                        Tr(
                            Th("ID", cls="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"),
                            Th("이메일", cls="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"),
                            Th("사용자명", cls="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"),
                            Th("역할", cls="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"),
                            Th("상태", cls="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"),
                            Th("가입일", cls="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"),
                            Th("액션", cls="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider")
                        )
                    ),
                    Tbody(
                        *[
                            Tr(
                                Td(str(user.id), cls="px-6 py-4 whitespace-nowrap text-sm text-gray-900"),
                                Td(user.email, cls="px-6 py-4 whitespace-nowrap text-sm text-gray-900"),
                                Td(user.username or "-", cls="px-6 py-4 whitespace-nowrap text-sm text-gray-900"),
                                Td(
                                    ", ".join(user.roles),
                                    cls="px-6 py-4 whitespace-nowrap text-sm text-gray-900"
                                ),
                                Td(
                                    Span(
                                        "활성" if user.is_active else "비활성",
                                        cls=f"px-2 inline-flex text-xs leading-5 font-semibold rounded-full {'bg-green-100 text-green-800' if user.is_active else 'bg-red-100 text-red-800'}"
                                    ),
                                    cls="px-6 py-4 whitespace-nowrap"
                                ),
                                Td(
                                    user.created_at.strftime("%Y-%m-%d"),
                                    cls="px-6 py-4 whitespace-nowrap text-sm text-gray-900"
                                ),
                                Td(
                                    Button(
                                        "권한 보기",
                                        onclick=f"window.location.href='/admin/users/{user.id}/permissions'",
                                        cls="text-blue-600 hover:text-blue-900 text-sm font-medium mr-2"
                                    ),
                                    Button(
                                        "역할 변경",
                                        onclick=f"openRoleModal({user.id}, '{user.email}', {user.roles})",
                                        cls="text-green-600 hover:text-green-900 text-sm font-medium"
                                    ),
                                    cls="px-6 py-4 whitespace-nowrap text-sm font-medium"
                                )
                            )
                            for user in users
                        ]
                    ),
                    cls="min-w-full divide-y divide-gray-200"
                ),
                cls="bg-white shadow overflow-hidden sm:rounded-lg"
            ),
            
            # 역할 변경 모달 (Alpine.js)
            Script("""
                function openRoleModal(userId, email, currentRoles) {
                    // TODO: 모달 구현
                    alert(`사용자 ${email}의 역할 변경 기능은 곧 구현될 예정입니다.`);
                }
            """)
        )
        
        page = create_layout("사용자 관리", content, current_user)
        html_content = to_xml(page)
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error("사용자 관리 페이지 로딩 실패", error=str(e))
        error_content = Div(
            H1("오류", cls="text-3xl font-bold text-red-600 mb-4"),
            P(f"사용자 관리 페이지를 로드하는 중 오류가 발생했습니다: {str(e)}", cls="text-gray-700")
        )
        page = create_layout("오류", error_content, current_user)
        html_content = to_xml(page)
        return HTMLResponse(content=html_content)


@app.get("/admin/permissions", response_class=HTMLResponse)
async def admin_permissions_page(
    current_user: Annotated[UserResponse, Depends(require_admin)],
    permission_service: Annotated["PermissionService", Depends(get_permission_service)],
):
    """권한 관리 페이지"""
    try:
        content = Div(
            H1("권한 관리", cls="text-3xl font-bold text-gray-900 mb-8"),
            
            # 권한 생성 폼
            Div(
                H2("새 권한 추가", cls="text-xl font-semibold text-gray-900 mb-4"),
                Form(
                    Div(
                        Div(
                            Label("대상 타입", cls="block text-sm font-medium text-gray-700 mb-2"),
                            Select(
                                Option("사용자별", value="user"),
                                Option("역할별", value="role"),
                                name="target_type",
                                cls="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                            ),
                            cls="mb-4"
                        ),
                        Div(
                            Label("리소스 타입", cls="block text-sm font-medium text-gray-700 mb-2"),
                            Select(
                                Option("웹 검색", value="web_search"),
                                Option("벡터 DB", value="vector_db"),
                                Option("데이터베이스", value="database"),
                                name="resource_type",
                                cls="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                            ),
                            cls="mb-4"
                        ),
                        cls="grid grid-cols-1 md:grid-cols-2 gap-4"
                    ),
                    Div(
                        Label("리소스 이름", cls="block text-sm font-medium text-gray-700 mb-2"),
                        Input(
                            type="text",
                            name="resource_name",
                            placeholder="예: public.*, users.documents",
                            cls="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                        ),
                        cls="mb-4"
                    ),
                    Div(
                        Label("권한", cls="block text-sm font-medium text-gray-700 mb-2"),
                        Div(
                            Label(
                                Input(type="checkbox", name="actions", value="read", cls="mr-2"),
                                "읽기",
                                cls="inline-flex items-center mr-4"
                            ),
                            Label(
                                Input(type="checkbox", name="actions", value="write", cls="mr-2"),
                                "쓰기",
                                cls="inline-flex items-center mr-4"
                            ),
                            Label(
                                Input(type="checkbox", name="actions", value="delete", cls="mr-2"),
                                "삭제",
                                cls="inline-flex items-center"
                            ),
                            cls="flex flex-wrap"
                        ),
                        cls="mb-4"
                    ),
                    Button(
                        "권한 추가",
                        type="submit",
                        cls="bg-blue-500 hover:bg-blue-600 text-white font-medium py-2 px-4 rounded-lg"
                    ),
                    method="post",
                    action="/admin/permissions/create",
                    cls="space-y-4"
                ),
                cls="bg-white rounded-lg shadow-md p-6 mb-8"
            ),
            
            # 기존 권한 목록
            Div(
                H2("기존 권한 목록", cls="text-xl font-semibold text-gray-900 mb-4"),
                P("권한 목록을 보려면 API를 통해 조회하세요.", cls="text-gray-600"),
                A(
                    "권한 API 보기",
                    href="/docs#/default/list_resource_permissions_api_v1_permissions_resources_get",
                    cls="inline-block bg-gray-500 hover:bg-gray-600 text-white font-medium py-2 px-4 rounded-lg mt-4"
                ),
                cls="bg-white rounded-lg shadow-md p-6"
            )
        )
        
        page = create_layout("권한 관리", content, current_user)
        html_content = to_xml(page)
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error("권한 관리 페이지 로딩 실패", error=str(e))
        error_content = Div(
            H1("오류", cls="text-3xl font-bold text-red-600 mb-4"),
            P(f"권한 관리 페이지를 로드하는 중 오류가 발생했습니다: {str(e)}", cls="text-gray-700")
        )
        page = create_layout("오류", error_content, current_user)
        html_content = to_xml(page)
        return HTMLResponse(content=html_content)


@app.get("/admin/roles", response_class=HTMLResponse)
async def admin_roles_page(
    current_user: Annotated[UserResponse, Depends(require_admin)],
    rbac_service: Annotated["RBACService", Depends(get_rbac_service)],
):
    """역할 관리 페이지"""
    try:
        # 역할 목록 조회
        roles = []
        for role_name, permissions in rbac_service.role_permissions.items():
            roles.append({
                "name": role_name,
                "permissions": permissions,
                "permission_count": len(permissions)
            })
        
        content = Div(
            H1("역할 관리", cls="text-3xl font-bold text-gray-900 mb-8"),
            
            # 역할 생성 폼
            Div(
                H2("새 역할 추가", cls="text-xl font-semibold text-gray-900 mb-4"),
                Form(
                    Div(
                        Label("역할 이름", cls="block text-sm font-medium text-gray-700 mb-2"),
                        Input(
                            type="text",
                            name="name",
                            placeholder="예: editor, viewer",
                            cls="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                        ),
                        cls="mb-4"
                    ),
                    Div(
                        Label("설명 (선택사항)", cls="block text-sm font-medium text-gray-700 mb-2"),
                        Textarea(
                            name="description",
                            placeholder="역할에 대한 설명을 입력하세요",
                            rows="3",
                            cls="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                        ),
                        cls="mb-4"
                    ),
                    Button(
                        "역할 생성",
                        type="submit",
                        cls="bg-green-500 hover:bg-green-600 text-white font-medium py-2 px-4 rounded-lg"
                    ),
                    method="post",
                    action="/admin/roles/create",
                    cls="space-y-4"
                ),
                cls="bg-white rounded-lg shadow-md p-6 mb-8"
            ),
            
            # 기존 역할 목록
            Div(
                H2("기존 역할 목록", cls="text-xl font-semibold text-gray-900 mb-4"),
                Div(
                    P(f"총 {len(roles)}개의 역할이 있습니다.", cls="text-gray-600"),
                    cls="bg-white rounded-lg shadow-md p-6"
                )
            ),
            
            # JavaScript 함수들
            Script("""
                function editRole(roleName) {
                    alert(`역할 '${roleName}' 수정 기능은 곧 구현될 예정입니다.`);
                }
                
                function deleteRole(roleName) {
                    if (confirm(`정말로 역할 '${roleName}'을 삭제하시겠습니까?`)) {
                        fetch(`/api/v1/roles/${roleName}`, {
                            method: 'DELETE',
                            headers: {
                                'Authorization': 'Bearer ' + localStorage.getItem('access_token')
                            }
                        })
                        .then(response => response.json())
                        .then(data => {
                            alert('역할이 삭제되었습니다.');
                            location.reload();
                        })
                        .catch(error => {
                            alert('역할 삭제 중 오류가 발생했습니다.');
                        });
                    }
                }
            """)
        )
        
        page = create_layout("역할 관리", content, current_user)
        html_content = to_xml(page)
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error("역할 관리 페이지 로딩 실패", error=str(e))
        error_content = Div(
            H1("오류", cls="text-3xl font-bold text-red-600 mb-4"),
            P(f"역할 관리 페이지를 로드하는 중 오류가 발생했습니다: {str(e)}", cls="text-gray-700")
        )
        page = create_layout("오류", error_content, current_user)
        html_content = to_xml(page)
        return HTMLResponse(content=html_content)


@app.get("/admin/users/{user_id}/permissions", response_class=HTMLResponse)
async def admin_user_permissions_page(
    user_id: int,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    auth_service: Annotated[SQLiteAuthService, Depends(get_sqlite_auth_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
    permission_service: Annotated["PermissionService", Depends(get_permission_service)],
):
    """사용자별 권한 관리 페이지"""
    try:
        # 사용자 정보 조회
        user = await auth_service.get_user_by_id(str(user_id))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="사용자를 찾을 수 없습니다"
            )
        
        # 사용자 권한 조회 (API 호출 시뮬레이션)
        permissions = []
        if permission_service.db_conn:
            try:
                query = """
                    SELECT id, resource_type, resource_name, actions, granted_at
                    FROM resource_permissions
                    WHERE user_id = $1
                    ORDER BY granted_at DESC
                """
                rows = await permission_service.db_conn.fetch(query, user_id)
                permissions = [
                    {
                        "id": row["id"],
                        "resource_type": row["resource_type"],
                        "resource_name": row["resource_name"],
                        "actions": row["actions"],
                        "granted_at": row["granted_at"]
                    }
                    for row in rows
                ]
            except Exception as e:
                logger.warning("사용자 권한 조회 실패", error=str(e))
        
        content = Div(
            Div(
                A("← 사용자 관리로 돌아가기", href="/admin/users", cls="text-blue-600 hover:text-blue-800 mb-4 inline-block"),
                cls="mb-4"
            ),
            
            H1(f"{user.email}의 권한 관리", cls="text-3xl font-bold text-gray-900 mb-8"),
            
            # 사용자 정보
            Div(
                H2("사용자 정보", cls="text-xl font-semibold text-gray-900 mb-4"),
                Div(
                    P(f"이메일: {user.email}", cls="mb-2"),
                    P(f"사용자명: {user.username or '-'}", cls="mb-2"),
                    P(f"역할: {', '.join(user.roles)}", cls="mb-2"),
                    P(f"상태: {'활성' if user.is_active else '비활성'}", cls="mb-2"),
                    P(f"가입일: {user.created_at.strftime('%Y-%m-%d')}", cls="mb-2"),
                    cls="text-gray-700"
                ),
                cls="bg-white rounded-lg shadow-md p-6 mb-8"
            ),
            
            # 개별 권한 목록  
            Div(
                H2("개별 권한", cls="text-xl font-semibold text-gray-900 mb-4"),
                Div(
                    P(f"총 {len(permissions) if permissions else 0}개의 개별 권한이 있습니다." if permissions else "이 사용자에게 부여된 개별 권한이 없습니다.", cls="text-gray-600 text-center py-8"),
                    cls="bg-white rounded-lg shadow-md"
                )
            ),
            
            # 권한 추가 폼
            Div(
                H2("새 권한 추가", cls="text-xl font-semibold text-gray-900 mb-4"),
                Form(
                    Input(type="hidden", name="user_id", value=str(user_id)),
                    Div(
                        Div(
                            Label("리소스 타입", cls="block text-sm font-medium text-gray-700 mb-2"),
                            Select(
                                Option("웹 검색", value="web_search"),
                                Option("벡터 DB", value="vector_db"),
                                Option("데이터베이스", value="database"),
                                name="resource_type",
                                cls="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                            ),
                            cls="mb-4"
                        ),
                        Div(
                            Label("리소스 이름", cls="block text-sm font-medium text-gray-700 mb-2"),
                            Input(
                                type="text",
                                name="resource_name",
                                placeholder="예: public.*, users.documents",
                                cls="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                            ),
                            cls="mb-4"
                        ),
                        cls="grid grid-cols-1 md:grid-cols-2 gap-4"
                    ),
                    Div(
                        Label("권한", cls="block text-sm font-medium text-gray-700 mb-2"),
                        Div(
                            Label(
                                Input(type="checkbox", name="actions", value="read", cls="mr-2"),
                                "읽기",
                                cls="inline-flex items-center mr-4"
                            ),
                            Label(
                                Input(type="checkbox", name="actions", value="write", cls="mr-2"),
                                "쓰기",
                                cls="inline-flex items-center mr-4"
                            ),
                            Label(
                                Input(type="checkbox", name="actions", value="delete", cls="mr-2"),
                                "삭제",
                                cls="inline-flex items-center"
                            ),
                            cls="flex flex-wrap"
                        ),
                        cls="mb-4"
                    ),
                    Button(
                        "권한 추가",
                        type="submit",
                        cls="bg-blue-500 hover:bg-blue-600 text-white font-medium py-2 px-4 rounded-lg"
                    ),
                    method="post",
                    action=f"/admin/users/{user_id}/permissions/create",
                    cls="space-y-4"
                ),
                cls="bg-white rounded-lg shadow-md p-6"
            ),
            
            # JavaScript 함수들
            Script("""
                function deletePermission(permissionId) {
                    if (confirm('정말로 이 권한을 삭제하시겠습니까?')) {
                        fetch(`/api/v1/permissions/resources/${permissionId}`, {
                            method: 'DELETE',
                            headers: {
                                'Authorization': 'Bearer ' + localStorage.getItem('access_token')
                            }
                        })
                        .then(response => response.json())
                        .then(data => {
                            alert('권한이 삭제되었습니다.');
                            location.reload();
                        })
                        .catch(error => {
                            alert('권한 삭제 중 오류가 발생했습니다.');
                        });
                    }
                }
            """)
        )
        
        page = create_layout(f"{user.email} 권한 관리", content, current_user)
        html_content = to_xml(page)
        return HTMLResponse(content=html_content)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("사용자 권한 페이지 로딩 실패", error=str(e))
        error_content = Div(
            H1("오류", cls="text-3xl font-bold text-red-600 mb-4"),
            P(f"사용자 권한 페이지를 로드하는 중 오류가 발생했습니다: {str(e)}", cls="text-gray-700")
        )
        page = create_layout("오류", error_content, current_user)
        html_content = to_xml(page)
        return HTMLResponse(content=html_content)


# === 에러 핸들러 ===

@app.exception_handler(AuthenticationError)
async def authentication_error_handler(
    request: Request,
    exc: AuthenticationError,
):
    """인증 오류 핸들러"""
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": str(exc)},
        headers={"WWW-Authenticate": "Bearer"},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTP 예외 핸들러"""
    logger.warning(
        "HTTP 예외 발생",
        path=request.url.path,
        status_code=exc.status_code,
        detail=exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """일반 예외 핸들러"""
    logger.error(
        "예상치 못한 오류",
        path=request.url.path,
        error=str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "내부 서버 오류가 발생했습니다"},
    )


def main():
    """
    인증 게이트웨이 서버 실행
    
    개발 환경에서 사용하는 서버 실행 함수입니다.
    uvicorn을 사용하여 FastAPI 애플리케이션을 실행하며,
    자동 재로드와 상세한 로깅을 활성화합니다.
    
    실행 설정:
        - 호스트: 0.0.0.0 (모든 인터페이스에서 접근 허용)
        - 포트: 8000 (기본 인증 게이트웨이 포트)
        - 자동 재로드: True (코드 변경 시 자동 재시작)
        - 로그 레벨: info
        
    사용법:
        ```bash
        # 스크립트로 실행
        python -m src.auth.server
        
        # 또는 함수 직접 호출
        from src.auth.server import main
        main()
        ```
        
    주의사항:
        - 개발 환경 전용 (production에서는 gunicorn 등 사용)
        - 환경 변수 설정 필요 (JWT_SECRET_KEY 등)
        - MCP 서버가 별도로 실행되어야 함
    """
    uvicorn.run(
        "src.auth.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()