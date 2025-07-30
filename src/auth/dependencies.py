"""
MCP 서버 인증 시스템 FastAPI 의존성 주입 모듈

이 모듈은 FastAPI의 의존성 주입(Dependency Injection) 시스템을 활용하여
MCP 서버의 인증, 권한 관리, 서비스 인스턴스 생성을 담당합니다.
싱글톤 패턴을 사용하여 서비스 인스턴스를 효율적으로 관리합니다.

주요 기능:
    - JWT Bearer 토큰 기반 인증
    - 역할 기반 접근 제어 (RBAC)
    - 서비스 인스턴스 싱글톤 관리
    - 사용자 권한 검증 미들웨어
    - MCP 프록시 서비스 의존성 제공

의존성 체계:
    1. get_auth_service(): 인증 서비스 (싱글톤)
    2. get_current_user(): JWT 토큰으로 사용자 인증
    3. get_current_active_user(): 활성화된 사용자만 허용
    4. RoleChecker: 역할 기반 권한 검증
    5. get_rbac_service(): 권한 관리 서비스
    6. get_mcp_proxy_service(): MCP 프록시 서비스

사용 패턴:
    ```python
    @app.get("/protected")
    async def protected_route(
        user: UserResponse = Depends(get_current_active_user)
    ):
        return {"user": user.email}
    
    @app.get("/admin-only")
    async def admin_route(
        user: UserResponse = Depends(require_admin)
    ):
        return {"message": "Admin access granted"}
    ```

작성일: 2024-01-30
"""

from typing import Annotated, TYPE_CHECKING

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .models import UserResponse
from .services import AuthService, AuthenticationError

if TYPE_CHECKING:
    from .services import RBACService, MCPProxyService


# HTTP Bearer 토큰 인증 스키마 정의
# Authorization 헤더에서 "Bearer <token>" 형식으로 토큰을 추출
security = HTTPBearer()


# 싱글톤 패턴을 위한 전역 인스턴스 저장소
# 애플리케이션 생명주기 동안 하나의 인스턴스만 유지하여 메모리 효율성 향상
_user_repository = None  # 사용자 데이터 저장소 인스턴스
_jwt_service = None      # JWT 토큰 관리 서비스 인스턴스
_auth_service = None     # 통합 인증 서비스 인스턴스


