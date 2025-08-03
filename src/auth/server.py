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
"""

import csv
import io
import json
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Annotated, Optional, AsyncGenerator
from collections import deque

# 재사용 가능한 컴포넌트 import
from .components import (
    AdminTable, AdminModal, AdminForm, StatsCard, 
    FilterBar, AdminCard, AdminBreadcrumb, LoadingSpinner,
    AnalyticsChart, ExportButton, MetricsTable, NotificationBanner,
    LanguageSelector
)
# 번역 시스템 import
from .translations import T, get_user_language, set_user_language, SUPPORTED_LANGUAGES
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import FastAPI, Depends, HTTPException, status, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from sse_starlette import EventSourceResponse
from fasthtml.common import (
    Div,
    P,
    H1,
    H2,
    H3,
    A,
    Form,
    Input,
    Button,
    Table,
    Thead,
    Tbody,
    Tr,
    Th,
    Td,
    Script,
    Title,
    Meta,
    Link,
    Canvas,
    Span,
    Nav,
    Label,
    Select,
    Option,
    Span,
    Main,
    Html,
    Body,
    Head,
    Textarea,
    Ul,
    Li,
)
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
from .request_models import RefreshTokenRequest
from .services import (
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
        import redis.asyncio as redis
        from .repositories.token_repository import RedisTokenRepository

        jwt_secret = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")

        # Redis 연결 및 토큰 저장소 설정
        token_repository = None
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            try:
                redis_client = redis.from_url(redis_url, decode_responses=True)
                token_repository = RedisTokenRepository(redis_client)
                logger.info("Redis 토큰 저장소 활성화됨")
            except Exception as e:
                logger.warning(f"Redis 연결 실패, 토큰 무효화 기능 비활성화: {e}")

        jwt_service = JWTService(
            secret_key=jwt_secret, token_repository=token_repository
        )
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
        structlog.dev.ConsoleRenderer(),
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
    from .services.auth_service_sqlite import SQLiteAuthService
    from .services.jwt_service import JWTService
    from .models import UserCreate
    import os

    logger.info("데이터베이스 초기화 시작")
    await init_db()
    logger.info("데이터베이스 테이블 생성 완료")

    # 초기 관리자 계정 생성
    try:
        from .init_admin import init_admin_on_startup
        await init_admin_on_startup()
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

# SSE (Server-Sent Events) 이벤트 관리
event_queue: deque = deque(maxlen=100)  # 최대 100개 이벤트 유지
active_connections: set = set()  # 활성 SSE 연결 추적

def send_notification(type: str, message: str, title: Optional[str] = None, **kwargs):
    """실시간 알림 이벤트 발송"""
    event_data = {
        "type": type,  # "success", "warning", "error", "info"
        "message": message,
        "title": title,
        "timestamp": datetime.utcnow().isoformat(),
        **kwargs
    }
    
    # 이벤트 큐에 추가
    event_queue.append(event_data)
    logger.info(f"SSE 알림 발송: {type} - {message}")

def send_user_event(event_type: str, user_data: dict):
    """사용자 관련 이벤트 발송"""
    send_notification(
        type="info",
        message=f"새 사용자가 등록되었습니다: {user_data.get('email', 'Unknown')}",
        title="사용자 등록",
        event_type=event_type,
        user_data=user_data
    )

def send_permission_event(event_type: str, permission_data: dict):
    """권한 변경 이벤트 발송"""
    send_notification(
        type="warning",
        message=f"권한이 변경되었습니다: {permission_data.get('resource_type', 'Unknown')}",
        title="권한 변경",
        event_type=event_type,
        permission_data=permission_data
    )

def send_system_error(error_msg: str, error_details: Optional[dict] = None):
    """시스템 오류 이벤트 발송"""
    send_notification(
        type="error",
        message=f"시스템 오류 발생: {error_msg}",
        title="시스템 오류",
        event_type="system_error",
        error_details=error_details
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
        
        # SSE 알림 발송
        send_user_event("user_registered", {
            "email": user.email,
            "username": user.username,
            "id": user.id,
            "roles": user.roles
        })
        
        return user
    except AuthenticationError as e:
        logger.warning("사용자 등록 실패", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except ValueError as e:
        # Legacy support - ValueError를 AuthenticationError로 처리
        logger.warning("사용자 등록 실패 (유효성 검사)", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        # 예상치 못한 오류에 대한 안전장치
        error_message = str(e)
        logger.error(
            "사용자 등록 중 예상치 못한 오류", error=error_message, exc_info=True
        )

        # 특정 에러 메시지는 사용자에게 전달 (중복 이메일 등)
        if (
            "이미 등록된" in error_message
            or "already exists" in error_message.lower()
            or "duplicate" in error_message.lower()
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="이미 등록된 이메일입니다",
            )

        # 그 외의 경우 일반적인 오류 메시지로 응답
        # 보안을 위해 내부 오류 정보는 노출하지 않음
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="서버 내부 오류가 발생했습니다",
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
            secure=False,  # HTTPS가 아닌 환경에서도 동작 (개발용)
            samesite="lax",  # CSRF 방지
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
    request: RefreshTokenRequest,
    auth_service: Annotated[SQLiteAuthService, Depends(get_sqlite_auth_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    토큰 갱신

    리프레시 토큰을 사용하여 새로운 액세스 토큰을 발급받습니다.

    Args:
        request: RefreshTokenRequest - 리프레시 토큰을 포함한 요청
        auth_service: SQLiteAuthService - 인증 서비스
        db: AsyncSession - 데이터베이스 세션

    Returns:
        AuthTokens: 새로운 액세스 토큰과 리프레시 토큰

    Raises:
        HTTPException 401: 유효하지 않거나 만료된 리프레시 토큰
    """
    try:
        # 명확한 파라미터 전달: refresh_token과 session
        tokens = await auth_service.refresh_tokens(
            refresh_token=request.refresh_token,
            session=db,  # 'db'가 아닌 'session' 파라미터명 사용
        )
        logger.info("토큰 갱신 성공")
        return tokens
    except AuthenticationError as e:
        logger.warning("토큰 갱신 실패", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        # 예상치 못한 오류 처리
        logger.error("토큰 갱신 중 예상치 못한 오류", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="토큰 갱신 중 오류가 발생했습니다",
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
        <script src="https://unpkg.com/htmx.org@1.9.12"></script>
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
            <button 
                hx-get="/auth/test-me" 
                hx-target="#message"
                hx-headers='{"Authorization": "Bearer " + (currentAccessToken || "")}'
                class="btn-primary">현재 사용자 정보 조회</button>
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

        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


# === 권한 관리 API (Admin Page용) ===


@app.get(
    "/api/v1/permissions/resources", response_model=list[ResourcePermissionResponse]
)
async def list_resource_permissions(
    current_user: Annotated[UserResponse, Depends(require_admin)],
    permission_service=Depends(get_permission_service),
    resource_type: Optional[ResourceType] = None,
    resource_name: Optional[str] = None,
    user_id: Optional[int] = None,
    role_name: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
):
    """리소스 권한 목록 조회 (관리자 전용)"""
    if not permission_service.db_conn:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="데이터베이스 연결이 필요합니다",
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
                expires_at=row["expires_at"],
            )
            permissions.append(perm)

        return permissions

    except Exception as e:
        logger.error("권한 목록 조회 실패", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="권한 목록 조회에 실패했습니다",
        )


@app.post("/api/v1/permissions/resources", response_model=ResourcePermissionResponse)
async def create_resource_permission(
    permission_data: ResourcePermissionCreate,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    permission_service=Depends(get_permission_service),
):
    """리소스 권한 생성 (관리자 전용)"""
    if not permission_service.db_conn:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="데이터베이스 연결이 필요합니다",
        )

    # user_id와 role_name 중 하나는 필수
    if not permission_data.user_id and not permission_data.role_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_id 또는 role_name 중 하나는 필수입니다",
        )

    try:
        await permission_service.grant_permission(
            user_id=permission_data.user_id,
            role_name=permission_data.role_name,
            resource_type=permission_data.resource_type,
            resource_name=permission_data.resource_name,
            actions=permission_data.actions,
            granted_by=current_user.id,
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
            permission_data.role_name,
        )

        if not row:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="권한 생성 후 조회에 실패했습니다",
            )

        # SSE 권한 변경 알림 발송
        send_permission_event("permission_created", {
            "resource_type": permission_data.resource_type.value,
            "resource_name": permission_data.resource_name,
            "actions": permission_data.actions,
            "user_id": permission_data.user_id,
            "role_name": permission_data.role_name,
            "granted_by": current_user.email
        })

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
            expires_at=row["expires_at"],
        )

    except Exception as e:
        logger.error("권한 생성 실패", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"권한 생성에 실패했습니다: {str(e)}",
        )


