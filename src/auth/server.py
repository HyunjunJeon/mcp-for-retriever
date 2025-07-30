"""
MCP 서버용 JWT 기반 인증 게이트웨이 서버

이 모듈은 MCP(Model Context Protocol) 서버의 인증과 권한 관리를 담당하는
FastAPI 기반 게이트웨이 서버를 구현합니다. 클라이언트의 모든 요청은
이 게이트웨이를 통해 인증과 권한 검증을 거친 후 실제 MCP 서버로 전달됩니다.

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
        
    MCP 프록시:
        - 인증된 요청을 실제 MCP 서버로 전달
        - 배치 요청 처리 지원
        - 요청/응답 로깅 및 모니터링
        - 내부 API 키를 통한 MCP 서버 인증
        
    사용자 관리:
        - 사용자 검색 및 조회
        - 관리자용 사용자 목록 및 통계
        - 사용자 프로필 관리
        - 최근 가입자 조회

API 엔드포인트:
    인증 관련:
        - POST /auth/register: 회원가입
        - POST /auth/login: 로그인  
        - POST /auth/refresh: 토큰 갱신
        - GET /auth/me: 현재 사용자 정보 조회
        
    MCP 프록시:
        - POST /mcp/proxy: 단일 MCP 요청 전달
        - POST /mcp/batch: 배치 MCP 요청 전달
        
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
    - MCP_SERVER_URL: 실제 MCP 서버 주소
    - MCP_INTERNAL_API_KEY: MCP 서버 내부 인증키
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

from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog
import uvicorn

from .models import (
    UserCreate,
    UserLogin,
    UserResponse,
    AuthTokens,
)
from .services import (
    AuthService,
    AuthenticationError,
    MCPRequest,
    MCPResponse,
    MCPProxyService,
)
from .dependencies import (
    get_auth_service,
    get_current_user,
    get_current_active_user,
    get_mcp_proxy_service,
    require_admin,
)


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
        - 로깅 시스템 초기화 확인
        - 서비스 의존성 준비 상태 확인
        - 서버 시작 로그 기록
        
    종료 시 작업:
        - 활성 연결 정리
        - 리소스 해제
        - 종료 로그 기록
        
    Args:
        app (FastAPI): FastAPI 애플리케이션 인스턴스
        
    Yields:
        None: 애플리케이션 실행 중에는 제어권을 양보
    """
    # 시작 시
    logger.info("인증 게이트웨이 서버 시작", port=8000)
    
    yield
    
    # 종료 시
    logger.info("인증 게이트웨이 서버 종료")


# FastAPI 앱 생성
app = FastAPI(
    title="MCP Auth Gateway",
    description="JWT 기반 인증 및 MCP 프록시 게이트웨이",
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
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
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
        user = await auth_service.register(user_create)
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
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
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
        tokens = await auth_service.login(user_login)
        logger.info("로그인 성공", email=user_login.email)
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
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
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


# === MCP 프록시 엔드포인트 ===

@app.post("/mcp/proxy", response_model=MCPResponse)
async def proxy_mcp_request(
    request: MCPRequest,
    current_user: Annotated[UserResponse, Depends(get_current_active_user)],
    mcp_proxy: Annotated[MCPProxyService, Depends(get_mcp_proxy_service)],
):
    """
    인증된 MCP 요청을 실제 MCP 서버로 프록시
    
    사용자의 JWT 토큰을 검증하고 권한을 확인한 후,
    요청을 내부 API 키와 함께 실제 MCP 서버로 전달합니다.
    모든 요청/응답은 로깅되어 감사 추적이 가능합니다.
    
    Args:
        request (MCPRequest): MCP 프로토콜 요청
            - jsonrpc: "2.0"
            - method: MCP 메서드 (예: "tools/call")
            - params: 도구 호출 매개변수
            - id: 요청 식별자
        current_user (UserResponse): 인증된 활성 사용자
        mcp_proxy (MCPProxyService): MCP 프록시 서비스
        
    Returns:
        MCPResponse: MCP 서버 응답
            - jsonrpc: "2.0"
            - result: 성공 시 결과 데이터
            - error: 실패 시 에러 정보
            - id: 요청과 동일한 식별자
            
    처리 과정:
        1. 사용자 인증 및 활성 상태 확인
        2. 요청하는 도구에 대한 권한 검증
        3. 내부 API 키로 MCP 서버 인증
        4. 요청 전달 및 응답 수신
        5. 응답 로깅 및 클라이언트 반환
        
    보안 특징:
        - JWT 토큰 기반 사용자 인증
        - 역할 기반 도구 접근 권한 검증
        - 내부 API 키로 MCP 서버 보호
        - 모든 요청/응답 구조화된 로깅
        - 에러 정보 필터링으로 정보 유출 방지
    """
    logger.info(
        "MCP 요청 수신",
        user_id=current_user.id,
        method=request.method,
        tool_name=request.params.get("name") if request.params else None,
    )
    
    # 요청 전달
    response = await mcp_proxy.forward_request(
        request=request,
        user_roles=current_user.roles,
    )
    
    # 에러 로깅
    if response.error:
        logger.warning(
            "MCP 요청 처리 실패",
            user_id=current_user.id,
            error=response.error,
        )
    
    return response


@app.post("/mcp/batch", response_model=list[MCPResponse])
async def proxy_batch_mcp_requests(
    requests: list[MCPRequest],
    current_user: Annotated[UserResponse, Depends(get_current_active_user)],
    mcp_proxy: Annotated[MCPProxyService, Depends(get_mcp_proxy_service)],
):
    """배치 MCP 요청 프록시"""
    logger.info(
        "배치 MCP 요청 수신",
        user_id=current_user.id,
        request_count=len(requests),
    )
    
    responses = await mcp_proxy.batch_forward_requests(
        requests=requests,
        user_roles=current_user.roles,
    )
    
    return responses


# === 사용자 검색 엔드포인트 ===

@app.get("/api/v1/users/search", response_model=list[UserResponse])
async def search_users(
    current_user: Annotated[UserResponse, Depends(get_current_active_user)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
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
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
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


# === 관리자 엔드포인트 ===

@app.get("/api/v1/admin/users", response_model=list[UserResponse])
async def list_users(
    current_user: Annotated[UserResponse, Depends(require_admin)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
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
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
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