def get_auth_service() -> AuthService:
    """
    인증 서비스 의존성 제공 (싱글톤 패턴)
    
    애플리케이션 전체에서 단일 AuthService 인스턴스를 공유하여 메모리 효율성과
    상태 일관성을 보장합니다. 지연 초기화(Lazy Initialization) 패턴으로
    최초 호출 시에만 인스턴스를 생성합니다.
    
    싱글톤 구현 특징:
        - 전역 변수를 사용한 간단한 싱글톤 패턴
        - 스레드 안전성은 GIL에 의존 (FastAPI는 단일 스레드)
        - 애플리케이션 재시작 시 인스턴스 초기화
        
    의존성 체인:
        1. 환경 변수에서 JWT 설정 로드
        2. InMemoryUserRepository 생성 (또는 DB 기반 Repository)
        3. JWTService 생성 (토큰 관리)
        4. AuthService 생성 (통합 인증 로직)
        
    환경 변수:
        - JWT_SECRET_KEY: JWT 서명용 비밀 키 (필수)
        - ACCESS_TOKEN_EXPIRE_MINUTES: 액세스 토큰 만료 시간 (기본값: 30분)
        - REFRESH_TOKEN_EXPIRE_MINUTES: 리프레시 토큰 만료 시간 (기본값: 7일)
        
    Returns:
        AuthService: 인증 서비스 싱글톤 인스턴스
        
    보안 고려사항:
        - JWT_SECRET_KEY는 production에서 반드시 변경 필요
        - 비밀 키는 최소 32자 이상의 무작위 문자열 권장
        - 토큰 만료 시간은 보안과 사용성의 균형 고려
    """
    global _user_repository, _jwt_service, _auth_service
    
    # 이미 생성된 인스턴스가 있으면 재사용 (싱글톤)
    if _auth_service is None:
        # 순환 임포트 방지를 위한 지연 임포트
        from .repositories import InMemoryUserRepository
        from .services import JWTService
        import os
        
        # 환경 변수에서 JWT 비밀 키 로드
        jwt_secret = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
        
        # 사용자 저장소 인스턴스 생성 (싱글톤)
        if _user_repository is None:
            _user_repository = InMemoryUserRepository()
        
        # JWT 서비스 인스턴스 생성 (싱글톤)
        if _jwt_service is None:
            _jwt_service = JWTService(
                secret_key=jwt_secret,
                access_token_expire_minutes=30,        # 30분 액세스 토큰
                refresh_token_expire_minutes=60 * 24 * 7,  # 7일 리프레시 토큰
            )
        
        # 인증 서비스 인스턴스 생성 (의존성 주입)
        _auth_service = AuthService(
            user_repository=_user_repository,
            jwt_service=_jwt_service,
        )
    
    return _auth_service


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> UserResponse:
    """
    JWT Bearer 토큰으로 현재 인증된 사용자 조회
    
    HTTP Authorization 헤더에서 추출한 JWT 토큰을 검증하여 현재 사용자 정보를 반환합니다.
    FastAPI의 의존성 주입을 활용하여 인증이 필요한 모든 엔드포인트에서 사용됩니다.
    
    인증 과정:
        1. Authorization 헤더에서 "Bearer <token>" 추출
        2. JWT 토큰 서명 및 만료 시간 검증
        3. 토큰에서 사용자 ID 추출
        4. 데이터베이스에서 사용자 정보 조회
        5. 사용자 활성 상태 확인
        6. 안전한 사용자 정보 반환 (비밀번호 제외)
    
    Args:
        credentials (HTTPAuthorizationCredentials): FastAPI security에서 추출한 인증 정보
            - scheme: "Bearer"
            - credentials: JWT 토큰 문자열
        auth_service (AuthService): 인증 서비스 인스턴스 (의존성 주입)
            
    Returns:
        UserResponse: 현재 사용자 정보
            - id: 사용자 고유 ID
            - email: 사용자 이메일 
            - is_active: 계정 활성화 상태
            - roles: 사용자 역할 목록
            - created_at, updated_at: 타임스탬프
            
    Raises:
        HTTPException 401: 인증 실패 시
            - 잘못된 토큰 형식
            - 만료된 토큰
            - 토큰 서명 검증 실패
            - 사용자 불존재
            - 계정 비활성화
            
    HTTP 응답 헤더:
        - WWW-Authenticate: "Bearer" (인증 실패 시)
        
    사용 예시:
        ```python
        @app.get("/profile")
        async def get_profile(
            user: UserResponse = Depends(get_current_user)
        ):
            return {"email": user.email, "roles": user.roles}
        ```
        
    보안 특징:
        - 토큰 무결성 검증 (서명 확인)
        - 토큰 만료 시간 자동 검증
        - 사용자 존재 여부 실시간 확인
        - 민감 정보 제외한 안전한 응답
    """
    try:
        # AuthService를 통해 토큰 검증 및 사용자 조회
        return await auth_service.get_current_user(credentials.credentials)
    except AuthenticationError as e:
        # 인증 실패 시 HTTP 401 응답 (RFC 7235 준수)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},  # 클라이언트에게 Bearer 토큰 요구 명시
        )


