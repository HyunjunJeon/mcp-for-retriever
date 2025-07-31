"""
FastMCP 표준 Bearer Token Verifier 구현

이 모듈은 FastMCP의 표준 인증 방식에 따라 JWT 토큰과 내부 API 키를 검증합니다.
기존 미들웨어 방식을 대체하여 FastMCP의 BearerAuthProvider와 함께 사용됩니다.

주요 기능:
    - JWT Bearer 토큰 검증
    - 내부 API 키 검증
    - 사용자 정보 및 권한 추출
    - 토큰 만료 및 유효성 검사

작성일: 2024-01-31
"""

from typing import Optional, List, Callable
from datetime import datetime, timezone

from fastmcp.server.auth.providers.bearer import AccessToken
import structlog

from .services.jwt_service import JWTService
from .models import TokenData


logger = structlog.get_logger(__name__)


class JWTBearerVerifier:
    """
    JWT Bearer 토큰 검증기
    
    FastMCP의 BearerAuthProvider와 함께 사용하여 JWT 토큰을 검증합니다.
    내부 API 키도 함께 지원하여 서비스간 인증을 처리합니다.
    """
    
    def __init__(
        self,
        jwt_service: JWTService,
        internal_api_key: str,
        require_auth: bool = True
    ):
        """
        JWT Bearer 검증기 초기화
        
        Args:
            jwt_service: JWT 토큰 검증 서비스
            internal_api_key: 서비스간 통신용 내부 API 키
            require_auth: 인증 필수 여부 (False여도 잘못된 토큰은 거부)
        """
        self.jwt_service = jwt_service
        self.internal_api_key = internal_api_key
        self.require_auth = require_auth
        
        logger.info(
            "JWT Bearer Verifier 초기화",
            require_auth=require_auth
        )
    
    async def verify(self, token: str) -> Optional[AccessToken]:
        """
        Bearer 토큰 검증
        
        FastMCP의 표준에 따라 토큰을 검증하고 AccessToken 객체를 반환합니다.
        
        Args:
            token: Bearer 토큰 문자열
            
        Returns:
            Optional[AccessToken]: 검증 성공 시 AccessToken, 실패 시 None
            
        중요:
            - require_auth가 False여도 잘못된 토큰이 제공되면 None 반환
            - 토큰이 없을 때만 require_auth 설정에 따라 처리
        """
        # 토큰이 없는 경우
        if not token:
            if self.require_auth:
                logger.warning("인증 토큰이 제공되지 않음")
                return None
            else:
                # require_auth=False이고 토큰이 없으면 익명 접근 허용
                logger.debug("익명 접근 허용")
                return AccessToken(
                    token="anonymous",
                    client_id="anonymous",
                    scopes=["tools:read"],  # 기본 읽기 권한만 부여
                    expires_at=None
                )
        
        # 내부 API 키 확인
        if token == self.internal_api_key:
            logger.info("내부 API 키 인증 성공")
            return AccessToken(
                token=token,
                client_id="internal-service",
                scopes=["*"],  # 모든 권한
                expires_at=None
            )
        
        # JWT 토큰 검증
        try:
            # JWT 디코드 및 검증
            token_data = self.jwt_service.decode_token(token)
            
            if token_data is None:
                logger.warning("JWT 토큰 검증 실패")
                return None
            
            # 액세스 토큰만 허용
            if token_data.token_type != "access":
                logger.warning(
                    "잘못된 토큰 타입",
                    token_type=token_data.token_type,
                    expected="access"
                )
                return None
            
            # 역할을 스코프로 변환
            scopes = self._roles_to_scopes(token_data.roles)
            
            logger.info(
                "JWT 인증 성공",
                user_id=token_data.user_id,
                email=token_data.email,
                roles=token_data.roles,
                scopes=scopes
            )
            
            # FastMCP AccessToken 생성
            # JWT claims를 resource 필드에 JSON으로 인코딩
            import json
            claims_data = {
                "email": token_data.email,
                "roles": token_data.roles,
                "sub": token_data.sub,
                "token_type": token_data.token_type
            }
            
            return AccessToken(
                token=token,
                client_id=token_data.user_id,
                scopes=scopes,
                expires_at=int(token_data.exp) if token_data.exp else None,
                resource=json.dumps(claims_data)  # JWT claims를 JSON으로 저장
            )
            
        except Exception as e:
            logger.error(
                "예상치 못한 토큰 검증 오류",
                error=str(e),
                error_type=type(e).__name__
            )
            return None
    
    def _roles_to_scopes(self, roles: List[str]) -> List[str]:
        """
        역할을 FastMCP 스코프로 변환
        
        Args:
            roles: 사용자 역할 목록
            
        Returns:
            List[str]: FastMCP 스코프 목록
        """
        scopes = set()
        
        # 기본 도구 읽기 권한
        scopes.add("tools:read")
        scopes.add("tools:list")
        
        for role in roles:
            if role == "admin":
                # 관리자는 모든 권한
                scopes.add("*")
                scopes.add("tools:write")
                scopes.add("tools:delete")
                scopes.add("resources:read")
                scopes.add("resources:write")
                scopes.add("prompts:read")
                scopes.add("prompts:write")
            elif role == "user":
                # 일반 사용자는 도구 실행 권한
                scopes.add("tools:call")
                scopes.add("resources:read")
                scopes.add("prompts:read")
            elif role == "guest":
                # 게스트는 읽기 권한만
                scopes.add("resources:read")
        
        return list(scopes)


class CompositeVerifier:
    """
    복합 토큰 검증기
    
    여러 검증기를 순차적으로 시도하여 첫 번째 성공한 결과를 반환합니다.
    JWT와 다른 인증 방식을 함께 사용할 때 유용합니다.
    """
    
    def __init__(self, verifiers: List[JWTBearerVerifier]):
        """
        복합 검증기 초기화
        
        Args:
            verifiers: 시도할 검증기 목록 (순서대로 시도)
        """
        self.verifiers = verifiers
        logger.info(
            "복합 토큰 검증기 초기화",
            verifier_count=len(verifiers)
        )
    
    async def verify(self, token: str) -> Optional[AccessToken]:
        """
        여러 검증기를 순차적으로 시도
        
        Args:
            token: 검증할 토큰
            
        Returns:
            Optional[AccessToken]: 첫 번째 성공한 검증 결과
        """
        for verifier in self.verifiers:
            try:
                result = await verifier.verify(token)
                if result is not None:
                    return result
            except Exception as e:
                logger.warning(
                    "검증기 실행 중 오류",
                    verifier=type(verifier).__name__,
                    error=str(e)
                )
                continue
        
        return None