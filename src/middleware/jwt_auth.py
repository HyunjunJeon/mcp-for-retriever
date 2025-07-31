"""
JWT 토큰 직접 검증 미들웨어

이 모듈은 MCP 서버에서 JWT 토큰을 직접 검증하는 FastMCP 미들웨어를 구현합니다.
기존 Auth Gateway를 통한 프록시 방식을 대체하여 JWT 토큰을 로컬에서 직접 검증합니다.

주요 기능:
    토큰 검증:
        - Authorization 헤더에서 Bearer 토큰 추출
        - JWTService를 사용한 토큰 서명 및 만료 검증
        - 내부 API 키 지원 (서비스간 인증)
        
    사용자 컨텍스트 설정:
        - 검증된 사용자 정보를 미들웨어 컨텍스트에 저장
        - 사용자 ID, 이메일, 역할 정보 포함
        - 인증 타입 및 시각 기록
        
    FastMCP 통합:
        - FastMCP Middleware 기본 클래스 상속
        - on_message 훅을 통한 모든 요청 인터셉트
        - MiddlewareContext를 통한 요청 정보 접근
        
    다중 인증 모드:
        - 사용자 인증: JWT Bearer 토큰
        - 서비스 인증: 내부 API 키  
        - 익명 접근: 선택적 허용 (health_check 등)

아키텍처:
    - JWTService: JWT 토큰 생성/검증 재사용
    - FastMCP Middleware: 프로토콜 레벨 요청 인터셉트
    - 구조화된 로깅: 감사 추적
    - 에러 처리: JSON-RPC 2.0 호환 응답

작성일: 2024-01-30
"""

from typing import Any, Optional
from datetime import datetime, timezone

from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.exceptions import McpError
from mcp.types import ErrorData
import structlog

from ..auth.services.jwt_service import JWTService
from ..auth.models import TokenData


logger = structlog.get_logger(__name__)