async def get_current_active_user(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
) -> UserResponse:
    """
    현재 활성화된 사용자만 허용하는 의존성
    
    get_current_user()를 기반으로 추가 검증을 수행하여 활성화된 사용자만 접근을 허용합니다.
    비활성화된 계정으로는 보호된 리소스에 접근할 수 없도록 하는 보안 계층입니다.
    
    사용 시나리오:
        - 일반 사용자 기능 접근 (프로필 조회, 검색 등)
        - 비활성화된 계정의 기능 제한
        - 관리자에 의한 계정 정지 효과 적용
        - 사용자 스스로 계정 비활성화 시 제한
        
    의존성 체인:
        1. get_current_user(): JWT 토큰 검증 및 사용자 조회
        2. get_current_active_user(): 활성화 상태 추가 검증
        
    Args:
        current_user (UserResponse): get_current_user()에서 반환된 사용자 정보
            이미 JWT 토큰 검증과 사용자 존재 확인이 완료된 상태
            
    Returns:
        UserResponse: 활성화된 사용자 정보 (입력과 동일)
        
    Raises:
        HTTPException 403 Forbidden: 계정이 비활성화된 경우
            - 관리자에 의한 계정 정지
            - 사용자 스스로 계정 비활성화
            - 보안상 이유로 계정 차단
            
    HTTP 상태 코드:
        - 401 vs 403 구분: 401은 인증 실패, 403은 권한 부족
        - 이미 인증된 사용자이지만 권한(활성 상태)이 부족한 상황
        
    사용 예시:
        ```python
        @app.get("/dashboard")
        async def get_dashboard(
            user: UserResponse = Depends(get_current_active_user)
        ):
            # 활성화된 사용자만 대시보드 접근 가능
            return {"message": f"Welcome {user.email}"}
        ```
        
    계정 비활성화 시나리오:
        - 사용자의 계정 정지 요청
        - 보안 위반으로 인한 관리자 조치
        - 장기간 미사용 계정 자동 비활성화
        - 결제 실패 등으로 인한 서비스 일시 중지
    """
    # 사용자 활성화 상태 검증
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="계정이 비활성화되었습니다",
        )
    return current_user


def get_rbac_service() -> "RBACService":
    """
    역할 기반 접근 제어(RBAC) 서비스 의존성
    
    사용자의 역할과 권한을 관리하는 RBAC 서비스 인스턴스를 제공합니다.
    매번 새로운 인스턴스를 생성하는 팩토리 패턴을 사용합니다.
    
    RBAC 기능:
        - 사용자 역할 검증
        - 도구별 접근 권한 확인
        - 계층적 권한 구조 지원
        - 동적 권한 부여/회수
        
    Returns:
        RBACService: 역할 기반 접근 제어 서비스 인스턴스
        
    Note:
        현재는 매번 새 인스턴스를 생성하지만, 필요시 싱글톤으로 변경 가능
    """
    from .services import RBACService
    
    return RBACService()


def get_mcp_proxy_service() -> "MCPProxyService":
    """
    MCP 프록시 서비스 의존성
    
    인증된 요청을 실제 MCP 서버로 프록시하는 서비스를 제공합니다.
    사용자 인증과 권한 검증을 거친 후 MCP 서버의 도구들을 안전하게 호출할 수 있게 합니다.
    
    프록시 기능:
        - JWT 토큰을 Internal API Key로 변환
        - 사용자별 도구 접근 권한 검증
        - MCP 서버로 요청 전달 및 응답 반환
        - 요청/응답 로깅 및 감사
        
    환경 변수:
        - MCP_SERVER_URL: 실제 MCP 서버 주소 (기본값: http://localhost:8001)
        - MCP_INTERNAL_API_KEY: MCP 서버 내부 인증키 (필수)
        
    의존성:
        - RBACService: 권한 검증을 위한 RBAC 서비스
        
    Returns:
        MCPProxyService: MCP 프록시 서비스 인스턴스
        
    보안 특징:
        - 사용자 토큰을 내부 API 키로 안전하게 교환
        - 요청별 권한 검증
        - 민감한 정보 필터링
        - 요청 추적 및 로깅
    """
    from .services import MCPProxyService
    import os
    
    # 환경 변수에서 MCP 서버 설정 로드
    mcp_server_url = os.getenv("MCP_SERVER_URL", "http://localhost:8001")
    internal_api_key = os.getenv("MCP_INTERNAL_API_KEY", "")
    
    # RBAC 서비스 인스턴스 생성
    rbac_service = get_rbac_service()
    
    # MCP 프록시 서비스 생성
    return MCPProxyService(
        mcp_server_url=mcp_server_url,
        rbac_service=rbac_service,
        internal_api_key=internal_api_key,
    )