@app.put(
    "/api/v1/permissions/resources/{permission_id}",
    response_model=ResourcePermissionResponse,
)
async def update_resource_permission(
    permission_id: int,
    permission_data: ResourcePermissionUpdate,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    permission_service=Depends(get_permission_service),
):
    """리소스 권한 수정 (관리자 전용)"""
    if not permission_service.db_conn:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="데이터베이스 연결이 필요합니다",
        )

    try:
        # 기존 권한 확인
        existing_query = """
            SELECT id, user_id, role_name, resource_type, resource_name, 
                   actions, conditions, granted_at, granted_by, expires_at
            FROM resource_permissions
            WHERE id = $1
        """

        existing_row = await permission_service.db_conn.fetchrow(
            existing_query, permission_id
        )
        if not existing_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="권한을 찾을 수 없습니다"
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
                detail="업데이트할 필드가 없습니다",
            )

        # 업데이트 쿼리 실행
        update_query = f"""
            UPDATE resource_permissions
            SET {", ".join(update_fields)}
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
            expires_at=updated_row["expires_at"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("권한 수정 실패", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"권한 수정에 실패했습니다: {str(e)}",
        )


@app.delete("/api/v1/permissions/resources/{permission_id}")
async def delete_resource_permission(
    permission_id: int,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    permission_service=Depends(get_permission_service),
):
    """리소스 권한 삭제 (관리자 전용)"""
    if not permission_service.db_conn:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="데이터베이스 연결이 필요합니다",
        )

    try:
        # 기존 권한 확인 및 사용자 ID 가져오기
        check_query = """
            SELECT user_id, role_name, resource_type, resource_name
            FROM resource_permissions
            WHERE id = $1
        """

        existing_row = await permission_service.db_conn.fetchrow(
            check_query, permission_id
        )
        if not existing_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="권한을 찾을 수 없습니다"
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
            role_name=existing_row["role_name"],
        )

        return {"message": "권한이 성공적으로 삭제되었습니다"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("권한 삭제 실패", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"권한 삭제에 실패했습니다: {str(e)}",
        )


# === 사용자별 권한 관리 API ===


@app.get(
    "/api/v1/users/{user_id}/permissions",
    response_model=list[ResourcePermissionResponse],
)
async def get_user_permissions(
    user_id: int,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    permission_service=Depends(get_permission_service),
):
    """사용자의 리소스 권한 조회 (관리자 전용)"""
    if not permission_service.db_conn:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="데이터베이스 연결이 필요합니다",
        )

    try:
        # 사용자 존재 확인
        auth_service = get_auth_service()
        user = await auth_service.get_user_by_id(str(user_id))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="사용자를 찾을 수 없습니다",
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
                expires_at=row["expires_at"],
            )
            permissions.append(perm)

        return permissions

    except HTTPException:
        raise
    except Exception as e:
        logger.error("사용자 권한 조회 실패", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="사용자 권한 조회에 실패했습니다",
        )


@app.post(
    "/api/v1/users/{user_id}/permissions", response_model=ResourcePermissionResponse
)
async def grant_user_permission(
    user_id: int,
    permission_data: ResourcePermissionCreate,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    permission_service=Depends(get_permission_service),
):
    """사용자에게 권한 부여 (관리자 전용)"""
    if not permission_service.db_conn:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="데이터베이스 연결이 필요합니다",
        )

    try:
        # 사용자 존재 확인
        auth_service = get_auth_service()
        user = await auth_service.get_user_by_id(str(user_id))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="사용자를 찾을 수 없습니다",
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
            granted_by=current_user.id,
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
            permission_data.resource_name,
        )

        if not row:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="권한 생성 후 조회에 실패했습니다",
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
            expires_at=row["expires_at"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("사용자 권한 부여 실패", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"사용자 권한 부여에 실패했습니다: {str(e)}",
        )


# === 역할 관리 API ===


@app.get("/api/v1/roles", response_model=list[RoleResponse])
async def list_roles(
    current_user: Annotated[UserResponse, Depends(require_admin)],
    rbac_service=Depends(get_rbac_service),
):
    """역할 목록 조회 (관리자 전용)"""
    try:
        roles = []
        for role_name, permissions in rbac_service.role_permissions.items():
            role = RoleResponse(
                name=role_name, description=f"{role_name} 역할", permissions=permissions
            )
            roles.append(role)

        return roles

    except Exception as e:
        logger.error("역할 목록 조회 실패", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="역할 목록 조회에 실패했습니다",
        )


@app.post("/api/v1/roles", response_model=RoleResponse)
async def create_role(
    role_data: RoleCreate,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    rbac_service=Depends(get_rbac_service),
):
    """새 역할 생성 (관리자 전용)"""
    try:
        if role_data.name in rbac_service.role_permissions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"역할 '{role_data.name}'이 이미 존재합니다",
            )

        # 새 역할 생성
        permissions = role_data.permissions or []
        rbac_service.role_permissions[role_data.name] = permissions

        logger.info(
            "새 역할 생성",
            role_name=role_data.name,
            admin_id=current_user.id,
            permissions_count=len(permissions),
        )

        return RoleResponse(
            name=role_data.name,
            description=role_data.description,
            permissions=permissions,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("역할 생성 실패", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"역할 생성에 실패했습니다: {str(e)}",
        )


@app.put("/api/v1/roles/{role_name}", response_model=RoleResponse)
async def update_role(
    role_name: str,
    role_data: RoleUpdate,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    rbac_service=Depends(get_rbac_service),
):
    """역할 수정 (관리자 전용)"""
    try:
        if role_name not in rbac_service.role_permissions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"역할 '{role_name}'을 찾을 수 없습니다",
            )

        # 권한 업데이트
        if role_data.permissions is not None:
            rbac_service.role_permissions[role_name] = role_data.permissions

        logger.info("역할 수정 완료", role_name=role_name, admin_id=current_user.id)

        return RoleResponse(
            name=role_name,
            description=role_data.description,
            permissions=rbac_service.role_permissions[role_name],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("역할 수정 실패", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"역할 수정에 실패했습니다: {str(e)}",
        )


@app.delete("/api/v1/roles/{role_name}")
async def delete_role(
    role_name: str,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    rbac_service=Depends(get_rbac_service),
):
    """역할 삭제 (관리자 전용)"""
    try:
        if role_name not in rbac_service.role_permissions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"역할 '{role_name}'을 찾을 수 없습니다",
            )

        # 기본 역할 삭제 방지
        if role_name in ["admin", "user", "guest"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"기본 역할 '{role_name}'은 삭제할 수 없습니다",
            )

        # 역할 삭제
        del rbac_service.role_permissions[role_name]

        logger.info("역할 삭제 완료", role_name=role_name, admin_id=current_user.id)

        return {"message": f"역할 '{role_name}'이 성공적으로 삭제되었습니다"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("역할 삭제 실패", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"역할 삭제에 실패했습니다: {str(e)}",
        )


# === 사용자 검색 엔드포인트 ===


@app.get("/api/v1/users/search", response_model=list[UserResponse])
async def search_users(
    current_user: Annotated[UserResponse, Depends(get_current_active_user)],
    auth_service: Annotated[SQLiteAuthService, Depends(get_sqlite_auth_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
    q: str = "",
    limit: int = 10,
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
            status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다"
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
                detail="이미 관리자가 존재합니다",
            )

    # 관리자 계정 생성
    try:
        # 1. 사용자 생성
        user_create = UserCreate(email="superadmin@mcp.com", password="SuperAdmin123!")
        user = await auth_service.register(user_create)

        # 2. admin 역할 부여
        updated_user = await auth_service.user_repository.update(
            user.id, {"roles": ["admin"]}
        )

        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="관리자 역할 설정 실패",
            )

        logger.info("초기 관리자 생성 완료", user_id=user.id)
        return UserResponse(**updated_user.model_dump())

    except AuthenticationError as e:
        # 이미 존재하는 경우 역할만 업데이트
        existing_user = await auth_service.user_repository.get_by_email(
            "superadmin@mcp.com"
        )
        if existing_user:
            updated_user = await auth_service.user_repository.update(
                existing_user.id, {"roles": ["admin"]}
            )
            if updated_user:
                logger.info("기존 사용자를 관리자로 승격", user_id=existing_user.id)
                return UserResponse(**updated_user.model_dump())

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


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
            detail=f"사용자를 찾을 수 없습니다: {user_id}",
        )

    # 역할 업데이트
    updated_user = await auth_service.user_repository.update(user_id, {"roles": roles})

    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="사용자 역할 업데이트 실패",
        )

    logger.info(
        "사용자 역할 업데이트",
        admin_id=current_user.id,
        user_id=user_id,
        new_roles=roles,
        old_roles=user.roles,
    )

    return UserResponse(**updated_user.model_dump())


@app.get("/api/v1/admin/users", response_model=list[UserResponse])
async def list_users(
    current_user: Annotated[UserResponse, Depends(require_admin)],
    auth_service: Annotated[SQLiteAuthService, Depends(get_sqlite_auth_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = 0,
    limit: int = 50,
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


# === 토큰 관리 API (관리자 전용) ===


@app.get("/api/v1/admin/users/{user_id}/sessions", response_model=list[dict])
async def get_user_sessions(
    user_id: str,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    auth_service: Annotated[SQLiteAuthService, Depends(get_sqlite_auth_service)],
):
    """특정 사용자의 활성 세션(토큰) 목록 조회

    Args:
        user_id: 대상 사용자 ID

    Returns:
        사용자의 활성 세션 정보 목록
    """
    sessions = await auth_service.jwt_service.get_active_sessions(user_id)
    logger.info(
        "관리자가 사용자 세션 조회",
        admin_id=current_user.id,
        target_user_id=user_id,
        session_count=len(sessions),
    )
    return sessions


@app.post("/api/v1/admin/users/{user_id}/revoke-tokens")
async def revoke_user_tokens(
    user_id: str,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    auth_service: Annotated[SQLiteAuthService, Depends(get_sqlite_auth_service)],
    device_id: Optional[str] = None,
):
    """사용자의 토큰 무효화 (전체 또는 특정 디바이스)

    Args:
        user_id: 대상 사용자 ID
        device_id: 특정 디바이스 ID (없으면 모든 토큰 무효화)

    Returns:
        무효화 결과
    """
    if device_id:
        # 특정 디바이스 토큰만 무효화
        success = await auth_service.jwt_service.revoke_refresh_token(
            user_id, device_id
        )
        logger.info(
            "관리자가 사용자 디바이스 토큰 무효화",
            admin_id=current_user.id,
            target_user_id=user_id,
            device_id=device_id,
            success=success,
        )
        return {
            "success": success,
            "message": f"디바이스 {device_id}의 토큰이 무효화되었습니다."
            if success
            else "토큰 무효화 실패",
        }
    else:
        # 모든 토큰 무효화
        count = await auth_service.jwt_service.revoke_all_user_tokens(user_id)
        logger.info(
            "관리자가 사용자 모든 토큰 무효화",
            admin_id=current_user.id,
            target_user_id=user_id,
            revoked_count=count,
        )
        return {
            "success": count > 0,
            "revoked_count": count,
            "message": f"{count}개의 토큰이 무효화되었습니다.",
        }


@app.post("/api/v1/admin/tokens/revoke/{jti}")
async def revoke_token_by_jti(
    jti: str,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    auth_service: Annotated[SQLiteAuthService, Depends(get_sqlite_auth_service)],
):
    """특정 JWT ID로 토큰 무효화

    Args:
        jti: JWT ID (토큰의 고유 식별자)

    Returns:
        무효화 결과
    """
    if not auth_service.jwt_service.token_repository:
        raise HTTPException(
            status_code=503, detail="토큰 무효화 기능이 활성화되지 않았습니다."
        )

    success = await auth_service.jwt_service.token_repository.revoke_token(jti)
    logger.info(
        "관리자가 특정 토큰 무효화", admin_id=current_user.id, jti=jti, success=success
    )

    return {
        "success": success,
        "message": "토큰이 무효화되었습니다."
        if success
        else "토큰을 찾을 수 없거나 이미 무효화되었습니다.",
    }


@app.get("/api/v1/admin/sessions/active", response_model=list[dict])
async def get_all_active_sessions(
    current_user: Annotated[UserResponse, Depends(require_admin)],
    auth_service: Annotated[SQLiteAuthService, Depends(get_sqlite_auth_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 100,
):
    """모든 활성 세션 조회 (관리자 전용)

    Returns:
        모든 사용자의 활성 세션 정보
    """
    # 모든 사용자 조회
    repository = SQLiteUserRepository(db)
    users = await repository.list_all(limit=limit)

    all_sessions = []
    for user in users:
        sessions = await auth_service.jwt_service.get_active_sessions(user.id)
        for session in sessions:
            session["user_email"] = user.email
            session["user_id"] = user.id
            all_sessions.append(session)

    logger.info(
        "관리자가 모든 활성 세션 조회",
        admin_id=current_user.id,
        total_sessions=len(all_sessions),
    )

    return all_sessions


# === 세션 관리 페이지 (FastHTML) ===


@app.get("/admin/sessions", response_class=HTMLResponse)
async def admin_sessions_page(
    current_user: Annotated[UserResponse, Depends(require_admin)],
    auth_service: Annotated[SQLiteAuthService, Depends(get_sqlite_auth_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """세션 관리 페이지 (HTMX 기반)"""
    try:
        # 모든 활성 세션 조회
        all_sessions = []

        # 모든 사용자 조회 (제한적으로)
        from .repositories.sqlite_user_repository import SQLiteUserRepository

        repository = SQLiteUserRepository(db)
        users = await repository.list_all(limit=100)

        # 각 사용자의 세션 조회
        for user in users:
            sessions = await auth_service.jwt_service.get_active_sessions(user.id)
            for session in sessions:
                session["user_email"] = user.email
                session["user_id"] = user.id
                session["username"] = user.username
                all_sessions.append(session)

        content = Div(
            H1("세션 관리", cls="text-3xl font-bold text-gray-900 mb-8"),
            # 통계 카드
            Div(
                # 총 활성 세션
                Div(
                    Div(
                        H3("활성 세션", cls="text-lg font-semibold text-gray-700"),
                        P(
                            str(len(all_sessions)),
                            cls="text-3xl font-bold text-blue-600",
                        ),
                        cls="p-6",
                    ),
                    cls="bg-white rounded-lg shadow-md",
                ),
                # 활성 사용자 수
                Div(
                    Div(
                        H3("활성 사용자", cls="text-lg font-semibold text-gray-700"),
                        P(
                            str(len(set(s["user_id"] for s in all_sessions))),
                            cls="text-3xl font-bold text-green-600",
                        ),
                        cls="p-6",
                    ),
                    cls="bg-white rounded-lg shadow-md",
                ),
                # 평균 세션 수
                Div(
                    Div(
                        H3(
                            "사용자당 평균 세션",
                            cls="text-lg font-semibold text-gray-700",
                        ),
                        P(
                            f"{len(all_sessions) / max(len(set(s['user_id'] for s in all_sessions)), 1):.1f}",
                            cls="text-3xl font-bold text-purple-600",
                        ),
                        cls="p-6",
                    ),
                    cls="bg-white rounded-lg shadow-md",
                ),
                cls="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8",
            ),
            # 사용자별 세션 검색 (HTMX 기반)
            Div(
                H2("사용자 세션 검색", cls="text-xl font-semibold text-gray-900 mb-4"),
                Form(
                    Div(
                        Input(
                            type="text",
                            name="query",
                            placeholder="사용자 ID 또는 이메일로 검색",
                            cls="flex-1 px-4 py-2 border border-gray-300 rounded-l-lg focus:outline-none focus:ring-2 focus:ring-blue-500",
                            **{
                                "hx-get": "/admin/sessions/search",
                                "hx-target": "#userSessionsResult",
                                "hx-trigger": "keyup changed delay:500ms, search",
                            }
                        ),
                        Button(
                            "검색",
                            type="submit",
                            cls="bg-blue-500 hover:bg-blue-600 text-white font-medium py-2 px-6 rounded-r-lg",
                        ),
                        cls="flex",
                    ),
                    **{
                        "hx-get": "/admin/sessions/search",
                        "hx-target": "#userSessionsResult",
                        "hx-trigger": "submit",
                    },
                    cls="mb-4",
                ),
                Div(
                    # 검색 결과가 여기에 로드됩니다
                    id="userSessionsResult", 
                    cls="mt-4"
                ),
                cls="bg-white rounded-lg shadow-md p-6 mb-8",
            ),
            # 전체 활성 세션 목록
            Div(
                H2("전체 활성 세션", cls="text-xl font-semibold text-gray-900 mb-4"),
                Div(
                    Table(
                        Thead(
                            Tr(
                                Th(
                                    "사용자",
                                    cls="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider",
                                ),
                                Th(
                                    "JTI",
                                    cls="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider",
                                ),
                                Th(
                                    "발급 시간",
                                    cls="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider",
                                ),
                                Th(
                                    "만료 시간",
                                    cls="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider",
                                ),
                                Th(
                                    "메타데이터",
                                    cls="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider",
                                ),
                                Th(
                                    "액션",
                                    cls="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider",
                                ),
                            )
                        ),
                        Tbody(
                            *[
                                Tr(
                                    Td(
                                        Div(
                                            P(
                                                session.get("user_email", "Unknown"),
                                                cls="text-sm font-medium text-gray-900",
                                            ),
                                            P(
                                                f"ID: {session.get('user_id', 'Unknown')}",
                                                cls="text-xs text-gray-500",
                                            ),
                                            cls="flex flex-col",
                                        ),
                                        cls="px-6 py-4 whitespace-nowrap",
                                    ),
                                    Td(
                                        session.get("jti", "-")[:8] + "...",
                                        cls="px-6 py-4 whitespace-nowrap text-sm text-gray-900 font-mono",
                                    ),
                                    Td(
                                        session.get("issued_at", "").replace("T", " ")[
                                            :19
                                        ]
                                        if session.get("issued_at")
                                        else "-",
                                        cls="px-6 py-4 whitespace-nowrap text-sm text-gray-500",
                                    ),
                                    Td(
                                        session.get("expires_at", "").replace("T", " ")[
                                            :19
                                        ]
                                        if session.get("expires_at")
                                        else "-",
                                        cls="px-6 py-4 whitespace-nowrap text-sm text-gray-500",
                                    ),
                                    Td(
                                        str(
                                            session.get("metadata", {}).get(
                                                "device_id", "-"
                                            )
                                        ),
                                        cls="px-6 py-4 whitespace-nowrap text-sm text-gray-500",
                                    ),
                                    Td(
                                        Button(
                                            "무효화",
                                            **{
                                                "hx-post": f"/admin/sessions/revoke/{session.get('jti', '')}",
                                                "hx-confirm": f"{session.get('user_email', '')}의 토큰을 무효화하시겠습니까?",
                                                "hx-target": "closest tr",
                                                "hx-swap": "outerHTML",
                                            },
                                            cls="bg-red-500 hover:bg-red-600 text-white font-medium py-1 px-3 rounded text-sm",
                                        ),
                                        cls="px-6 py-4 whitespace-nowrap",
                                    ),
                                )
                                for session in all_sessions[:50]
                            ]  # 최대 50개만 표시
                        ),
                        cls="min-w-full divide-y divide-gray-200",
                    ),
                    cls="overflow-x-auto",
                ),
                P(
                    f"총 {len(all_sessions)}개 중 최대 50개 표시",
                    cls="text-sm text-gray-500 mt-2",
                )
                if len(all_sessions) > 50
                else "",
                cls="bg-white rounded-lg shadow-md overflow-hidden",
            ),
        )

        return create_layout("세션 관리", content, current_user)

    except Exception as e:
        logger.error("관리자 세션 페이지 오류", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="세션 관리 페이지를 로드하는 중 오류가 발생했습니다",
        )

# === HTMX 엔드포인트: 세션 관리 기능들 ===

@app.get("/admin/sessions/search", response_class=HTMLResponse)
async def search_user_sessions_htmx(
    query: str,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    auth_service: Annotated[SQLiteAuthService, Depends(get_sqlite_auth_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """HTMX: 사용자 세션 검색"""
    try:
        if not query.strip():
            return HTMLResponse(
                content='<p class="text-red-500">검색어를 입력하세요.</p>'
            )

        # 사용자 검색
        from .repositories.sqlite_user_repository import SQLiteUserRepository
        repository = SQLiteUserRepository(db)
        
        # ID로 검색을 시도하고, 실패하면 이메일로 검색
        users = []
        try:
            if query.isdigit():
                user = await repository.get_by_id(int(query))
                if user:
                    users = [user]
        except:
            pass
        
        if not users:
            # 이메일로 검색
            all_users = await repository.list_all(limit=100)
            users = [u for u in all_users if query.lower() in u.email.lower()]

        if not users:
            return HTMLResponse(
                content='<p class="text-red-500">사용자를 찾을 수 없습니다.</p>'
            )

        user = users[0]
        
        # 사용자 세션 조회
        sessions = await auth_service.jwt_service.get_active_sessions(user.id)
        
        # 결과 HTML 생성
        content_parts = [
            f'<div class="border-t pt-4">',
            f'<h3 class="font-semibold text-lg mb-2">{user.email} ({user.username or "No username"})</h3>',
            f'<p class="text-sm text-gray-600 mb-4">활성 세션: {len(sessions)}개</p>'
        ]
        
        if sessions:
            content_parts.append('<div class="space-y-2">')
            for session in sessions:
                jti = session.get("jti", "")
                expires_at = session.get("expires_at", "")
                expires_display = expires_at.replace("T", " ")[:19] if expires_at else "-"
                
                content_parts.append(
                    f'<div class="bg-gray-50 p-3 rounded flex justify-between items-center">'
                    f'<div>'
                    f'<p class="text-sm font-mono">{jti[:12]}...</p>'
                    f'<p class="text-xs text-gray-500">만료: {expires_display}</p>'
                    f'</div>'
                    f'<button hx-post="/admin/sessions/revoke/{jti}" '
                    f'hx-confirm="정말로 이 토큰을 무효화하시겠습니까?" '
                    f'hx-target="#userSessionsResult" '
                    f'hx-vals=\'{{"user_email": "{user.email}"}}\' '
                    f'class="bg-red-500 hover:bg-red-600 text-white text-sm px-3 py-1 rounded">'
                    f'무효화'
                    f'</button>'
                    f'</div>'
                )
            
            content_parts.append('</div>')
            content_parts.append(
                f'<button hx-post="/admin/sessions/revoke-all/{user.id}" '
                f'hx-confirm="정말로 {user.email}의 모든 세션을 무효화하시겠습니까?\\n이 사용자는 모든 디바이스에서 로그아웃됩니다." '
                f'hx-target="#userSessionsResult" '
                f'hx-vals=\'{{"user_email": "{user.email}"}}\' '
                f'class="mt-4 bg-red-600 hover:bg-red-700 text-white font-medium px-4 py-2 rounded">'
                f'모든 세션 무효화'
                f'</button>'
            )
        else:
            content_parts.append('<p class="text-gray-500">활성 세션이 없습니다.</p>')
        
        content_parts.append('</div>')
        
        return HTMLResponse(content="".join(content_parts))
        
    except Exception as e:
        logger.error("사용자 세션 검색 오류", error=str(e))
        return HTMLResponse(
            content=f'<p class="text-red-500">오류가 발생했습니다: {str(e)}</p>'
        )


@app.post("/admin/sessions/revoke/{jti}", response_class=HTMLResponse)
async def revoke_session_htmx(
    jti: str,
    request: Request,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    auth_service: Annotated[SQLiteAuthService, Depends(get_sqlite_auth_service)],
):
    """HTMX: 개별 세션 무효화"""
    try:
        # 토큰 무효화
        result = await auth_service.jwt_service.revoke_token(jti)
        
        if result:
            # 성공 메시지와 함께 페이지 새로고침 트리거
            return HTMLResponse(
                content='<div class="text-green-600 p-3 bg-green-50 rounded mb-4">'
                '토큰이 무효화되었습니다.'
                '</div>'
                
                headers={"HX-Refresh": "true"}
            )
        else:
            return HTMLResponse(
                content='<div class="text-red-600 p-3 bg-red-50 rounded">'
                '토큰 무효화에 실패했습니다.'
                '</div>'
            )
    except Exception as e:
        logger.error("토큰 무효화 오류", error=str(e), jti=jti)
        return HTMLResponse(
            content=f'<div class="text-red-600 p-3 bg-red-50 rounded">'
            f'오류가 발생했습니다: {str(e)}'
            f'</div>'
        )


@app.post("/admin/sessions/revoke-all/{user_id}", response_class=HTMLResponse)
async def revoke_all_user_sessions_htmx(
    user_id: str,
    request: Request,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    auth_service: Annotated[SQLiteAuthService, Depends(get_sqlite_auth_service)],
):
    """HTMX: 사용자의 모든 세션 무효화"""
    try:
        # 사용자의 모든 토큰 무효화
        revoked_count = await auth_service.jwt_service.revoke_all_user_tokens(user_id)
        
        return HTMLResponse(
            content=f'<div class="text-green-600 p-3 bg-green-50 rounded mb-4">'
            f'{revoked_count}개의 토큰이 무효화되었습니다.'
            '</div>'
            
            headers={"HX-Refresh": "true"}
        )
        
    except Exception as e:
        logger.error("사용자 토큰 전체 무효화 오류", error=str(e), user_id=user_id)
        return HTMLResponse(
            content=f'<div class="text-red-600 p-3 bg-red-50 rounded">'
            f'오류가 발생했습니다: {str(e)}'
            f'</div>'
        )


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


# === Placeholder 기능 HTMX 엔드포인트 ===

@app.get("/admin/placeholder/add-user", response_class=HTMLResponse)
async def placeholder_add_user():
    """사용자 추가 기능 준비 중 알림"""
    return HTMLResponse(
        content='<div class="text-blue-600 p-3 bg-blue-50 rounded mb-4">'
        '사용자 추가 기능은 곧 구현될 예정입니다.'
        '</div>'
    )

@app.get("/admin/export/users.csv")
async def export_users_csv(
    current_user: Annotated[UserResponse, Depends(require_admin)],
    auth_service: Annotated[SQLiteAuthService, Depends(get_sqlite_auth_service)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """사용자 데이터를 CSV 형태로 내보내기"""
    try:
        logger.info("사용자 CSV 내보내기 시작", user_id=current_user.id)
        
        # 모든 사용자 데이터 조회
        users = await auth_service.list_users(db)
        
        # CSV 스트림 생성
        def generate_csv():
            output = io.StringIO()
            writer = csv.writer(output)
            
            # 헤더 작성
            writer.writerow(['ID', '사용자명', '이메일', '역할', '활성화', '생성일', '최종로그인'])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)
            
            # 데이터 행 작성
            for user in users:
                writer.writerow([
                    user.id,
                    user.username or '',
                    user.email,
                    ', '.join(user.roles) if user.roles else '',
                    '예' if user.is_active else '아니오',
                    user.created_at.strftime('%Y-%m-%d %H:%M:%S') if user.created_at else '',
                    user.last_login.strftime('%Y-%m-%d %H:%M:%S') if user.last_login else ''
                ])
                yield output.getvalue()
                output.seek(0)
                output.truncate(0)
        
        logger.info("사용자 CSV 내보내기 완료", user_count=len(users))
        
        return StreamingResponse(
            generate_csv(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=users.csv"}
        )
        
    except Exception as e:
        logger.error("사용자 CSV 내보내기 실패", error=str(e))
        raise HTTPException(status_code=500, detail="내보내기 중 오류가 발생했습니다")

@app.get("/admin/export/permissions.csv")
async def export_permissions_csv(
    current_user: Annotated[UserResponse, Depends(require_admin)],
    permission_service=Depends(get_permission_service)
):
    """권한 데이터를 CSV 형태로 내보내기"""
    try:
        logger.info("권한 CSV 내보내기 시작", user_id=current_user.id)
        
        # 모든 권한 데이터 조회
        permissions = await permission_service.list_permissions()
        
        # CSV 스트림 생성
        def generate_csv():
            output = io.StringIO()
            writer = csv.writer(output)
            
            # 헤더 작성
            writer.writerow(['ID', '사용자ID', '역할명', '리소스타입', '리소스명', '액션', '조건', '부여일', '만료일'])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)
            
            # 데이터 행 작성
            for permission in permissions:
                writer.writerow([
                    permission.id,
                    permission.user_id or '',
                    permission.role_name or '',
                    permission.resource_type,
                    permission.resource_name,
                    ', '.join(permission.actions) if permission.actions else '',
                    json.dumps(permission.conditions, ensure_ascii=False) if permission.conditions else '',
                    permission.granted_at.strftime('%Y-%m-%d %H:%M:%S') if permission.granted_at else '',
                    permission.expires_at.strftime('%Y-%m-%d %H:%M:%S') if permission.expires_at else ''
                ])
                yield output.getvalue()
                output.seek(0)
                output.truncate(0)
        
        logger.info("권한 CSV 내보내기 완료", permission_count=len(permissions))
        
        return StreamingResponse(
            generate_csv(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=permissions.csv"}
        )
        
    except Exception as e:
        logger.error("권한 CSV 내보내기 실패", error=str(e))
        raise HTTPException(status_code=500, detail="내보내기 중 오류가 발생했습니다")

@app.get("/admin/export/metrics.json")
async def export_metrics_json(
    current_user: Annotated[UserResponse, Depends(require_admin)]
):
    """시스템 메트릭을 JSON 형태로 내보내기"""
    try:
        logger.info("메트릭 JSON 내보내기 시작", user_id=current_user.id)
        
        # 기본 시스템 메트릭 생성 (향후 MetricsMiddleware 통합 예정)
        metrics_data = {
            "export_timestamp": datetime.now().isoformat(),
            "export_user": current_user.email,
            "system_metrics": {
                "total_requests": 0,
                "error_rate": 0.0,
                "avg_response_time_ms": 0.0
            },
            "tool_metrics": {
                "search_web": {"count": 0, "avg_duration_ms": 0},
                "search_vectors": {"count": 0, "avg_duration_ms": 0},
                "search_database": {"count": 0, "avg_duration_ms": 0},
                "health_check": {"count": 0, "avg_duration_ms": 0}
            },
            "user_metrics": {
                "active_users": 0,
                "total_sessions": 0,
                "avg_requests_per_user": 0.0
            },
            "note": "메트릭 수집 시스템 통합 예정"
        }
        
        # JSON 스트림 생성
        def generate_json():
            json_str = json.dumps(metrics_data, ensure_ascii=False, indent=2)
            yield json_str
        
        logger.info("메트릭 JSON 내보내기 완료")
        
        return StreamingResponse(
            generate_json(),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=metrics.json"}
        )
        
    except Exception as e:
        logger.error("메트릭 JSON 내보내기 실패", error=str(e))
        raise HTTPException(status_code=500, detail="내보내기 중 오류가 발생했습니다")

@app.get("/admin/analytics", response_class=HTMLResponse)
async def admin_analytics_page(
    current_user: Annotated[UserResponse, Depends(require_admin)]
):
    """사용 분석 대시보드"""
    try:
        logger.info("분석 페이지 로딩 시작", user_id=current_user.id)
        
        # Breadcrumb
        breadcrumb = AdminBreadcrumb([
            {"label": "관리자", "url": "/admin"},
            {"label": "사용 분석"}
        ])
        
        # 메트릭 데이터 조회 (현재는 Mock 데이터, 향후 실제 MetricsMiddleware 연동)
        metrics_data = await get_analytics_data()
        
        # Chart.js 데이터 생성
        chart_data = generate_chart_data(metrics_data)
        
        # 통계 카드들
        stats_cards = Div(
            StatsCard(
                title="총 요청 수",
                value=metrics_data["total_requests"],
                color="blue",
                icon="📊",
                trend={"value": "+12%", "positive": True}
            ),
            StatsCard(
                title="성공률",
                value=f"{metrics_data['success_rate']:.1f}%",
                color="green",
                icon="✅",
                trend={"value": "+2.3%", "positive": True}
            ),
            StatsCard(
                title="평균 응답시간",
                value=f"{metrics_data['avg_response_time']:.0f}ms",
                color="yellow",
                icon="⚡",
                trend={"value": "-15ms", "positive": True}
            ),
            StatsCard(
                title="활성 사용자",
                value=metrics_data["active_users"],
                color="purple",
                icon="👥",
                trend={"value": "+5", "positive": True}
            ),
            cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8"
        )
        
        # 차트 섹션
        charts_section = Div(
            # 도구 사용량 바차트와 시간별 활동 라인차트
            Div(
                AnalyticsChart(
                    chart_type="bar",
                    data=chart_data["tool_usage"],
                    canvas_id="tool-usage-chart",
                    title="도구별 사용량"
                ),
                AnalyticsChart(
                    chart_type="line",
                    data=chart_data["activity_timeline"],
                    canvas_id="activity-timeline-chart",
                    title="시간별 활동"
                ),
                cls="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6"
            ),
            
            # 응답시간 히스토그램과 사용자별 활동 도넛차트
            Div(
                AnalyticsChart(
                    chart_type="bar",
                    data=chart_data["response_time_histogram"],
                    canvas_id="response-time-chart",
                    title="응답시간 분포"
                ),
                AnalyticsChart(
                    chart_type="doughnut",
                    data=chart_data["user_activity"],
                    canvas_id="user-activity-chart",
                    title="사용자별 활동"
                ),
                cls="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8"
            ),
            
            # 차트 자동 업데이트를 위한 JavaScript
            Script("""
                // 차트 업데이트 함수
                async function updateCharts() {
                    try {
                        const response = await fetch('/admin/analytics/charts-data');
                        const chartData = await response.json();
                        
                        // 전역 chartInstances에서 차트 인스턴스 확인
                        if (typeof window.chartInstances !== 'undefined') {
                            // 각 차트 업데이트
                            Object.keys(chartData).forEach(chartKey => {
                                const canvasId = chartKey.replace(/[_]/g, '-') + '-chart';
                                const chart = window.chartInstances[canvasId];
                                if (chart) {
                                    chart.data = chartData[chartKey];
                                    chart.update('none'); // 애니메이션 없이 업데이트
                                }
                            });
                        }
                    } catch (error) {
                        console.error('차트 업데이트 실패:', error);
                    }
                }
                
                // 페이지 로드 후 차트 업데이트 함수 등록
                document.addEventListener('DOMContentLoaded', function() {
                    // 30초마다 차트 업데이트
                    setInterval(updateCharts, 30000);
                });
            """),
            cls="charts-container"
        )
        
        # 도구별 사용 통계 테이블
        tool_headers = ["도구명", "사용 횟수", "평균 응답시간", "성공률", "마지막 사용"]
        tool_rows = []
        for tool_name, stats in metrics_data["tool_stats"].items():
            tool_rows.append([
                tool_name,
                str(stats["count"]),
                f"{stats['avg_duration']:.0f}ms",
                f"{stats['success_rate']:.1f}%",
                stats["last_used"]
            ])
        
        tool_usage_table = AdminTable(
            headers=tool_headers,
            rows=tool_rows,
            table_id="tool-usage-table",
            empty_message="도구 사용 데이터가 없습니다."
        )
        
        # 필터 옵션
        filter_options = [
            {"name": "period", "label": "기간", "options": [
                {"value": "1h", "label": "최근 1시간"},
                {"value": "24h", "label": "최근 24시간"},
                {"value": "7d", "label": "최근 7일"},
                {"value": "30d", "label": "최근 30일"}
            ]},
            {"name": "tool", "label": "도구", "options": [
                {"value": "search_web", "label": "웹 검색"},
                {"value": "search_vectors", "label": "벡터 검색"},
                {"value": "search_database", "label": "데이터베이스 검색"},
                {"value": "health_check", "label": "헬스 체크"}
            ]}
        ]
        
        filter_bar = FilterBar(
            filters=filter_options,
            search_placeholder="사용자 검색...",
            htmx_target="#analytics-content",
            htmx_endpoint="/admin/analytics/data",
            container_id="analytics-filter"
        )
        
        # 메인 콘텐츠
        content = Div(
            breadcrumb,
            H1("사용 분석", cls="text-3xl font-bold text-gray-900 mb-8"),
            
            # 통계 카드
            stats_cards,
            
            # 차트 섹션
            charts_section,
            
            # 필터 및 도구 통계
            AdminCard(
                title="도구 사용 통계",
                content=Div(
                    filter_bar,
                    Div(
                        tool_usage_table,
                        id="analytics-content",
                        **{
                            "hx-get": "/admin/analytics/data",
                            "hx-trigger": "every 30s",
                            "hx-include": "#analytics-filter"
                        }
                    )
                ),
                color="white"
            ),
            
            # 시스템 정보
            AdminCard(
                title="시스템 정보",
                content=Div(
                    P(f"마지막 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", cls="text-sm text-gray-600"),
                    P("데이터 소스: MCP Server 메트릭 (향후 실시간 연동 예정)", cls="text-xs text-gray-500"),
                    cls="space-y-2"
                ),
                color="gray"
            ),
            
            cls="space-y-8"
        )
        
        logger.info("분석 페이지 로딩 완료", user_id=current_user.id)
        
        page = create_layout("사용 분석", content, current_user)
        html_content = to_xml(page)
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error("분석 페이지 로딩 실패", error=str(e))
        error_content = Div(
            H1("오류", cls="text-3xl font-bold text-red-600 mb-4"),
            P(f"분석 페이지를 로드하는 중 오류가 발생했습니다: {str(e)}", cls="text-gray-700"),
        )
        page = create_layout("오류", error_content, current_user)
        html_content = to_xml(page)
        return HTMLResponse(content=html_content, status_code=500)

@app.get("/admin/analytics/data", response_class=HTMLResponse)
async def admin_analytics_data(
    current_user: Annotated[UserResponse, Depends(require_admin)],
    period: Optional[str] = None,
    tool: Optional[str] = None,
    search: Optional[str] = None
):
    """분석 데이터 (HTMX 자동 새로고침용)"""
    try:
        logger.debug("분석 데이터 업데이트", user_id=current_user.id, period=period, tool=tool)
        
        # 필터링된 메트릭 데이터 조회
        metrics_data = await get_analytics_data(period=period, tool_filter=tool, search=search)
        
        # 도구별 사용 통계 테이블 재생성
        tool_headers = ["도구명", "사용 횟수", "평균 응답시간", "성공률", "마지막 사용"]
        tool_rows = []
        for tool_name, stats in metrics_data["tool_stats"].items():
            tool_rows.append([
                tool_name,
                str(stats["count"]),
                f"{stats['avg_duration']:.0f}ms",
                f"{stats['success_rate']:.1f}%",
                stats["last_used"]
            ])
        
        table = AdminTable(
            headers=tool_headers,
            rows=tool_rows,
            table_id="tool-usage-table",
            empty_message="필터 조건에 맞는 데이터가 없습니다."
        )
        
        return HTMLResponse(content=to_xml(table))
        
    except Exception as e:
        logger.error("분석 데이터 업데이트 실패", error=str(e))
        return HTMLResponse(
            content='<div class="text-red-600 p-3 bg-red-50 rounded">데이터 업데이트 중 오류가 발생했습니다.</div>'
        )

@app.get("/admin/analytics/charts-data")
async def admin_analytics_charts_data(
    current_user: Annotated[UserResponse, Depends(require_admin)],
    period: Optional[str] = None,
    tool: Optional[str] = None
):
    """차트 데이터 JSON 제공 (HTMX + JavaScript 차트 업데이트용)"""
    try:
        logger.debug("차트 데이터 업데이트", user_id=current_user.id, period=period, tool=tool)
        
        # 필터링된 메트릭 데이터 조회
        metrics_data = await get_analytics_data(period=period, tool_filter=tool)
        
        # Chart.js 데이터 생성
        chart_data = generate_chart_data(metrics_data)
        
        return JSONResponse(content=chart_data)
        
    except Exception as e:
        logger.error("차트 데이터 업데이트 실패", error=str(e))
        return JSONResponse(
            content={"error": "차트 데이터 업데이트 중 오류가 발생했습니다."},
            status_code=500
        )

async def get_analytics_data(
    period: Optional[str] = None,
    tool_filter: Optional[str] = None,
    search: Optional[str] = None
) -> Dict[str, Any]:
    """분석 데이터 조회 (현재는 Mock 데이터, 향후 실제 메트릭 연동)"""
    
    # TODO: 실제 MetricsMiddleware 데이터 연동
    # 현재는 Mock 데이터로 기본 구조 구현
    
    base_data = {
        "total_requests": 1247,
        "success_rate": 97.8,
        "avg_response_time": 156.3,
        "active_users": 12,
        "tool_stats": {
            "search_web": {
                "count": 456,
                "avg_duration": 234.5,
                "success_rate": 98.2,
                "last_used": "2분 전"
            },
            "search_vectors": {
                "count": 234,
                "avg_duration": 189.3,
                "success_rate": 96.5,
                "last_used": "5분 전"
            },
            "search_database": {
                "count": 345,
                "avg_duration": 78.9,
                "success_rate": 99.1,
                "last_used": "1분 전"
            },
            "health_check": {
                "count": 212,
                "avg_duration": 12.1,
                "success_rate": 100.0,
                "last_used": "30초 전"
            }
        }
    }
    
    # 필터 적용 시뮬레이션
    if tool_filter:
        filtered_stats = {k: v for k, v in base_data["tool_stats"].items() if k == tool_filter}
        base_data["tool_stats"] = filtered_stats
    
    if search:
        # 사용자 검색 시뮬레이션 (실제로는 사용자별 메트릭 필터링)
        pass
    
    return base_data

def generate_chart_data(metrics_data: Dict[str, Any]) -> Dict[str, Any]:
    """메트릭 데이터를 Chart.js 형식으로 변환"""
    
    # 도구별 사용량 바차트 데이터
    tool_names = list(metrics_data["tool_stats"].keys())
    tool_counts = [stats["count"] for stats in metrics_data["tool_stats"].values()]
    
    tool_usage_data = {
        "labels": [name.replace("search_", "").replace("_", " ").title() for name in tool_names],
        "datasets": [{
            "label": "사용 횟수",
            "data": tool_counts,
            "backgroundColor": [
                "rgba(59, 130, 246, 0.8)",    # Blue
                "rgba(16, 185, 129, 0.8)",    # Green  
                "rgba(245, 158, 11, 0.8)",    # Yellow
                "rgba(139, 92, 246, 0.8)"     # Purple
            ],
            "borderColor": [
                "rgb(59, 130, 246)",
                "rgb(16, 185, 129)",
                "rgb(245, 158, 11)",
                "rgb(139, 92, 246)"
            ],
            "borderWidth": 1
        }]
    }
    
    # 시간별 활동 라인차트 데이터 (Mock 시간 데이터)
    activity_timeline_data = {
        "labels": ["06:00", "09:00", "12:00", "15:00", "18:00", "21:00"],
        "datasets": [{
            "label": "요청 수",
            "data": [45, 120, 89, 156, 203, 78],
            "borderColor": "rgb(59, 130, 246)",
            "backgroundColor": "rgba(59, 130, 246, 0.1)",
            "tension": 0.4,
            "fill": True
        }]
    }
    
    # 응답시간 히스토그램 데이터
    response_time_data = {
        "labels": ["0-50ms", "50-100ms", "100-200ms", "200-500ms", "500ms+"],
        "datasets": [{
            "label": "요청 수",
            "data": [234, 456, 189, 67, 12],
            "backgroundColor": "rgba(16, 185, 129, 0.8)",
            "borderColor": "rgb(16, 185, 129)",
            "borderWidth": 1
        }]
    }
    
    # 사용자별 활동 도넛차트 데이터
    user_activity_data = {
        "labels": ["Admin", "일반 사용자", "분석가", "게스트"],
        "datasets": [{
            "label": "활동량",
            "data": [35, 45, 15, 5],
            "backgroundColor": [
                "rgba(239, 68, 68, 0.8)",     # Red
                "rgba(59, 130, 246, 0.8)",    # Blue
                "rgba(245, 158, 11, 0.8)",    # Yellow
                "rgba(107, 114, 128, 0.8)"    # Gray
            ],
            "borderColor": [
                "rgb(239, 68, 68)",
                "rgb(59, 130, 246)",
                "rgb(245, 158, 11)", 
                "rgb(107, 114, 128)"
            ],
            "borderWidth": 2
        }]
    }
    
    return {
        "tool_usage": tool_usage_data,
        "activity_timeline": activity_timeline_data,
        "response_time_histogram": response_time_data,
        "user_activity": user_activity_data
    }

@app.get("/admin/empty", response_class=HTMLResponse)
async def empty_response():
    """빈 응답을 반환하는 엔드포인트 (모달 닫기 등에 사용)"""
    return HTMLResponse(content="")

# === 로그인 페이지 테스트 엔드포인트 ===

@app.get("/auth/test-me", response_class=HTMLResponse)
async def test_auth_me_htmx(request: Request):
    """HTMX: 현재 사용자 정보 조회 테스트"""
    try:
        # Authorization 헤더에서 토큰 추출
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return HTMLResponse(
                content='<p class="error">먼저 로그인하세요.</p>'
            )
        
        token = auth_header[7:]  # "Bearer " 제거
        
        # /auth/me API 호출
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{request.base_url}auth/me",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if response.status_code == 200:
                user_data = response.json()
                formatted_data = f"<pre>{user_data}</pre>".replace('"', '&quot;')
                return HTMLResponse(
                    content=f'<p class="success">사용자 정보: {formatted_data}</p>'
                )
            else:
                return HTMLResponse(
                    content='<p class="error">인증 실패: 토큰이 유효하지 않습니다.</p>'
                )
                
    except Exception as e:
        return HTMLResponse(
            content=f'<p class="error">네트워크 오류가 발생했습니다: {str(e)}</p>'
        )

# === 권한 삭제 HTMX 엔드포인트 ===

@app.delete("/admin/permissions/delete/{permission_id}", response_class=HTMLResponse)
async def delete_permission_htmx(
    permission_id: str,
    request: Request,
    current_user: Annotated[UserResponse, Depends(require_admin)],
):
    """HTMX: 권한 삭제"""
    try:
        # Authorization 헤더에서 토큰 추출
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return HTMLResponse(
                content='<div class="text-red-600 p-3 bg-red-50 rounded">인증이 필요합니다.</div>'
            )
        
        token = auth_header[7:]  # "Bearer " 제거
        
        # API 호출을 통한 권한 삭제
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{request.base_url}api/v1/permissions/resources/{permission_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if response.status_code == 200:
                return HTMLResponse(
                    content='<div class="text-green-600 p-3 bg-green-50 rounded">권한이 삭제되었습니다.</div>',
                    headers={"HX-Refresh": "true"}  # 페이지 새로고침
                )
            else:
                return HTMLResponse(
                    content='<div class="text-red-600 p-3 bg-red-50 rounded">권한 삭제 중 오류가 발생했습니다.</div>'
                )
                
    except Exception as e:
        logger.error("권한 삭제 오류", error=str(e), permission_id=permission_id)
        return HTMLResponse(
            content=f'<div class="text-red-600 p-3 bg-red-50 rounded">오류가 발생했습니다: {str(e)}</div>'
        )

def create_layout(title: str, content, current_user=None, request: Optional[Request] = None):
    """공통 레이아웃 템플릿 (다국어 지원)"""
    # 현재 언어 설정 가져오기
    current_lang = get_user_language(request) if request else 'ko'
    
    # FastHTML에서는 to_xml()을 직접 호출하지 않고 객체를 반환
    # FastAPI HTMLResponse와 함께 사용시 자동으로 변환됨
    return Html(
        Head(
            Title(f"{title} - MCP Auth Gateway"),
            Meta(charset="utf-8"),
            Meta(name="viewport", content="width=device-width, initial-scale=1"),
            # Tailwind CSS CDN
            Link(
                rel="stylesheet",
                href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css",
            ),
            # HTMX for interactivity (Alpine.js removed - using HTMX for all interactions)
            Script(src="https://unpkg.com/htmx.org@1.9.12"),
            # Chart.js for analytics charts
            Script(src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.min.js"),
            # HTMX SSE 확장
            Script(src="https://unpkg.com/htmx.org@1.9.12/dist/ext/sse.js"),
            
            # SSE 이벤트 처리 스크립트
            Script("""
                document.addEventListener('DOMContentLoaded', function() {
                    const sseConnection = document.getElementById('sse-connection');
                    const notificationArea = document.getElementById('notification-area');
                    
                    if (sseConnection) {
                        // SSE 메시지 수신 이벤트
                        document.body.addEventListener('htmx:sseMessage', function(event) {
                            try {
                                const data = JSON.parse(event.detail.data);
                                
                                // heartbeat 이벤트는 무시
                                if (data.type === 'heartbeat') {
                                    return;
                                }
                                
                                // 알림 생성
                                const notification = createNotification(data);
                                notificationArea.appendChild(notification);
                                
                                // 5초 후 자동 제거
                                setTimeout(() => {
                                    if (notification && notification.parentNode) {
                                        notification.style.opacity = '0';
                                        setTimeout(() => {
                                            notification.remove();
                                        }, 300);
                                    }
                                }, 5000);
                                
                            } catch (e) {
                                console.error('SSE 메시지 파싱 오류:', e);
                            }
                        });
                        
                        // SSE 연결 오류 처리
                        document.body.addEventListener('htmx:sseError', function(event) {
                            console.error('SSE 연결 오류:', event.detail);
                        });
                    }
                    
                    function createNotification(data) {
                        const notification = document.createElement('div');
                        const typeConfig = {
                            'success': {
                                bg: 'bg-green-50',
                                border: 'border-green-200',
                                text: 'text-green-800',
                                icon: '✅'
                            },
                            'warning': {
                                bg: 'bg-yellow-50',
                                border: 'border-yellow-200',
                                text: 'text-yellow-800',
                                icon: '⚠️'
                            },
                            'error': {
                                bg: 'bg-red-50',
                                border: 'border-red-200',
                                text: 'text-red-800',
                                icon: '❌'
                            },
                            'info': {
                                bg: 'bg-blue-50',
                                border: 'border-blue-200',
                                text: 'text-blue-800',
                                icon: 'ℹ️'
                            }
                        };
                        
                        const config = typeConfig[data.type] || typeConfig['info'];
                        
                        notification.className = `p-4 mb-2 ${config.bg} ${config.border} border rounded-lg shadow-lg transition-opacity duration-300`;
                        notification.innerHTML = `
                            <div class="flex items-start justify-between">
                                <div class="flex items-start">
                                    <span class="text-lg mr-2">${config.icon}</span>
                                    <div>
                                        ${data.title ? `<div class="font-semibold ${config.text} mb-1">${data.title}</div>` : ''}
                                        <div class="${config.text}">${data.message}</div>
                                        <div class="text-xs text-gray-500 mt-1">${new Date(data.timestamp).toLocaleTimeString()}</div>
                                    </div>
                                </div>
                                <button onclick="this.parentElement.parentElement.remove()" class="ml-2 ${config.text} hover:opacity-70">
                                    ×
                                </button>
                            </div>
                        `;
                        
                        return notification;
                    }
                });
            """)
        ),
        Body(
            # SSE 연결 설정 (관리자인 경우에만)
            Div(
                id="sse-connection",
                **{
                    "hx-ext": "sse",
                    "sse-connect": "/admin/events",
                    "sse-swap": "message",
                    "hx-target": "#notification-area",
                    "style": "display: none;"
                } if request and current_user else {}
            ),
            
            # 실시간 알림 표시 영역
            Div(id="notification-area", cls="fixed top-20 right-4 z-50 space-y-2 max-w-md"),
            
            # Navigation
            Nav(
                Div(
                    Div(
                        H1("MCP Auth Gateway", cls="text-xl font-bold text-white"),
                        # 언어 선택기 추가
                        LanguageSelector(
                            current_language=current_lang,
                            endpoint="/admin/change-language",
                            target="body",
                            size="sm"
                        ) if request else "",
                        cls="container mx-auto px-4 py-3 flex justify-between items-center",
                    ),
                    cls="bg-blue-600",
                ),
                Div(
                    Div(
                        A(
                            T("nav_dashboard", request),
                            href="/admin",
                            cls="px-3 py-2 text-sm font-medium text-gray-700 hover:text-blue-600",
                        ),
                        A(
                            T("nav_users", request),
                            href="/admin/users",
                            cls="px-3 py-2 text-sm font-medium text-gray-700 hover:text-blue-600",
                        ),
                        A(
                            T("nav_sessions", request),
                            href="/admin/sessions",
                            cls="px-3 py-2 text-sm font-medium text-gray-700 hover:text-blue-600",
                        ),
                        A(
                            T("nav_analytics", request),
                            href="/admin/analytics",
                            cls="px-3 py-2 text-sm font-medium text-gray-700 hover:text-blue-600",
                        ),
                        A(
                            T("nav_permissions", request),
                            href="/admin/permissions",
                            cls="px-3 py-2 text-sm font-medium text-gray-700 hover:text-blue-600",
                        ),
                        A(
                            T("nav_roles", request),
                            href="/admin/roles",
                            cls="px-3 py-2 text-sm font-medium text-gray-700 hover:text-blue-600",
                        ),
                        cls="container mx-auto px-4 flex space-x-4",
                    ),
                    cls="bg-gray-100 border-b",
                ),
            ),
            # Main content
            Main(Div(content, cls="container mx-auto px-4 py-8")),
            cls="min-h-screen bg-gray-50",
        ),
    )


@app.post("/admin/change-language", response_class=HTMLResponse)
async def change_language(
    request: Request,
    language: str = Form(),
    current_user: Annotated[UserResponse, Depends(require_admin)] = None
):
    """언어 설정 변경"""
    try:
        # 지원되는 언어인지 확인
        if language not in SUPPORTED_LANGUAGES:
            raise HTTPException(
                status_code=400, 
                detail=f"지원되지 않는 언어입니다: {language}"
            )
        
        # 세션에 언어 설정 저장
        if hasattr(request, 'session'):
            request.session['language'] = language
        
        # 현재 페이지로 리다이렉트 (Referer 헤더 사용)
        referer = request.headers.get('referer', '/admin')
        
        # 성공 메시지와 함께 현재 페이지 새로고침
        return Response(
            content="",
            status_code=200,
            headers={
                "HX-Redirect": referer,
                "HX-Trigger": f"languageChanged:{language}"
            }
        )
        
    except Exception as e:
        logger.error(f"언어 변경 실패: {str(e)}")
        return HTMLResponse(
            content=f'<div class="text-red-600 p-3 bg-red-50 rounded mb-4">'
                   f'{T("operation_failed", request)}: {str(e)}</div>',
            status_code=500
        )


@app.get("/admin/events")
async def stream_admin_events(
    request: Request,
    current_user: Annotated[UserResponse, Depends(require_admin)]
):
    """관리자용 SSE 이벤트 스트림"""
    
    async def event_generator() -> AsyncGenerator[str, None]:
        connection_id = id(request)
        active_connections.add(connection_id)
        
        try:
            logger.info(f"SSE 연결 시작: {current_user.email} (연결 ID: {connection_id})")
            
            # 연결 확인 메시지
            initial_event = {
                "type": "success",
                "message": "실시간 알림이 활성화되었습니다.",
                "title": "연결 성공",
                "timestamp": datetime.utcnow().isoformat()
            }
            yield f"data: {json.dumps(initial_event)}\n\n"
            
            # 기존 이벤트 전송 (최근 5개)
            recent_events = list(event_queue)[-5:] if event_queue else []
            for event in recent_events:
                yield f"data: {json.dumps(event)}\n\n"
            
            last_event_count = len(event_queue)
            
            # 실시간 이벤트 스트림
            while True:
                # 새 이벤트 확인
                current_event_count = len(event_queue)
                if current_event_count > last_event_count:
                    # 새 이벤트들 전송
                    new_events = list(event_queue)[last_event_count:]
                    for event in new_events:
                        yield f"data: {json.dumps(event)}\n\n"
                    last_event_count = current_event_count
                
                # 연결 유지를 위한 heartbeat (30초마다)
                heartbeat = {
                    "type": "heartbeat",
                    "timestamp": datetime.utcnow().isoformat(),
                    "active_connections": len(active_connections)
                }
                yield f"data: {json.dumps(heartbeat)}\n\n"
                
                # 5초 대기
                await asyncio.sleep(5)
                
        except asyncio.CancelledError:
            logger.info(f"SSE 연결 종료: {current_user.email}")
        except Exception as e:
            logger.error(f"SSE 연결 오류: {str(e)}")
        finally:
            active_connections.discard(connection_id)
    
    return EventSourceResponse(event_generator())


@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
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

        # AdminBreadcrumb 사용 (번역 적용)
        breadcrumb = AdminBreadcrumb([
            {"label": T("admin", request), "url": "/admin"},
            {"label": T("dashboard", request)}
        ])

        # StatsCard들 생성 (번역 적용)
        stats_cards = Div(
            StatsCard(
                title=T("total_users", request),
                value=stats.get("total_users", 0),
                color="blue",
                icon="👥",
                subtitle=T("total_users", request)
            ),
            StatsCard(
                title=T("active_users", request), 
                value=stats.get("active_users", 0),
                color="green",
                icon="✅",
                subtitle=T("active_users", request),
                trend={"value": "+12%", "positive": True} if stats.get("active_users", 0) > 0 else None
            ),
            StatsCard(
                title=T("admin_users", request),
                value=stats.get("admin_users", 0),
                color="purple", 
                icon="👑",
                subtitle=T("admin_users", request)
            ),
            StatsCard(
                title=T("new_users_today", request),
                value=stats.get("today_registrations", 0),
                color="yellow",
                icon="📈",
                subtitle=T("new_users_today", request),
                trend={"value": "+3", "positive": True} if stats.get("today_registrations", 0) > 0 else None
            ),
            cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8"
        )

        # 빠른 액션 버튼들 (번역 적용)
        quick_actions = [
            A(
                f"👥 {T('nav_users', request)}",
                href="/admin/users",
                cls="inline-block bg-blue-500 hover:bg-blue-600 text-white font-medium py-3 px-6 rounded-lg mr-4 mb-2 transition-colors"
            ),
            A(
                f"🔒 {T('nav_permissions', request)}", 
                href="/admin/permissions",
                cls="inline-block bg-green-500 hover:bg-green-600 text-white font-medium py-3 px-6 rounded-lg mr-4 mb-2 transition-colors"
            ),
            A(
                f"⚡ {T('nav_roles', request)}",
                href="/admin/roles", 
                cls="inline-block bg-purple-500 hover:bg-purple-600 text-white font-medium py-3 px-6 rounded-lg mr-4 mb-2 transition-colors"
            ),
            A(
                f"🔐 {T('nav_sessions', request)}",
                href="/admin/sessions",
                cls="inline-block bg-orange-500 hover:bg-orange-600 text-white font-medium py-3 px-6 rounded-lg mr-4 mb-2 transition-colors"
            ),
            A(
                "📚 API 문서",
                href="/docs",
                cls="inline-block bg-gray-500 hover:bg-gray-600 text-white font-medium py-3 px-6 rounded-lg mr-4 mb-2 transition-colors"
            ),
            A(
                "📊 메트릭 내보내기",
                href="/admin/export/metrics.json",
                cls="inline-block bg-indigo-500 hover:bg-indigo-600 text-white font-medium py-3 px-6 rounded-lg mr-4 mb-2 transition-colors",
                download="metrics.json"
            ),
            A(
                "📈 사용 분석",
                href="/admin/analytics",
                cls="inline-block bg-cyan-500 hover:bg-cyan-600 text-white font-medium py-3 px-6 rounded-lg mr-4 mb-2 transition-colors"
            )
        ]

        # AdminCard로 빠른 액션 섹션 생성
        quick_actions_card = AdminCard(
            title="빠른 액션",
            content=Div(*quick_actions, cls="flex flex-wrap"),
            color="white"
        )

        # 최근 활동 카드 (추가)
        recent_activity_card = AdminCard(
            title="최근 활동",
            content=Div(
                P("• 새로운 사용자 3명이 가입했습니다", cls="text-sm text-gray-600 mb-2"),
                P("• 권한 설정이 2건 변경되었습니다", cls="text-sm text-gray-600 mb-2"),
                P("• 시스템 상태: 정상", cls="text-sm text-green-600 font-medium")
            ),
            color="gray"
        )

        content = Div(
            breadcrumb,
            H1("관리자 대시보드", cls="text-3xl font-bold text-gray-900 mb-8"),
            
            # 통계 카드들
            stats_cards,
            
            # 카드 섹션들
            Div(
                quick_actions_card,
                recent_activity_card,
                cls="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8"
            ),
            
            # 시스템 정보 카드
            AdminCard(
                title="시스템 정보",
                content=Div(
                    Div(
                        Strong("서버 상태: "), 
                        Span("🟢 정상", cls="text-green-600 font-medium"),
                        cls="mb-2"
                    ),
                    Div(
                        Strong("데이터베이스: "),
                        Span("🟢 연결됨", cls="text-green-600 font-medium"), 
                        cls="mb-2"
                    ),
                    Div(
                        Strong("캐시: "),
                        Span("🟢 작동 중", cls="text-green-600 font-medium"),
                        cls="mb-2"
                    ),
                    Div(
                        Strong("마지막 백업: "),
                        Span("2시간 전", cls="text-gray-600"),
                        cls="mb-2"
                    )
                ),
                color="blue"
            )
        )

        page = create_layout(T("dashboard", request), content, current_user, request)
        html_content = to_xml(page)
        return HTMLResponse(content=html_content)

    except Exception as e:
        logger.error("대시보드 로딩 실패", error=str(e))
        error_content = Div(
            H1("오류", cls="text-3xl font-bold text-red-600 mb-4"),
            P(
                f"대시보드를 로드하는 중 오류가 발생했습니다: {str(e)}",
                cls="text-gray-700",
            ),
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

        # Breadcrumb 생성
        breadcrumb = AdminBreadcrumb([
            {"label": "관리자", "url": "/admin"},
            {"label": "사용자 관리"}
        ])

        # AdminTable을 위한 헤더와 데이터 준비
        headers = ["ID", "이메일", "사용자명", "역할", "상태", "가입일"]
        
        # 테이블 행 데이터 생성
        table_rows = []
        for user in users:
            # 상태 뱃지
            status_badge = Span(
                "활성" if user.is_active else "비활성",
                cls=f"px-2 inline-flex text-xs leading-5 font-semibold rounded-full {'bg-green-100 text-green-800' if user.is_active else 'bg-red-100 text-red-800'}"
            )
            
            # 액션 버튼들
            action_buttons = Div(
                Button(
                    "권한 보기",
                    **{"hx-get": f"/admin/users/{user.id}/permissions", "hx-target": "body", "hx-push-url": "true"},
                    cls="text-blue-600 hover:text-blue-900 text-sm font-medium mr-2"
                ),
                Button(
                    "역할 변경",
                    cls="text-green-600 hover:text-green-900 text-sm font-medium",
                    **{
                        "hx-get": f"/admin/users/{user.id}/modal/roles",
                        "hx-target": "#modalContainer",
                        "hx-swap": "innerHTML"
                    }
                ),
                cls="flex space-x-2"
            )
            
            # 행 데이터 구성
            row_data = [
                str(user.id),
                user.email,
                user.username or "-",
                Span(
                    ", ".join(user.roles),
                    id=f"userRoles_{user.id}"
                ),
                status_badge,
                user.created_at.strftime("%Y-%m-%d"),
                action_buttons
            ]
            
            table_rows.append(row_data)

        # AdminTable 컴포넌트 사용
        users_table = AdminTable(
            headers=headers,
            rows=table_rows,
            table_id="users-table",
            empty_message="등록된 사용자가 없습니다.",
            css_classes="users-admin-table"
        )

        # 테이블 컨테이너 (HTMX 업데이트를 위한 래퍼)
        table_container = Div(
            users_table,
            id="users-table-container",
            cls="bg-white shadow overflow-hidden sm:rounded-lg"
        )

        # 사용자 통계 카드들
        total_users = len(users)
        active_users = len([u for u in users if u.is_active])
        admin_users = len([u for u in users if "admin" in u.roles])
        
        stats_section = Div(
            StatsCard(
                title="총 사용자",
                value=total_users,
                color="blue",
                icon="👥"
            ),
            StatsCard(
                title="활성 사용자",
                value=active_users,
                color="green",
                icon="✅"
            ),
            StatsCard(
                title="관리자",
                value=admin_users,
                color="purple",
                icon="👑"
            ),
            cls="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8"
        )

        # 필터/검색 바 (향후 확장용)
        filter_section = FilterBar(
            filters=[
                {
                    "name": "role_filter",
                    "label": "역할별 필터",
                    "options": [
                        {"value": "admin", "label": "관리자"},
                        {"value": "user", "label": "일반 사용자"},
                        {"value": "guest", "label": "게스트"}
                    ]
                },
                {
                    "name": "status_filter", 
                    "label": "상태별 필터",
                    "options": [
                        {"value": "active", "label": "활성"},
                        {"value": "inactive", "label": "비활성"}
                    ]
                }
            ],
            search_placeholder="이메일 또는 사용자명으로 검색...",
            htmx_target="#users-table-container",
            htmx_endpoint="/admin/users/filter",
            container_id="users-filter-bar"
        )

        content = Div(
            # Notification area for HTMX messages
            Div(id="notification-area", cls="mb-4"),
            
            breadcrumb,
            H1("사용자 관리", cls="text-3xl font-bold text-gray-900 mb-8"),
            
            # 통계 섹션
            stats_section,
            
            # 사용자 관리 카드
            AdminCard(
                title="사용자 목록",
                content=Div(
                    # 필터/검색 섹션 (접을 수 있음)
                    Details(
                        Summary(
                            "필터 및 검색",
                            cls="cursor-pointer text-blue-600 hover:text-blue-800 font-medium mb-4"
                        ),
                        filter_section,
                        cls="mb-6"
                    ),
                    
                    # 사용자 테이블
                    table_container
                ),
                actions=[
                    Button(
                        "+ 새 사용자 추가",
                        cls="bg-green-500 hover:bg-green-600 text-white font-medium py-2 px-4 rounded-lg",
                        **{"hx-get": "/admin/placeholder/add-user", "hx-target": "#notification-area", "hx-swap": "afterbegin"}
                    ),
                    A(
                        "📊 사용자 내보내기",
                        href="/admin/export/users.csv",
                        cls="bg-blue-500 hover:bg-blue-600 text-white font-medium py-2 px-4 rounded-lg inline-block text-center",
                        download="users.csv"
                    )
                ]
            ),
            
            # 모달 컨테이너
            Div(id="modalContainer"),
            
        )

        page = create_layout("사용자 관리", content, current_user)
        html_content = to_xml(page)
        return HTMLResponse(content=html_content)

    except Exception as e:
        logger.error("사용자 관리 페이지 로딩 실패", error=str(e))
        error_content = Div(
            H1("오류", cls="text-3xl font-bold text-red-600 mb-4"),
            P(
                f"사용자 관리 페이지를 로드하는 중 오류가 발생했습니다: {str(e)}",
                cls="text-gray-700",
            ),
        )
        page = create_layout("오류", error_content, current_user)
        html_content = to_xml(page)
        return HTMLResponse(content=html_content)


@app.get("/admin/users/{user_id}/modal/roles", response_class=HTMLResponse)
async def get_role_change_modal(
    user_id: str,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    auth_service: Annotated[SQLiteAuthService, Depends(get_sqlite_auth_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """사용자 역할 변경 모달 콘텐츠 반환"""
    try:
        # 사용자 조회
        from .repositories.sqlite_user_repository import SQLiteUserRepository
        
        repository = SQLiteUserRepository(db)
        user = await repository.get_by_id(user_id)
        
        if not user:
            return HTMLResponse(
                content=f'<div class="text-red-600">사용자를 찾을 수 없습니다: {user_id}</div>',
                status_code=404
            )
        
        # 사용 가능한 역할 목록
        available_roles = ["admin", "user", "guest", "viewer", "analyst"]
        current_roles = user.roles
        
        # 모달 콘텐츠 생성
        modal_content = Div(
            # 모달 배경
            Div(
                id="roleModalOverlay",
                cls="fixed inset-0 bg-gray-600 bg-opacity-50 z-40",
                **{"hx-get": "/admin/users/modal/close", "hx-trigger": "click", "hx-target": "#roleChangeModal", "hx-swap": "outerHTML"}
            ),
            # 모달 콘텐츠
            Div(
                Div(
                    # 모달 헤더
                    Div(
                        H3(
                            f"사용자 역할 변경: {user.email}",
                            cls="text-lg font-medium text-gray-900"
                        ),
                        Button(
                            "×",
                            cls="text-gray-400 hover:text-gray-600 text-xl font-bold",
                            **{"hx-get": "/admin/users/modal/close", "hx-target": "#roleChangeModal", "hx-swap": "outerHTML"}
                        ),
                        cls="flex justify-between items-center pb-3 border-b border-gray-200"
                    ),
                    
                    # 모달 본문
                    Form(
                        Div(
                            P(
                                "이 사용자에게 부여할 역할을 선택하세요:",
                                cls="text-sm text-gray-600 mb-4"
                            ),
                            # 역할 선택 체크박스
                            *[
                                Div(
                                    Label(
                                        Input(
                                            type="checkbox",
                                            name="roles",
                                            value=role,
                                            checked=role in current_roles,
                                            cls="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                                        ),
                                        Span(
                                            role.capitalize(),
                                            cls="ml-2 text-sm text-gray-900"
                                        ),
                                        cls="flex items-center"
                                    ),
                                    cls="mb-2"
                                )
                                for role in available_roles
                            ],
                            cls="space-y-2"
                        ),
                        Input(type="hidden", name="user_id", value=user_id),
                        cls="py-4"
                    ),
                    
                    # 모달 푸터
                    Div(
                        Button(
                            "취소",
                            type="button",
                            cls="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 mr-3",
                            **{"hx-get": "/admin/users/modal/close", "hx-target": "#roleChangeModal", "hx-swap": "outerHTML"}
                        ),
                        Button(
                            "저장",
                            type="submit",
                            cls="px-4 py-2 text-sm font-medium text-white bg-blue-600 border border-transparent rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500",
                            **{
                                "hx-put": f"/admin/users/{user_id}/roles/update",
                                "hx-include": "closest form",
                                "hx-target": "#roleChangeModal",
                                "hx-swap": "outerHTML"
                            }
                        ),
                        cls="flex justify-end pt-3 border-t border-gray-200"
                    ),
                    cls="bg-white rounded-lg p-6 max-w-md w-full mx-4"
                ),
                cls="fixed inset-0 z-50 flex items-center justify-center"
            ),
            id="roleChangeModal",
            cls="fixed inset-0 z-40"
        )
        
        return HTMLResponse(content=to_xml(modal_content))
        
    except Exception as e:
        logger.error("역할 변경 모달 로딩 실패", error=str(e), user_id=user_id)
        error_content = Div(
            f"모달을 로드하는 중 오류가 발생했습니다: {str(e)}",
            cls="text-red-600 p-4"
        )
        return HTMLResponse(content=to_xml(error_content), status_code=500)


@app.get("/admin/users/modal/close", response_class=HTMLResponse)
async def close_role_modal():
    """역할 변경 모달 닫기"""
    return HTMLResponse(content="")


@app.put("/admin/users/{user_id}/roles/update", response_class=HTMLResponse)
async def update_user_roles_htmx(
    user_id: str,
    request: Request,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    auth_service: Annotated[SQLiteAuthService, Depends(get_sqlite_auth_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """HTMX용 사용자 역할 업데이트"""
    try:
        # 폼 데이터 파싱
        form = await request.form()
        roles = form.getlist("roles")  # 체크박스에서 선택된 역할들
        
        # 기존 API 로직 재사용
        user = await auth_service.user_repository.get_by_id(user_id)
        if not user:
            return HTMLResponse(
                content='<div class="text-red-600 p-4">사용자를 찾을 수 없습니다.</div>',
                status_code=404
            )
        
        # 역할 업데이트
        updated_user = await auth_service.user_repository.update(user_id, {"roles": roles})
        
        if not updated_user:
            return HTMLResponse(
                content='<div class="text-red-600 p-4">역할 업데이트에 실패했습니다.</div>',
                status_code=500
            )
        
        logger.info(
            "사용자 역할 업데이트 (HTMX)",
            admin_id=current_user.id,
            user_id=user_id,
            new_roles=roles,
            old_roles=user.roles,
        )
        
        # 성공 응답 - 모달 닫기 + 사용자 테이블 행 업데이트 트리거
        # HTMX 응답: 모달을 닫고 성공 메시지 표시
        success_message = Div(
            "역할이 성공적으로 업데이트되었습니다.",
            cls="text-green-600 p-3 bg-green-50 rounded mb-4"
        )
        
        return HTMLResponse(
            content=to_xml(success_message),
            headers={
                "HX-Trigger": f"userUpdated-{user_id}",  # 사용자 테이블 업데이트 트리거
                "HX-Refresh": "true"  # 페이지 새로고침
            }
        )
        
    except Exception as e:
        logger.error("역할 업데이트 실패 (HTMX)", error=str(e), user_id=user_id)
        error_response = Div(
            f"역할 업데이트 중 오류가 발생했습니다: {str(e)}",
            cls="text-red-600 p-4"
        )
        return HTMLResponse(content=to_xml(error_response), status_code=500)


@app.get("/admin/users/{user_id}/row/refresh", response_class=HTMLResponse)
async def refresh_user_row(
    user_id: str,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    auth_service: Annotated[SQLiteAuthService, Depends(get_sqlite_auth_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """사용자 테이블 행 새로고침"""
    try:
        # 사용자 조회
        from .repositories.sqlite_user_repository import SQLiteUserRepository
        
        repository = SQLiteUserRepository(db)
        user = await repository.get_by_id(user_id)
        
        if not user:
            return HTMLResponse(
                content=f'<tr><td colspan="7" class="text-red-600 text-center p-4">사용자를 찾을 수 없습니다: {user_id}</td></tr>',
                status_code=404
            )
        
        # 업데이트된 사용자 행 생성
        user_row = Tr(
            Td(
                str(user.id),
                cls="px-6 py-4 whitespace-nowrap text-sm text-gray-900",
            ),
            Td(
                user.email,
                cls="px-6 py-4 whitespace-nowrap text-sm text-gray-900",
            ),
            Td(
                user.username or "-",
                cls="px-6 py-4 whitespace-nowrap text-sm text-gray-900",
            ),
            Td(
                ", ".join(user.roles),
                cls="px-6 py-4 whitespace-nowrap text-sm text-gray-900",
                id=f"userRoles_{user.id}"
            ),
            Td(
                Span(
                    "활성" if user.is_active else "비활성",
                    cls=f"px-2 inline-flex text-xs leading-5 font-semibold rounded-full {'bg-green-100 text-green-800' if user.is_active else 'bg-red-100 text-red-800'}",
                ),
                cls="px-6 py-4 whitespace-nowrap",
            ),
            Td(
                user.created_at.strftime("%Y-%m-%d"),
                cls="px-6 py-4 whitespace-nowrap text-sm text-gray-900",
            ),
            Td(
                Button(
                    "권한 보기",
                    **{"hx-get": f"/admin/users/{user.id}/permissions", "hx-target": "body", "hx-push-url": "true"},
                    cls="text-blue-600 hover:text-blue-900 text-sm font-medium mr-2",
                ),
                Button(
                    "역할 변경",
                    cls="text-green-600 hover:text-green-900 text-sm font-medium",
                    **{
                        "hx-get": f"/admin/users/{user.id}/modal/roles",
                        "hx-target": "#modalContainer",
                        "hx-swap": "innerHTML"
                    }
                ),
                cls="px-6 py-4 whitespace-nowrap text-sm font-medium",
            ),
            id=f"userRow_{user.id}",
            **{
                "hx-get": f"/admin/users/{user.id}/row/refresh",
                "hx-trigger": "userUpdated",
                "hx-swap": "outerHTML"
            }
        )
        
        return HTMLResponse(content=to_xml(user_row))
        
    except Exception as e:
        logger.error("사용자 행 새로고침 실패", error=str(e), user_id=user_id)
        error_row = Tr(
            Td(
                f"사용자 행 새로고침 중 오류가 발생했습니다: {str(e)}",
                colspan="7",
                cls="text-red-600 text-center p-4"
            ),
            id=f"userRow_{user_id}"
        )
        return HTMLResponse(content=to_xml(error_row), status_code=500)


@app.get("/admin/permissions", response_class=HTMLResponse)
async def admin_permissions_page(
    current_user: Annotated[UserResponse, Depends(require_admin)],
    permission_service=Depends(get_permission_service),
):
    """권한 관리 페이지"""
    try:
        # Breadcrumb 생성
        breadcrumb = AdminBreadcrumb([
            {"label": "관리자", "url": "/admin"},
            {"label": "권한 관리"}
        ])

        # 권한 생성 폼 필드 정의
        permission_form_fields = [
            {
                "name": "target_type",
                "label": "대상 타입",
                "type": "select",
                "options": [
                    {"value": "user", "label": "사용자별"},
                    {"value": "role", "label": "역할별"}
                ],
                "required": True
            },
            {
                "name": "resource_type", 
                "label": "리소스 타입",
                "type": "select",
                "options": [
                    {"value": "web_search", "label": "웹 검색"},
                    {"value": "vector_db", "label": "벡터 DB"}, 
                    {"value": "database", "label": "데이터베이스"}
                ],
                "required": True
            },
            {
                "name": "resource_name",
                "label": "리소스 이름",
                "type": "text",
                "placeholder": "예: public.*, users.documents",
                "required": True
            },
            {
                "name": "actions",
                "label": "권한",
                "type": "checkbox",
                "options": [
                    {"value": "read", "label": "읽기"},
                    {"value": "write", "label": "쓰기"},
                    {"value": "delete", "label": "삭제"}
                ]
            }
        ]

        # AdminForm 컴포넌트 사용
        permission_form = AdminForm(
            fields=permission_form_fields,
            action="/admin/permissions/create",
            method="POST",
            submit_text="권한 추가",
            form_id="permission-create-form",
            grid_cols=2
        )

        # 권한 생성 카드
        create_permission_card = AdminCard(
            title="새 권한 추가",
            content=permission_form,
            color="white"
        )

        # 필터링 섹션을 Details로 구성
        filter_section = Details(
            Summary(
                "🔍 필터 옵션",
                cls="cursor-pointer text-blue-600 hover:text-blue-800 font-medium mb-4 flex items-center"
            ),
            Div(
                LoadingSpinner(size="sm", color="blue"),
                " 필터 옵션을 불러오는 중...",
                **{
                    "hx-get": "/admin/permissions/filters",
                    "hx-trigger": "load",
                    "hx-target": "this",
                },
                cls="mb-6 p-4 bg-gray-50 rounded-lg"
            ),
            cls="mb-6"
        )

        # 권한 테이블 컨테이너
        permissions_table_container = Div(
            Div(
                LoadingSpinner(size="md", color="blue"),
                P("권한 목록을 불러오는 중...", cls="text-center text-gray-500 mt-4"),
                cls="text-center py-8"
            ),
            **{
                "hx-get": "/admin/permissions/table",
                "hx-trigger": "load",
                "hx-target": "this",
            },
            id="permissions-table-container"
        )

        # 기존 권한 목록 카드
        permissions_list_card = AdminCard(
            title="기존 권한 목록",
            content=Div(
                filter_section,
                permissions_table_container
            ),
            actions=[
                Button(
                    "🔄 새로고침",
                    **{
                        "hx-get": "/admin/permissions/table",
                        "hx-target": "#permissions-table-container",
                    },
                    cls="bg-blue-500 hover:bg-blue-600 text-white font-medium py-2 px-4 rounded-lg"
                ),
                A(
                    "📊 권한 내보내기",
                    href="/admin/export/permissions.csv",
                    cls="bg-green-500 hover:bg-green-600 text-white font-medium py-2 px-4 rounded-lg inline-block text-center",
                    download="permissions.csv"
                )
            ],
            color="white"
        )

        # 권한 관리 도움말 카드
        help_card = AdminCard(
            title="권한 관리 가이드",
            content=Div(
                Div(
                    Strong("🎯 대상 타입:"),
                    Ul(
                        Li("사용자별: 특정 사용자에게 권한 부여", cls="text-sm text-gray-600"),
                        Li("역할별: 특정 역할에 속한 모든 사용자에게 권한 부여", cls="text-sm text-gray-600"),
                        cls="ml-4 mt-2 space-y-1"
                    ),
                    cls="mb-4"
                ),
                Div(
                    Strong("📁 리소스 타입:"),
                    Ul(
                        Li("웹 검색: Tavily API를 통한 웹 검색 권한", cls="text-sm text-gray-600"),
                        Li("벡터 DB: Qdrant 벡터 데이터베이스 접근 권한", cls="text-sm text-gray-600"),
                        Li("데이터베이스: PostgreSQL 데이터베이스 접근 권한", cls="text-sm text-gray-600"),
                        cls="ml-4 mt-2 space-y-1"
                    ),
                    cls="mb-4"
                ),
                Div(
                    Strong("🔧 권한 종류:"),
                    Ul(
                        Li("읽기: 데이터 조회 및 검색", cls="text-sm text-gray-600"),
                        Li("쓰기: 데이터 생성 및 수정", cls="text-sm text-gray-600"),
                        Li("삭제: 데이터 삭제", cls="text-sm text-gray-600"),
                        cls="ml-4 mt-2 space-y-1"
                    )
                )
            ),
            color="blue"
        )

        content = Div(
            # Notification area for HTMX messages
            Div(id="notification-area", cls="mb-4"),
            
            breadcrumb,
            H1("권한 관리", cls="text-3xl font-bold text-gray-900 mb-8"),
            
            # 권한 생성 섹션
            create_permission_card,
            
            Div(cls="mb-8"),  # 구분선
            
            # 권한 목록 및 도움말 섹션
            Div(
                permissions_list_card,
                help_card,
                cls="grid grid-cols-1 lg:grid-cols-3 gap-6"
            )
        )

        page = create_layout("권한 관리", content, current_user)
        html_content = to_xml(page)
        return HTMLResponse(content=html_content)

    except Exception as e:
        logger.error("권한 관리 페이지 로딩 실패", error=str(e))
        error_content = Div(
            H1("오류", cls="text-3xl font-bold text-red-600 mb-4"),
            P(
                f"권한 관리 페이지를 로드하는 중 오류가 발생했습니다: {str(e)}",
                cls="text-gray-700",
            ),
        )
        page = create_layout("오류", error_content, current_user)
        html_content = to_xml(page)
        return HTMLResponse(content=html_content)


@app.get("/admin/permissions/table", response_class=HTMLResponse)
async def admin_permissions_table(
    current_user: Annotated[UserResponse, Depends(require_admin)],
    permission_service=Depends(get_permission_service),
    resource_type_filter: Optional[str] = None,
    resource_name_filter: Optional[str] = None,
    user_id_filter: Optional[int] = None,
    role_name_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
):
    """권한 목록 테이블 HTMX 엔드포인트"""
    try:
        # 기존 list_resource_permissions API와 동일한 로직 사용
        if not permission_service.db_conn:
            return Div(
                P("데이터베이스 연결이 필요합니다.", cls="text-red-600 p-4"),
                cls="text-center"
            )

        # 쿼리 조건 구성
        conditions = []
        params = []

        # 필터 파라미터 처리
        if resource_type_filter:
            try:
                resource_type = ResourceType(resource_type_filter)
                conditions.append(f"resource_type = ${len(params) + 1}")
                params.append(resource_type.value)
            except ValueError:
                pass  # 유효하지 않은 리소스 타입은 무시

        if resource_name_filter:
            conditions.append(f"resource_name ILIKE ${len(params) + 1}")
            params.append(f"%{resource_name_filter}%")

        if user_id_filter:
            conditions.append(f"user_id = ${len(params) + 1}")
            params.append(user_id_filter)

        if role_name_filter:
            conditions.append(f"role_name = ${len(params) + 1}")
            params.append(role_name_filter)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        # 총 개수 조회
        count_query = f"""
            SELECT COUNT(*) as total
            FROM resource_permissions
            {where_clause}
        """
        count_result = await permission_service.db_conn.fetchrow(count_query, *params[:len(params)-2] if params else [])
        total_count = count_result["total"] if count_result else 0

        # 권한 목록 조회
        query = f"""
            SELECT id, user_id, role_name, resource_type, resource_name, 
                   actions, conditions, granted_at, granted_by, expires_at
            FROM resource_permissions
            {where_clause}
            ORDER BY granted_at DESC
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """
        params.extend([limit, skip])

        rows = await permission_service.db_conn.fetch(query, *params)

        # HTML 테이블 생성
        permission_rows = []
        for row in rows:
            actions_str = ", ".join([a for a in row["actions"]])
            granted_date = row["granted_at"].strftime("%Y-%m-%d %H:%M") if row["granted_at"] else ""
            expires_date = row["expires_at"].strftime("%Y-%m-%d") if row["expires_at"] else "무제한"
            
            # 대상 표시 (사용자 또는 역할)
            target = row["role_name"] if row["role_name"] else f"사용자 ID: {row['user_id']}"
            
            permission_rows.append(
                Tr(
                    Td(target, cls="px-6 py-4 whitespace-nowrap text-sm text-gray-900"),
                    Td(row["resource_type"], cls="px-6 py-4 whitespace-nowrap text-sm text-gray-900"),
                    Td(row["resource_name"], cls="px-6 py-4 whitespace-nowrap text-sm text-gray-900"),
                    Td(actions_str, cls="px-6 py-4 whitespace-nowrap text-sm text-gray-900"),
                    Td(granted_date, cls="px-6 py-4 whitespace-nowrap text-sm text-gray-500"),
                    Td(expires_date, cls="px-6 py-4 whitespace-nowrap text-sm text-gray-500"),
                    Td(
                        Button(
                            "삭제",
                            **{
                                "hx-delete": f"/admin/permissions/{row['id']}",
                                "hx-target": "#permissions-table",
                                "hx-confirm": "이 권한을 삭제하시겠습니까?",
                            },
                            cls="text-red-600 hover:text-red-900 text-sm font-medium"
                        ),
                        cls="px-6 py-4 whitespace-nowrap text-sm font-medium"
                    ),
                    cls="hover:bg-gray-50"
                )
            )

        # 페이지네이션 정보
        has_next = skip + limit < total_count
        has_prev = skip > 0
        current_page = (skip // limit) + 1
        total_pages = (total_count + limit - 1) // limit

        table_content = Div(
            # 테이블 헤더와 데이터
            Table(
                Thead(
                    Tr(
                        Th("대상", cls="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"),
                        Th("리소스 타입", cls="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"),
                        Th("리소스 이름", cls="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"),
                        Th("권한", cls="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"),
                        Th("부여일", cls="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"),
                        Th("만료일", cls="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"),
                        Th("액션", cls="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"),
                        cls="bg-gray-50"
                    )
                ),
                Tbody(
                    *permission_rows if permission_rows else [
                        Tr(
                            Td(
                                "권한이 없습니다.", 
                                colspan="7", 
                                cls="px-6 py-4 text-center text-gray-500"
                            )
                        )
                    ],
                    cls="bg-white divide-y divide-gray-200"
                ),
                cls="min-w-full divide-y divide-gray-200"
            ),
            # 페이지네이션
            Div(
                Div(
                    P(f"총 {total_count}개 권한 중 {skip + 1}-{min(skip + limit, total_count)}번째 표시", 
                      cls="text-sm text-gray-700"),
                    cls="flex-1"
                ),
                Div(
                    Button(
                        "이전",
                        **{
                            "hx-get": f"/admin/permissions/table?skip={max(0, skip - limit)}&limit={limit}",
                            "hx-target": "#permissions-table",
                            "hx-include": "#permissions-filters",
                        },
                        disabled=not has_prev,
                        cls="mr-2 px-3 py-1 text-sm bg-gray-300 hover:bg-gray-400 text-gray-700 rounded disabled:opacity-50"
                    ),
                    Span(f"페이지 {current_page} / {total_pages}", cls="mx-2 text-sm text-gray-700"),
                    Button(
                        "다음",
                        **{
                            "hx-get": f"/admin/permissions/table?skip={skip + limit}&limit={limit}",
                            "hx-target": "#permissions-table", 
                            "hx-include": "#permissions-filters",
                        },
                        disabled=not has_next,
                        cls="ml-2 px-3 py-1 text-sm bg-gray-300 hover:bg-gray-400 text-gray-700 rounded disabled:opacity-50"
                    ),
                    cls="flex items-center"
                ),
                cls="flex items-center justify-between mt-4"
            ),
            id="permissions-table"
        )

        return table_content

    except Exception as e:
        logger.error("권한 테이블 로딩 실패", error=str(e))
        return Div(
            P(f"권한 목록을 불러오는 중 오류가 발생했습니다: {str(e)}", cls="text-red-600 p-4"),
            cls="text-center"
        )


@app.delete("/admin/permissions/{permission_id}", response_class=HTMLResponse)
async def delete_permission(
    permission_id: int,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    permission_service=Depends(get_permission_service),
):
    """권한 삭제 HTMX 엔드포인트"""
    try:
        if not permission_service.db_conn:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="데이터베이스 연결이 필요합니다",
            )

        # 권한 삭제
        delete_query = "DELETE FROM resource_permissions WHERE id = $1"
        result = await permission_service.db_conn.execute(delete_query, permission_id)
        
        if result == "DELETE 0":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="권한을 찾을 수 없습니다",
            )

        logger.info("권한 삭제", permission_id=permission_id, admin_user=current_user.email)
        
        # 테이블 새로고침을 위해 HTMX 응답으로 업데이트된 테이블 반환
        return await admin_permissions_table(current_user, permission_service)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("권한 삭제 실패", permission_id=permission_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="권한 삭제에 실패했습니다",
        )


@app.get("/admin/permissions/filters", response_class=HTMLResponse)
async def admin_permissions_filters(
    current_user: Annotated[UserResponse, Depends(require_admin)],
):
    """권한 필터링 UI 컴포넌트"""
    return Div(
        Div(
            Div(
                Label("리소스 타입", cls="block text-sm font-medium text-gray-700 mb-2"),
                Select(
                    Option("전체", value=""),
                    Option("웹 검색", value="web_search"),
                    Option("벡터 DB", value="vector_db"),
                    Option("데이터베이스", value="database"),
                    name="resource_type_filter",
                    **{
                        "hx-get": "/admin/permissions/table",
                        "hx-target": "#permissions-table",
                        "hx-trigger": "change",
                        "hx-include": "#permissions-filters",
                    },
                    cls="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500",
                ),
                cls="mb-4"
            ),
            Div(
                Label("리소스 이름", cls="block text-sm font-medium text-gray-700 mb-2"),
                Input(
                    type="text",
                    name="resource_name_filter",
                    placeholder="리소스 이름으로 검색...",
                    **{
                        "hx-get": "/admin/permissions/table",
                        "hx-target": "#permissions-table",
                        "hx-trigger": "keyup changed delay:500ms",
                        "hx-include": "#permissions-filters",
                    },
                    cls="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500",
                ),
                cls="mb-4"
            ),
            cls="grid grid-cols-1 md:grid-cols-2 gap-4"
        ),
        Div(
            Div(
                Label("역할명", cls="block text-sm font-medium text-gray-700 mb-2"),
                Input(
                    type="text",
                    name="role_name_filter",
                    placeholder="역할명으로 검색...",
                    **{
                        "hx-get": "/admin/permissions/table",
                        "hx-target": "#permissions-table",
                        "hx-trigger": "keyup changed delay:500ms",
                        "hx-include": "#permissions-filters",
                    },
                    cls="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500",
                ),
                cls="mb-4"
            ),
            Div(
                Label("사용자 ID", cls="block text-sm font-medium text-gray-700 mb-2"),
                Input(
                    type="number",
                    name="user_id_filter",
                    placeholder="사용자 ID로 검색...",
                    **{
                        "hx-get": "/admin/permissions/table",
                        "hx-target": "#permissions-table",
                        "hx-trigger": "keyup changed delay:500ms",
                        "hx-include": "#permissions-filters",
                    },
                    cls="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500",
                ),
                cls="mb-4"
            ),
            cls="grid grid-cols-1 md:grid-cols-2 gap-4"
        ),
        id="permissions-filters"
    )


@app.get("/admin/roles", response_class=HTMLResponse)
async def admin_roles_page(
    current_user: Annotated[UserResponse, Depends(require_admin)],
    rbac_service=Depends(get_rbac_service),
):
    """역할 관리 페이지"""
    try:
        # 컴포넌트 라이브러리 import 추가
        from .components import AdminForm, AdminCard, StatsCard, AdminBreadcrumb
        
        # 역할 목록 조회
        roles = []
        for role_name, permissions in rbac_service.role_permissions.items():
            roles.append(
                {
                    "name": role_name,
                    "permissions": permissions,
                    "permission_count": len(permissions),
                }
            )

        # Breadcrumb 생성
        breadcrumb_items = [
            {"label": "관리자", "url": "/admin"},
            {"label": "역할 관리"}
        ]

        content = Div(
            # Breadcrumb
            AdminBreadcrumb(breadcrumb_items),
            
            H1("역할 관리", cls="text-3xl font-bold text-gray-900 mb-8"),
            
            # 통계 카드
            Div(
                StatsCard(
                    title="총 역할 수",
                    value=len(roles),
                    color="blue",
                    icon="👥",
                    subtitle="시스템에 등록된 역할"
                ),
                StatsCard(
                    title="활성 권한",
                    value=sum(len(role["permissions"]) for role in roles),
                    color="green", 
                    icon="🔐",
                    subtitle="할당된 권한 총합"
                ),
                StatsCard(
                    title="기본 역할",
                    value="3",
                    color="purple",
                    icon="⭐",
                    subtitle="admin, user, guest"
                ),
                cls="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8"
            ),
            
            # 새 역할 추가 카드
            AdminCard(
                title="새 역할 추가",
                content=AdminForm(
                    fields=[
                        {
                            "name": "name",
                            "label": "역할 이름",
                            "type": "text",
                            "placeholder": "예: editor, viewer",
                            "required": True
                        },
                        {
                            "name": "description", 
                            "label": "설명 (선택사항)",
                            "type": "textarea",
                            "placeholder": "역할에 대한 설명을 입력하세요",
                            "rows": 3
                        }
                    ],
                    action="/admin/roles/create",
                    method="POST",
                    submit_text="역할 생성",
                    form_id="create-role-form"
                ),
                color="white"
            ),
            
            # 역할 목록 카드
            AdminCard(
                title="역할 목록",
                content=Div(
                    # 역할 테이블 컨테이너
                    Div(
                        Div(
                            "역할 목록을 불러오는 중...",
                            cls="text-center py-8 text-gray-500"
                        ),
                        **{
                            "hx-get": "/admin/roles/table",
                            "hx-trigger": "load",
                            "hx-target": "this",
                        },
                        id="roles-table-container",
                        cls="mb-6"
                    )
                ),
                color="white"
            ),
            
            # 역할 권한 상세 정보 영역
            Div(
                id="role-permissions-detail",
                cls="mb-8"
            ),
            
            # 권한 매트릭스 카드
            AdminCard(
                title="권한 매트릭스",
                content=Div(
                    P("각 역할별 리소스 및 도구 접근 권한을 한 눈에 확인할 수 있습니다.", cls="text-gray-600 mb-4"),
                    
                    # 매트릭스 토글 버튼
                    Details(
                        Summary(
                            "권한 매트릭스 보기/숨기기",
                            cls="cursor-pointer text-blue-600 hover:text-blue-800 font-medium mb-4"
                        ),
                        Div(
                            Div(
                                "권한 매트릭스를 불러오는 중...",
                                cls="text-center py-8 text-gray-500"
                            ),
                            **{
                                "hx-get": "/admin/roles/matrix",
                                "hx-trigger": "intersect once",
                                "hx-target": "this",
                            },
                            id="roles-matrix-container"
                        ),
                        cls="mb-6"
                    )
                ),
                color="white"
            ),
            
            # 역할 별칭 정보 카드
            AdminCard(
                title="역할 별칭 정보",
                content=Ul(
                    Li(
                        Strong("viewer"), " → ", Strong("guest"), 
                        " : 웹 검색만 가능한 읽기 전용 역할",
                        cls="mb-2"
                    ),
                    Li(
                        Strong("analyst"), " → ", Strong("user"), 
                        " : 모든 검색 및 기본 데이터 조작이 가능한 역할",
                        cls="mb-2"
                    ),
                    cls="text-sm text-gray-700"
                ),
                color="blue"
            ),
            
            # 역할 편집 모달 컨테이너
            Div(
                id="role-edit-modal",
                cls="hidden"
            ),
        )

        page = create_layout("역할 관리", content, current_user)
        html_content = to_xml(page)
        return HTMLResponse(content=html_content)

    except Exception as e:
        logger.error("역할 관리 페이지 로딩 실패", error=str(e))
        error_content = Div(
            H1("오류", cls="text-3xl font-bold text-red-600 mb-4"),
            P(
                f"역할 관리 페이지를 로드하는 중 오류가 발생했습니다: {str(e)}",
                cls="text-gray-700",
            ),
        )
        page = create_layout("오류", error_content, current_user)
        html_content = to_xml(page)
        return HTMLResponse(content=html_content)

@app.get("/admin/roles/table", response_class=HTMLResponse)
async def admin_roles_table(
    current_user: Annotated[UserResponse, Depends(require_admin)],
    rbac_service=Depends(get_rbac_service),
):
    """역할 테이블 HTMX 엔드포인트"""
    try:
        # 모든 역할 정보 수집
        roles_data = []
        for role_name, permissions in rbac_service.role_permissions.items():
            # 해당 역할이 접근 가능한 도구들 확인
            accessible_tools = []
            for tool_name in rbac_service.tool_permissions.keys():
                if rbac_service.check_tool_permission([role_name], tool_name):
                    accessible_tools.append(tool_name)
            
            roles_data.append({
                "name": role_name,
                "permissions": permissions,
                "permission_count": len(permissions),
                "accessible_tools": accessible_tools,
                "tool_count": len(accessible_tools)
            })

        # 역할 테이블 생성
        role_rows = []
        for role_data in roles_data:
            # 역할 별칭 표시
            aliases = []
            if role_data["name"] == "guest":
                aliases.append("viewer")
            elif role_data["name"] == "user":
                aliases.append("analyst")
            
            alias_text = f" (별칭: {', '.join(aliases)})" if aliases else ""
            
            # 권한 리소스별 요약
            resources_summary = {}
            for perm in role_data["permissions"]:
                resource = perm.resource.value
                action = perm.action.value
                if resource not in resources_summary:
                    resources_summary[resource] = []
                resources_summary[resource].append(action)
            
            resources_text = ", ".join([
                f"{res}({','.join(actions)})" 
                for res, actions in resources_summary.items()
            ])
            
            role_rows.append(
                Tr(
                    Td(
                        Div(
                            Strong(role_data["name"]),
                            Span(alias_text, cls="text-sm text-gray-500") if alias_text else "",
                            cls="flex flex-col"
                        ),
                        cls="px-6 py-4 whitespace-nowrap text-sm text-gray-900"
                    ),
                    Td(role_data["permission_count"], cls="px-6 py-4 whitespace-nowrap text-sm text-gray-900"),
                    Td(
                        Span(resources_text, cls="text-sm text-gray-700") if resources_text else "없음",
                        cls="px-6 py-4 text-sm text-gray-900"
                    ),
                    Td(role_data["tool_count"], cls="px-6 py-4 whitespace-nowrap text-sm text-gray-900"),
                    Td(
                        Div(
                            Button(
                                "권한 보기",
                                **{
                                    "hx-get": f"/admin/roles/{role_data['name']}/permissions",
                                    "hx-target": "#role-permissions-detail",
                                    "hx-trigger": "click",
                                },
                                cls="mr-2 px-3 py-1 text-sm bg-blue-500 hover:bg-blue-600 text-white rounded"
                            ),
                            Button(
                                "편집",
                                **{
                                    "hx-get": f"/admin/roles/{role_data['name']}/edit",
                                    "hx-target": "#role-edit-modal",
                                    "hx-trigger": "click",
                                },
                                cls="mr-2 px-3 py-1 text-sm bg-yellow-500 hover:bg-yellow-600 text-white rounded"
                            ),
                            Button(
                                "삭제",
                                **{
                                    "hx-delete": f"/admin/roles/{role_data['name']}",
                                    "hx-target": "#roles-table",
                                    "hx-confirm": f"역할 '{role_data['name']}'을 정말 삭제하시겠습니까?",
                                },
                                cls="px-3 py-1 text-sm bg-red-500 hover:bg-red-600 text-white rounded",
                                disabled=role_data["name"] in ["admin", "user"]  # 기본 역할은 삭제 불가
                            ),
                            cls="flex space-x-1"
                        ),
                        cls="px-6 py-4 whitespace-nowrap text-sm font-medium"
                    ),
                    cls="hover:bg-gray-50"
                )
            )

        table_content = Table(
            Thead(
                Tr(
                    Th("역할", cls="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"),
                    Th("권한 수", cls="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"),
                    Th("리소스 권한", cls="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"),
                    Th("도구 접근", cls="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"),
                    Th("액션", cls="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"),
                    cls="bg-gray-50"
                )
            ),
            Tbody(
                *role_rows if role_rows else [
                    Tr(
                        Td(
                            "역할이 없습니다.", 
                            colspan="5", 
                            cls="px-6 py-4 text-center text-gray-500"
                        )
                    )
                ],
                cls="bg-white divide-y divide-gray-200"
            ),
            cls="min-w-full divide-y divide-gray-200",
            id="roles-table"
        )

        return table_content

    except Exception as e:
        logger.error("역할 테이블 로딩 실패", error=str(e))
        return Div(
            P(f"역할 목록을 불러오는 중 오류가 발생했습니다: {str(e)}", cls="text-red-600 p-4"),
            cls="text-center"
        )


@app.get("/admin/roles/matrix", response_class=HTMLResponse)
async def admin_roles_matrix(
    current_user: Annotated[UserResponse, Depends(require_admin)],
    rbac_service=Depends(get_rbac_service),
):
    """권한 매트릭스 HTMX 엔드포인트"""
    try:
        from ..models import ResourceType, ActionType
        
        # 모든 리소스와 액션 조합
        resources = [ResourceType.WEB_SEARCH, ResourceType.VECTOR_DB, ResourceType.DATABASE]
        actions = [ActionType.READ, ActionType.WRITE]
        
        # 역할 목록
        roles = list(rbac_service.role_permissions.keys())
        
        # 헤더 행 생성
        header_cells = [Th("역할/리소스", cls="px-4 py-2 bg-gray-100 border text-xs font-medium text-gray-500 uppercase")]
        for resource in resources:
            for action in actions:
                header_cells.append(
                    Th(
                        Div(
                            Div(resource.value, cls="font-semibold"),
                            Div(action.value, cls="text-xs"),
                            cls="text-center"
                        ),
                        cls="px-2 py-2 bg-gray-100 border text-xs"
                    )
                )
        
        # 데이터 행 생성
        matrix_rows = [Tr(*header_cells)]
        
        for role in roles:
            cells = [Td(Strong(role), cls="px-4 py-2 border bg-gray-50 font-medium")]
            
            for resource in resources:
                for action in actions:
                    has_permission = rbac_service.check_permission([role], resource, action)
                    icon = "✅" if has_permission else "❌"
                    color_class = "text-green-600" if has_permission else "text-red-600"
                    
                    cells.append(
                        Td(
                            Span(icon, cls=f"{color_class} text-lg"),
                            cls="px-2 py-2 border text-center"
                        )
                    )
            
            matrix_rows.append(Tr(*cells, cls="hover:bg-gray-50"))
        
        # 도구 접근 매트릭스
        tool_header_cells = [Th("역할/도구", cls="px-4 py-2 bg-blue-100 border text-xs font-medium text-gray-500 uppercase")]
        tools = list(rbac_service.tool_permissions.keys())
        
        for tool in tools:
            tool_header_cells.append(
                Th(
                    tool.replace("_", " ").title(),
                    cls="px-2 py-2 bg-blue-100 border text-xs text-center",
                    style="writing-mode: vertical-lr; text-orientation: mixed;"
                )
            )
        
        tool_rows = [Tr(*tool_header_cells)]
        
        for role in roles:
            cells = [Td(Strong(role), cls="px-4 py-2 border bg-blue-50 font-medium")]
            
            for tool in tools:
                has_access = rbac_service.check_tool_permission([role], tool)
                icon = "✅" if has_access else "❌"
                color_class = "text-green-600" if has_access else "text-red-600"
                
                cells.append(
                    Td(
                        Span(icon, cls=f"{color_class} text-lg"),
                        cls="px-2 py-2 border text-center"
                    )
                )
            
            tool_rows.append(Tr(*cells, cls="hover:bg-blue-50"))

        matrix_content = Div(
            H3("리소스 권한 매트릭스", cls="text-lg font-semibold mb-4"),
            Div(
                Table(
                    *matrix_rows,
                    cls="border-collapse border border-gray-300 text-sm"
                ),
                cls="overflow-x-auto mb-8"
            ),
            H3("도구 접근 권한 매트릭스", cls="text-lg font-semibold mb-4"),
            Div(
                Table(
                    *tool_rows,
                    cls="border-collapse border border-gray-300 text-sm"
                ),
                cls="overflow-x-auto"
            ),
            id="roles-matrix"
        )

        return matrix_content

    except Exception as e:
        logger.error("권한 매트릭스 로딩 실패", error=str(e))
        return Div(
            P(f"권한 매트릭스를 불러오는 중 오류가 발생했습니다: {str(e)}", cls="text-red-600 p-4"),
            cls="text-center"
        )


@app.get("/admin/roles/{role_name}/permissions", response_class=HTMLResponse)
async def role_permissions_detail(
    role_name: str,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    rbac_service=Depends(get_rbac_service),
):
    """특정 역할의 상세 권한 정보"""
    try:
        if role_name not in rbac_service.role_permissions:
            return Div(P("역할을 찾을 수 없습니다.", cls="text-red-600 p-4"))
        
        permissions = rbac_service.role_permissions[role_name]
        
        # 권한별 상세 정보
        permission_details = []
        for perm in permissions:
            permission_details.append(
                Div(
                    Span(f"리소스: {perm.resource.value}", cls="font-medium text-blue-600"),
                    Span(f"액션: {perm.action.value}", cls="ml-4 text-gray-600"),
                    cls="p-2 bg-gray-50 rounded mb-2"
                )
            )
        
        # 접근 가능한 도구들
        accessible_tools = []
        for tool_name in rbac_service.tool_permissions.keys():
            if rbac_service.check_tool_permission([role_name], tool_name):
                accessible_tools.append(
                    Span(
                        tool_name.replace("_", " ").title(),
                        cls="inline-block px-2 py-1 bg-green-100 text-green-800 rounded text-sm mr-2 mb-2"
                    )
                )
        
        detail_content = Div(
            H4(f"'{role_name}' 역할 상세 권한", cls="text-lg font-semibold mb-4"),
            
            Div(
                H5("리소스 권한", cls="font-medium mb-2"),
                *permission_details if permission_details else [P("권한이 없습니다.", cls="text-gray-500")],
                cls="mb-6"
            ),
            
            Div(
                H5("접근 가능한 도구", cls="font-medium mb-2"),
                Div(*accessible_tools) if accessible_tools else P("접근 가능한 도구가 없습니다.", cls="text-gray-500"),
                cls="mb-4"
            ),
            
            Button(
                "닫기",
                **{
                    "hx-get": "/admin/roles/empty",
                    "hx-target": "#role-permissions-detail",
                },
                cls="px-4 py-2 bg-gray-500 hover:bg-gray-600 text-white rounded"
            ),
            
            cls="p-4 bg-white border rounded-lg shadow"
        )
        
        return detail_content

    except Exception as e:
        logger.error("역할 권한 상세 조회 실패", role_name=role_name, error=str(e))
        return Div(
            P(f"권한 정보를 불러오는 중 오류가 발생했습니다: {str(e)}", cls="text-red-600 p-4"),
            cls="text-center"
        )


@app.get("/admin/roles/empty", response_class=HTMLResponse)
async def empty_content():
    """빈 컨텐츠 반환"""
    return Div("")


@app.delete("/admin/roles/{role_name}", response_class=HTMLResponse)
async def delete_role(
    role_name: str,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    rbac_service=Depends(get_rbac_service),
):
    """역할 삭제"""
    try:
        # 기본 역할은 삭제 불가
        if role_name in ["admin", "user"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="기본 역할은 삭제할 수 없습니다",
            )
        
        if role_name not in rbac_service.role_permissions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="역할을 찾을 수 없습니다",
            )
        
        # 역할 삭제 (현재는 메모리에서만)
        del rbac_service.role_permissions[role_name]
        
        logger.info("역할 삭제", role_name=role_name, admin_user=current_user.email)
        
        # 업데이트된 테이블 반환
        return await admin_roles_table(current_user, rbac_service)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("역할 삭제 실패", role_name=role_name, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="역할 삭제에 실패했습니다",
        )

@app.get("/admin/roles/{role_name}/edit", response_class=HTMLResponse)
async def edit_role_modal(
    role_name: str,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    rbac_service=Depends(get_rbac_service),
):
    """역할 편집 모달"""
    try:
        if role_name not in rbac_service.role_permissions:
            return Div(P("역할을 찾을 수 없습니다.", cls="text-red-600 p-4"))
        
        from ..models import ResourceType, ActionType
        
        current_permissions = rbac_service.role_permissions[role_name]
        
        # 모든 가능한 권한 조합
        all_permissions = []
        for resource in [ResourceType.WEB_SEARCH, ResourceType.VECTOR_DB, ResourceType.DATABASE]:
            for action in [ActionType.READ, ActionType.WRITE]:
                permission_key = f"{resource.value}_{action.value}"
                is_checked = any(
                    p.resource == resource and p.action == action 
                    for p in current_permissions
                )
                all_permissions.append({
                    "key": permission_key,
                    "resource": resource,
                    "action": action,
                    "checked": is_checked,
                    "label": f"{resource.value} - {action.value}"
                })
        
        modal_content = Div(
            # 모달 오버레이
            Div(
                # 모달 컨테이너
                Div(
                    # 모달 헤더
                    Div(
                        H3(f"'{role_name}' 역할 편집", cls="text-lg font-medium text-gray-900"),
                        Button(
                            "×",
                            **{
                                "hx-get": "/admin/roles/empty",
                                "hx-target": "#role-edit-modal",
                            },
                            cls="text-gray-400 hover:text-gray-600 text-2xl font-bold"
                        ),
                        cls="flex justify-between items-center mb-4"
                    ),
                    
                    # 모달 본문
                    Form(
                        Div(
                            H4("리소스 권한", cls="font-medium mb-3"),
                            Div(
                                *[
                                    Label(
                                        Input(
                                            type="checkbox",
                                            name="permissions",
                                            value=perm["key"],
                                            checked=perm["checked"],
                                            cls="mr-2"
                                        ),
                                        perm["label"],
                                        cls="flex items-center mb-2 text-sm"
                                    )
                                    for perm in all_permissions
                                ],
                                cls="grid grid-cols-2 gap-2 mb-4"
                            ),
                            cls="mb-6"
                        ),
                        
                        # 버튼
                        Div(
                            Button(
                                "취소",
                                type="button",
                                **{
                                    "hx-get": "/admin/roles/empty",
                                    "hx-target": "#role-edit-modal",
                                },
                                cls="mr-2 px-4 py-2 bg-gray-300 hover:bg-gray-400 text-gray-700 rounded"
                            ),
                            Button(
                                "저장",
                                type="submit",
                                cls="px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded"
                            ),
                            cls="flex justify-end"
                        ),
                        
                        **{
                            "hx-put": f"/admin/roles/{role_name}",
                            "hx-target": "#roles-table-container",
                            "hx-include": "this",
                        },
                        method="post"
                    ),
                    
                    cls="bg-white rounded-lg p-6 max-w-md mx-auto mt-20 relative"
                ),
                cls="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full",
                id="role-modal-overlay",
                **{
                    "hx-get": "/admin/roles/empty",
                    "hx-target": "#role-edit-modal",
                    "hx-trigger": "click[target==this]",
                }
            ),
            id="roleEditModal"
        )
        
        return modal_content

    except Exception as e:
        logger.error("역할 편집 모달 로딩 실패", role_name=role_name, error=str(e))
        return Div(
            P(f"역할 편집 폼을 불러오는 중 오류가 발생했습니다: {str(e)}", cls="text-red-600 p-4"),
            cls="text-center"
        )


@app.put("/admin/roles/{role_name}", response_class=HTMLResponse)
async def update_role(
    role_name: str,
    request: Request,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    rbac_service=Depends(get_rbac_service),
):
    """역할 권한 업데이트"""
    try:
        if role_name not in rbac_service.role_permissions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="역할을 찾을 수 없습니다",
            )
        
        # 폼 데이터 파싱
        form_data = await request.form()
        selected_permissions = form_data.getlist("permissions")
        
        from ..models import Permission, ResourceType, ActionType
        
        # 새로운 권한 목록 구성
        new_permissions = []
        for perm_key in selected_permissions:
            try:
                resource_str, action_str = perm_key.split("_")
                resource = ResourceType(resource_str)
                action = ActionType(action_str)
                new_permissions.append(Permission(resource=resource, action=action))
            except (ValueError, KeyError) as e:
                logger.warning("유효하지 않은 권한", permission_key=perm_key, error=str(e))
                continue
        
        # 권한 업데이트
        rbac_service.role_permissions[role_name] = new_permissions
        
        logger.info(
            "역할 권한 업데이트", 
            role_name=role_name, 
            new_permission_count=len(new_permissions),
            admin_user=current_user.email
        )
        
        # 모달 닫기 및 테이블 업데이트
        return Div(
            Div(
                **{
                    "hx-get": "/admin/roles/table",
                    "hx-trigger": "load",
                    "hx-target": "this",
                },
                cls="text-center py-8 text-gray-500"
            ),
            **{
                "hx-get": "/admin/roles/empty",
                "hx-target": "#role-edit-modal",
                "hx-trigger": "load delay:100ms",
            },
            id="roles-table-container"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("역할 업데이트 실패", role_name=role_name, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="역할 업데이트에 실패했습니다",
        )


@app.post("/admin/roles/create", response_class=HTMLResponse)
async def create_role(
    request: Request,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    rbac_service=Depends(get_rbac_service),
):
    """새 역할 생성"""
    try:
        form_data = await request.form()
        role_name = form_data.get("name", "").strip()
        description = form_data.get("description", "").strip()
        
        if not role_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="역할 이름은 필수입니다",
            )
        
        if role_name in rbac_service.role_permissions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="이미 존재하는 역할입니다",
            )
        
        # 새 역할 생성 (기본적으로 빈 권한)
        rbac_service.role_permissions[role_name] = []
        
        logger.info(
            "새 역할 생성", 
            role_name=role_name, 
            description=description,
            admin_user=current_user.email
        )
        
        # 페이지 새로고침
        return HTMLResponse(
            content="",
            headers={"HX-Refresh": "true"},
            status_code=200
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("역할 생성 실패", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="역할 생성에 실패했습니다",
        )


@app.get("/admin/users/{user_id}/permissions", response_class=HTMLResponse)
async def admin_user_permissions_page(
    user_id: int,
    current_user: Annotated[UserResponse, Depends(require_admin)],
    auth_service: Annotated[SQLiteAuthService, Depends(get_sqlite_auth_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
    permission_service=Depends(get_permission_service),
):
    """사용자별 권한 관리 페이지"""
    try:
        # 사용자 정보 조회
        user = await auth_service.get_user_by_id(str(user_id))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="사용자를 찾을 수 없습니다",
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
                        "granted_at": row["granted_at"],
                    }
                    for row in rows
                ]
            except Exception as e:
                logger.warning("사용자 권한 조회 실패", error=str(e))

        content = Div(
            Div(
                A(
                    "← 사용자 관리로 돌아가기",
                    href="/admin/users",
                    cls="text-blue-600 hover:text-blue-800 mb-4 inline-block",
                ),
                cls="mb-4",
            ),
            H1(
                f"{user.email}의 권한 관리", cls="text-3xl font-bold text-gray-900 mb-8"
            ),
            # 사용자 정보
            Div(
                H2("사용자 정보", cls="text-xl font-semibold text-gray-900 mb-4"),
                Div(
                    P(f"이메일: {user.email}", cls="mb-2"),
                    P(f"사용자명: {user.username or '-'}", cls="mb-2"),
                    P(f"역할: {', '.join(user.roles)}", cls="mb-2"),
                    P(f"상태: {'활성' if user.is_active else '비활성'}", cls="mb-2"),
                    P(f"가입일: {user.created_at.strftime('%Y-%m-%d')}", cls="mb-2"),
                    cls="text-gray-700",
                ),
                cls="bg-white rounded-lg shadow-md p-6 mb-8",
            ),
            # 개별 권한 목록
            Div(
                H2("개별 권한", cls="text-xl font-semibold text-gray-900 mb-4"),
                Div(
                    P(
                        f"총 {len(permissions) if permissions else 0}개의 개별 권한이 있습니다."
                        if permissions
                        else "이 사용자에게 부여된 개별 권한이 없습니다.",
                        cls="text-gray-600 text-center py-8",
                    ),
                    cls="bg-white rounded-lg shadow-md",
                ),
            ),
            # 권한 추가 폼
            Div(
                H2("새 권한 추가", cls="text-xl font-semibold text-gray-900 mb-4"),
                Form(
                    Input(type="hidden", name="user_id", value=str(user_id)),
                    Div(
                        Div(
                            Label(
                                "리소스 타입",
                                cls="block text-sm font-medium text-gray-700 mb-2",
                            ),
                            Select(
                                Option("웹 검색", value="web_search"),
                                Option("벡터 DB", value="vector_db"),
                                Option("데이터베이스", value="database"),
                                name="resource_type",
                                cls="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500",
                            ),
                            cls="mb-4",
                        ),
                        Div(
                            Label(
                                "리소스 이름",
                                cls="block text-sm font-medium text-gray-700 mb-2",
                            ),
                            Input(
                                type="text",
                                name="resource_name",
                                placeholder="예: public.*, users.documents",
                                cls="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500",
                            ),
                            cls="mb-4",
                        ),
                        cls="grid grid-cols-1 md:grid-cols-2 gap-4",
                    ),
                    Div(
                        Label(
                            "권한", cls="block text-sm font-medium text-gray-700 mb-2"
                        ),
                        Div(
                            Label(
                                Input(
                                    type="checkbox",
                                    name="actions",
                                    value="read",
                                    cls="mr-2",
                                ),
                                "읽기",
                                cls="inline-flex items-center mr-4",
                            ),
                            Label(
                                Input(
                                    type="checkbox",
                                    name="actions",
                                    value="write",
                                    cls="mr-2",
                                ),
                                "쓰기",
                                cls="inline-flex items-center mr-4",
                            ),
                            Label(
                                Input(
                                    type="checkbox",
                                    name="actions",
                                    value="delete",
                                    cls="mr-2",
                                ),
                                "삭제",
                                cls="inline-flex items-center",
                            ),
                            cls="flex flex-wrap",
                        ),
                        cls="mb-4",
                    ),
                    Button(
                        "권한 추가",
                        type="submit",
                        cls="bg-blue-500 hover:bg-blue-600 text-white font-medium py-2 px-4 rounded-lg",
                    ),
                    method="post",
                    action=f"/admin/users/{user_id}/permissions/create",
                    cls="space-y-4",
                ),
                cls="bg-white rounded-lg shadow-md p-6",
            ),
            # JavaScript 함수들
            # JavaScript 함수 제거됨 - HTMX 엔드포인트로 대체
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
            P(
                f"사용자 권한 페이지를 로드하는 중 오류가 발생했습니다: {str(e)}",
                cls="text-gray-700",
            ),
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