class JWTAuthMiddleware(Middleware):
    """
    JWT 토큰 직접 검증 미들웨어
    
    FastMCP Middleware 기본 클래스를 상속받아 JWT 토큰 검증 기능을 제공합니다.
    기존 Auth Gateway 프록시 방식을 대체하여 JWT 토큰을 로컬에서 직접 검증하고
    사용자 컨텍스트를 설정합니다.
    
    검증 프로세스:
        1. on_message 훅에서 모든 MCP 요청 인터셉트
        2. Authorization 헤더에서 Bearer 토큰 추출
        3. 내부 API 키 확인 (서비스간 인증)
        4. JWT 토큰인 경우 JWTService로 검증
        5. 검증 성공 시 사용자 정보를 컨텍스트에 저장
        6. call_next()로 다음 미들웨어에 전달
        
    지원하는 인증 타입:
        - Bearer JWT: 일반 사용자 인증
        - Internal API Key: 서비스간 인증
        - Anonymous: 인증 없는 접근 (선택적)
    """
    
    def __init__(
        self,
        jwt_service: JWTService,
        internal_api_key: str,
        require_auth: bool = True,
        skip_auth_methods: Optional[list[str]] = None
    ) -> None:
        """
        JWT 인증 미들웨어 초기화
        
        Args:
            jwt_service (JWTService): JWT 토큰 검증 서비스
                기존 JWTService 인스턴스를 재사용하여
                토큰 생성/검증 로직 일관성 보장
                
            internal_api_key (str): 서비스간 통신용 내부 API 키
                예: "mcp-internal-key-12345"
                MCP 서버간 또는 내부 서비스간 인증에 사용
                
            require_auth (bool): 모든 요청에 대한 인증 필수 여부
                True: 모든 요청이 인증 필요 (기본값)
                False: 특정 메서드는 익명 접근 허용
                
            skip_auth_methods (Optional[list[str]]): 인증을 건너뛸 메서드 목록
                기본값: ["tools/list", "health_check"]
                개발/테스트 환경에서 유용
                
        초기화 과정:
            - 의존성 서비스 저장 및 검증
            - 인증 정책 설정
            - 로깅 컨텍스트 설정
        """
        super().__init__()
        self.jwt_service = jwt_service
        self.internal_api_key = internal_api_key
        self.require_auth = require_auth
        
        # 기본적으로 인증을 건너뛸 메서드들
        self.skip_auth_methods = skip_auth_methods or [
            "tools/list",      # 도구 목록 조회
            "health_check",    # 헬스 체크
        ]
        
        logger.info(
            "JWT 인증 미들웨어 초기화",
            require_auth=require_auth,
            skip_auth_methods=self.skip_auth_methods
        )
    
    async def on_message(
        self, 
        context: MiddlewareContext[Any], 
        call_next
    ) -> Any:
        """
        모든 MCP 메시지에 대한 JWT 인증 처리
        
        FastMCP의 on_message 훅을 구현하여 모든 MCP 요청을 인터셉트하고
        JWT 토큰 검증을 수행합니다. 검증 성공 시 사용자 정보를 컨텍스트에 추가하고
        다음 미들웨어로 요청을 전달합니다.
        
        Args:
            context (MiddlewareContext[Any]): FastMCP 미들웨어 컨텍스트
                - context.method: MCP 메서드명 (예: "tools/call")
                - context.message: 실제 MCP 메시지 데이터
                - context.timestamp: 요청 수신 시각
                - context.fastmcp_context: FastMCP 서버 컨텍스트
                
            call_next: 다음 미들웨어 호출 함수
                
        Returns:
            Any: 다음 미들웨어의 응답 또는 에러 응답
                성공 시: 다음 핸들러의 응답
                실패 시: McpError 예외 발생
                
        인증 플로우:
            1. 메서드별 인증 건너뛰기 확인
            2. Authorization 헤더 추출
            3. 내부 API 키 확인 (서비스간 인증)
            4. JWT 토큰 검증 (사용자 인증)
            5. 사용자 정보를 컨텍스트에 저장
            6. 다음 미들웨어로 전달
            
        예외 처리:
            - 인증 실패: McpError(-32603, "Authentication failed")
            - 토큰 만료: McpError(-32603, "Token expired")
            - 내부 오류: McpError(-32603, "Internal authentication error")
        """
        # 로깅을 위한 메서드명 추출
        method = getattr(context, 'method', 'unknown')
        
        logger.debug(
            "JWT 인증 처리 시작",
            method=method,
            message_type=getattr(context, 'type', 'unknown'),
            timestamp=getattr(context, 'timestamp', None)
        )
        
        # 설정에 따라 특정 메서드는 인증 건너뛰기
        if not self.require_auth and method in self.skip_auth_methods:
            logger.debug(
                "인증 건너뛰기",
                method=method,
                reason="skip_auth_methods"
            )
            # 익명 사용자 정보 설정
            await self._set_anonymous_user_context(context)
            return await call_next(context)
        
        # Authorization 헤더 추출 시도
        auth_header = await self._extract_auth_header(context)
        
        # 인증 헤더가 없는 경우
        if not auth_header:
            if self.require_auth:
                logger.warning(
                    "인증 헤더 누락",
                    method=method,
                    require_auth=self.require_auth
                )
                raise McpError(ErrorData(code=-32603, message="Missing authorization header"))
            else:
                # 익명 접근 허용
                logger.debug("익명 접근 허용", method=method)
                await self._set_anonymous_user_context(context)
                return await call_next(context)
        
        # Bearer 토큰에서 토큰 추출
        if not auth_header.startswith("Bearer "):
            logger.warning(
                "잘못된 Authorization 헤더 형식",
                method=method,
                auth_header_prefix=auth_header[:20] if auth_header else None
            )
            raise McpError(ErrorData(code=-32603, message="Invalid authorization header format"))
        
        token = auth_header[7:]  # "Bearer " 제거
        
        # 내부 API 키 확인 (서비스간 인증) - JWT 검증 전에 확인
        if token == self.internal_api_key:
            logger.info(
                "서비스 인증 성공",
                method=method,
                service="internal"
            )
            await self._set_service_user_context(context)
            return await call_next(context)
        
        # JWT 토큰 검증 (사용자 인증)
        try:
            logger.debug(
                "JWT 토큰 검증 시작",
                method=method,
                token_prefix=token[:20] if token else None,
                jwt_secret_available=bool(self.jwt_service)
            )
            
            # JWTService를 사용한 토큰 검증
            token_data = self.jwt_service.decode_token(token)
            
            logger.debug(
                "JWT 토큰 검증 결과",
                method=method,
                token_data_type=type(token_data).__name__ if token_data else None,
                token_data_content=str(token_data) if token_data else None
            )
            
            if token_data is None:
                logger.warning(
                    "JWT 토큰 검증 실패 - 토큰 데이터가 None",
                    method=method,
                    token_prefix=token[:20] if token else None
                )
                raise McpError(ErrorData(code=-32603, message="Invalid or expired JWT token"))
            
            # 액세스 토큰만 허용 (리프레시 토큰 거부)
            if token_data.token_type != "access":
                logger.warning(
                    "잘못된 토큰 타입",
                    method=method,
                    token_type=token_data.token_type,
                    expected="access"
                )
                raise McpError(ErrorData(code=-32603, message="Access token required"))
            
            # 사용자 컨텍스트 설정
            await self._set_jwt_user_context(context, token_data)
            
            logger.info(
                "JWT 인증 성공",
                method=method,
                user_id=token_data.user_id,
                user_email=token_data.email,
                roles=token_data.roles
            )
            
            return await call_next(context)
            
        except McpError:
            # McpError는 그대로 재발생
            raise
        except Exception as e:
            # 예상치 못한 오류 처리
            logger.error(
                "예상치 못한 인증 오류",
                error=str(e),
                error_type=type(e).__name__,
                method=method
            )
            raise McpError(ErrorData(code=-32603, message="Internal authentication error"))
    
    async def _extract_auth_header(self, context: MiddlewareContext[Any]) -> Optional[str]:
        """
        MiddlewareContext에서 Authorization 헤더 추출
        
        FastMCP HTTP 모드에서는 헤더 정보가 제한적일 수 있습니다.
        현재 구현에서는 테스트를 위해 임시로 None을 반환합니다.
        
        Args:
            context: FastMCP 미들웨어 컨텍스트
            
        Returns:
            Optional[str]: Authorization 헤더 값 또는 None
        """
        try:
            # 간단한 디버깅 로그
            logger.debug(
                "헤더 추출 시도",
                context_type=type(context).__name__,
                has_fastmcp_context=hasattr(context, 'fastmcp_context')
            )
            
            # TODO: FastMCP HTTP 헤더 접근 방법 구현 필요
            # 현재는 HTTP 모드에서 헤더 추출이 제한적이므로
            # 임시로 None을 반환하여 require_auth=False 정책 적용
            
            logger.debug("HTTP 헤더 추출 제한으로 인해 None 반환")
            return None
            
        except Exception as e:
            logger.error(
                "Authorization 헤더 추출 중 오류",
                error=str(e),
                error_type=type(e).__name__
            )
            return None
    
    async def _set_anonymous_user_context(self, context: MiddlewareContext[Any]) -> None:
        """
        익명 사용자 컨텍스트 설정
        
        인증이 필요하지 않은 요청에 대해 익명 사용자 정보를 설정합니다.
        
        Args:
            context: 사용자 정보를 설정할 미들웨어 컨텍스트
        """
        user_info = {
            "type": "anonymous",
            "authenticated_at": datetime.now(timezone.utc).isoformat(),
            "permissions": []
        }
        
        # 컨텍스트에 사용자 정보 저장 - 더 안전한 방법 사용
        try:
            if not hasattr(context, 'user_info'):
                object.__setattr__(context, 'user_info', user_info)
            logger.debug("익명 사용자 컨텍스트 설정 완료")
        except Exception as e:
            logger.warning("익명 사용자 컨텍스트 설정 실패", error=str(e))
            # 컨텍스트 설정에 실패해도 진행 - 인증 정보는 선택적
    
    async def _set_service_user_context(self, context: MiddlewareContext[Any]) -> None:
        """
        서비스 사용자 컨텍스트 설정
        
        내부 API 키를 통한 서비스간 인증에 대해 서비스 사용자 정보를 설정합니다.
        
        Args:
            context: 사용자 정보를 설정할 미들웨어 컨텍스트
        """
        user_info = {
            "type": "service",
            "service": "internal",
            "authenticated_at": datetime.now(timezone.utc).isoformat(),
            "permissions": ["admin"]  # 서비스는 관리자 권한
        }
        
        # 컨텍스트에 사용자 정보 저장 - 더 안전한 방법 사용
        try:
            if not hasattr(context, 'user_info'):
                object.__setattr__(context, 'user_info', user_info)
            logger.debug("서비스 사용자 컨텍스트 설정 완료", service="internal")
        except Exception as e:
            logger.warning("서비스 사용자 컨텍스트 설정 실패", error=str(e))
            # 서비스 인증은 중요하므로 오류 발생 시 예외 발생
            raise McpError(ErrorData(code=-32603, message="Failed to set service user context"))
    
    async def _set_jwt_user_context(
        self, 
        context: MiddlewareContext[Any], 
        token_data: TokenData
    ) -> None:
        """
        JWT 토큰 기반 사용자 컨텍스트 설정
        
        검증된 JWT 토큰 데이터를 바탕으로 사용자 정보를 컨텍스트에 설정합니다.
        
        Args:
            context: 사용자 정보를 설정할 미들웨어 컨텍스트
            token_data: 검증된 JWT 토큰 데이터
        """
        user_info = {
            "type": "user",
            "user_id": token_data.user_id,
            "email": token_data.email,
            "roles": token_data.roles,
            "token_type": token_data.token_type,
            "authenticated_at": datetime.now(timezone.utc).isoformat(),
            "token_issued_at": token_data.iat.isoformat() if token_data.iat else None,
            "token_expires_at": token_data.exp.isoformat() if token_data.exp else None,
        }
        
        # 컨텍스트에 사용자 정보 저장 - 더 안전한 방법 사용
        try:
            if not hasattr(context, 'user_info'):
                object.__setattr__(context, 'user_info', user_info)
            logger.debug(
                "JWT 사용자 컨텍스트 설정 완료",
                user_id=token_data.user_id,
                email=token_data.email,
                roles=token_data.roles
            )
        except Exception as e:
            logger.warning(
                "JWT 사용자 컨텍스트 설정 실패", 
                error=str(e),
                user_id=token_data.user_id
            )
            # JWT 사용자 인증은 중요하므로 오류 발생 시 예외 발생
            raise McpError(ErrorData(code=-32603, message="Failed to set JWT user context"))