class RoleChecker:
    """
    역할 기반 접근 제어를 위한 FastAPI 의존성 클래스
    
    특정 역할을 가진 사용자만 접근할 수 있는 엔드포인트를 구현하기 위한
    callable 클래스입니다. FastAPI의 의존성 주입 시스템과 함께 사용되어
    세밀한 권한 제어를 제공합니다.
    
    RBAC 구현 특징:
        - 여러 역할 허용 (OR 조건)
        - 계층적 권한 구조 지원
        - 명확한 에러 메시지 제공
        - FastAPI 의존성으로 재사용 가능
        
    사용 패턴:
        ```python
        # 관리자만 접근 가능
        @app.delete("/users/{user_id}")
        async def delete_user(
            user_id: str,
            current_user: UserResponse = Depends(require_admin)
        ):
            pass
            
        # 일반 사용자 또는 관리자 접근 가능
        @app.get("/profile") 
        async def get_profile(
            current_user: UserResponse = Depends(require_user)
        ):
            pass
        ```
        
    권한 계층:
        - admin: 최고 관리자 (모든 권한)
        - user: 일반 사용자 (기본 기능)
        - guest: 게스트 (제한된 기능)
    """
    
    def __init__(self, allowed_roles: list[str]) -> None:
        """
        역할 확인자 초기화
        
        허용할 역할 목록을 설정하여 RoleChecker 인스턴스를 생성합니다.
        여러 역할을 허용하면 OR 조건으로 동작합니다.
        
        Args:
            allowed_roles (list[str]): 접근을 허용할 역할 목록
                예: ["admin"], ["user", "admin"], ["guest", "user", "admin"]
                
        권한 설계 원칙:
            - 최소 권한 원칙: 필요한 최소한의 역할만 허용
            - 명시적 허용: 허용할 역할을 명확히 지정
            - 계층 구조: 상위 역할은 하위 역할의 권한 포함
        """
        self.allowed_roles = allowed_roles
    
    def __call__(
        self,
        current_user: Annotated[UserResponse, Depends(get_current_active_user)],
    ) -> UserResponse:
        """
        사용자 역할 검증 및 접근 허용 판단
        
        현재 사용자의 역할이 허용된 역할 목록에 포함되는지 확인합니다.
        하나라도 일치하면 접근을 허용하고, 모두 일치하지 않으면 403 에러를 발생시킵니다.
        
        Args:
            current_user (UserResponse): get_current_active_user()에서 반환된 활성 사용자
                이미 인증과 활성화 상태 검증이 완료된 상태
                
        Returns:
            UserResponse: 권한이 확인된 현재 사용자 정보
            
        Raises:
            HTTPException 403 Forbidden: 필요한 역할이 없는 경우
                - detail: 구체적인 에러 메시지 (필요한 역할 명시)
                - 보안상 현재 사용자의 역할은 노출하지 않음
                
        권한 검증 로직:
            1. 사용자의 모든 역할과 허용된 역할 비교
            2. 교집합이 있으면 접근 허용
            3. 교집합이 없으면 403 에러
            
        예시:
            - 사용자 역할: ["user"]
            - 허용된 역할: ["user", "admin"]  
            - 결과: 접근 허용 (user 역할 일치)
            
            - 사용자 역할: ["guest"]
            - 허용된 역할: ["admin"]
            - 결과: 403 에러 (일치하는 역할 없음)
        """
        # 사용자의 역할 중 하나라도 허용된 역할에 포함되면 접근 허용
        if not any(role in self.allowed_roles for role in current_user.roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"권한이 없습니다. 필요한 역할: {', '.join(self.allowed_roles)}",
            )
        return current_user


# 미리 정의된 역할별 의존성 인스턴스들
# 일반적인 권한 패턴을 쉽게 사용할 수 있도록 제공

# 관리자 전용 (최고 권한)
require_admin = RoleChecker(["admin"])

# 일반 사용자 이상 (user 또는 admin 역할)
# 대부분의 기본 기능에 사용
require_user = RoleChecker(["user", "admin"])

# 게스트 이상 (모든 역할 허용)
# 공개적이지만 인증이 필요한 기능에 사용
require_guest = RoleChecker(["guest", "user", "admin"])