class AuthorizationMiddleware(Middleware):
    """
    계층적 권한 제어 미들웨어
    
    JWT 인증 미들웨어 다음에 실행되어 사용자의 역할과 권한을 확인하고
    요청된 MCP 작업에 대한 접근 권한을 검증합니다.
    
    권한 검증 프로세스:
        1. 컨텍스트에서 사용자 정보 추출
        2. 요청된 MCP 메서드에 대한 권한 요구사항 확인
        3. RBACService를 통한 역할 기반 권한 검증
        4. 도구별 세부 권한 검증
        5. 권한 없는 경우 접근 거부
        
    지원하는 권한 체계:
        - 역할 기반 접근 제어 (RBAC)
        - 도구별 권한 매핑
        - 계층적 권한 상속
        - 리소스 레벨 권한 제어
    """
    
    def __init__(self, rbac_service) -> None:
        """
        권한 제어 미들웨어 초기화
        
        Args:
            rbac_service: RBAC 서비스 인스턴스
                기존 RBACService를 재사용하여 권한 정책 일관성 보장
        """
        super().__init__()
        self.rbac_service = rbac_service
        
        logger.info("권한 제어 미들웨어 초기화 완료")
    
    async def on_call_tool(
        self, 
        context: MiddlewareContext, 
        call_next
    ) -> Any:
        """
        도구 호출에 대한 권한 검증
        
        사용자가 특정 도구를 호출할 권한이 있는지 확인합니다.
        
        Args:
            context: 미들웨어 컨텍스트 (도구 호출 정보 포함)
            call_next: 다음 미들웨어 호출 함수
            
        Returns:
            도구 실행 결과 또는 권한 거부 오류
            
        Raises:
            McpError: 권한이 없는 경우
        """
        # 사용자 정보 추출
        user_info = getattr(context, 'user_info', None)
        if not user_info:
            logger.error("도구 호출 시 사용자 정보 없음")
            raise McpError(ErrorData(code=-32603, message="Authentication required for tool execution"))
        
        # 도구명 추출
        tool_name = getattr(context.message, 'name', None)
        if not tool_name:
            logger.error("도구 호출 시 도구명 없음")
            raise McpError(ErrorData(code=-32600, message="Tool name is required"))
        
        # 서비스 사용자는 모든 권한 허용
        if user_info.get("type") == "service":
            logger.debug(
                "서비스 사용자 도구 호출 허용",
                tool_name=tool_name,
                service=user_info.get("service")
            )
            return await call_next(context)
        
        # 일반 사용자 권한 확인
        user_roles = user_info.get("roles", [])
        
        # RBAC를 통한 도구 권한 확인
        if not self.rbac_service.check_tool_permission(user_roles, tool_name):
            logger.warning(
                "도구 접근 권한 거부",
                tool_name=tool_name,
                user_id=user_info.get("user_id"),
                user_roles=user_roles
            )
            raise McpError(ErrorData(code=-32603, message=f"Access denied: insufficient permissions for tool '{tool_name}'"))
        
        logger.info(
            "도구 접근 권한 허용",
            tool_name=tool_name,
            user_id=user_info.get("user_id"),
            user_roles=user_roles
        )
        
        return await call_next(context)
    
    async def on_list_tools(
        self, 
        context: MiddlewareContext, 
        call_next
    ) -> Any:
        """
        도구 목록 필터링
        
        사용자가 접근할 수 있는 도구만 목록에 표시합니다.
        
        Args:
            context: 미들웨어 컨텍스트
            call_next: 다음 미들웨어 호출 함수
            
        Returns:
            필터링된 도구 목록
        """
        # 전체 도구 목록 조회
        all_tools = await call_next(context)
        
        # 사용자 정보 추출
        user_info = getattr(context, 'user_info', None)
        if not user_info:
            # 인증되지 않은 사용자는 빈 목록 반환
            logger.debug("인증되지 않은 사용자 - 빈 도구 목록 반환")
            return []
        
        # 서비스 사용자는 모든 도구 접근 가능
        if user_info.get("type") == "service":
            logger.debug("서비스 사용자 - 모든 도구 목록 반환")
            return all_tools
        
        # 일반 사용자는 권한이 있는 도구만 필터링
        user_roles = user_info.get("roles", [])
        
        filtered_tools = []
        for tool in all_tools:
            tool_name = getattr(tool, 'name', None)
            if tool_name and self.rbac_service.check_tool_permission(user_roles, tool_name):
                filtered_tools.append(tool)
        
        logger.info(
            "도구 목록 필터링 완료",
            user_id=user_info.get("user_id"),
            total_tools=len(all_tools),
            accessible_tools=len(filtered_tools)
        )
        
        return filtered_tools