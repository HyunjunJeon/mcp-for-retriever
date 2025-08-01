"""
MCP 서버용 인증 미들웨어

이 모듈은 MCP 서버로 들어오는 모든 요청에 대해 JWT 토큰 기반 인증을 수행하는
미들웨어를 구현합니다. 사용자 토큰 검증, 서비스간 인증, 익명 접근 등을 처리합니다.

주요 기능:
    토큰 검증:
        - JWT Bearer 토큰 추출 및 검증
        - 인증 게이트웨이를 통한 토큰 유효성 확인
        - 토큰 만료 및 권한 검사

    다중 인증 모드:
        - 사용자 인증: JWT 토큰 기반 일반 사용자 인증
        - 서비스 인증: 내부 API 키를 통한 서비스간 인증
        - 익명 접근: 특정 메서드에 대한 인증 없는 접근

    요청 컨텍스트 설정:
        - 인증된 사용자 정보를 요청 객체에 추가
        - 사용자 역할 및 권한 정보 포함
        - 인증 시각 및 인증 타입 기록

    에러 처리:
        - JSON-RPC 2.0 호환 에러 응답
        - 인증 실패 시 적절한 HTTP 상태 코드
        - 네트워크 오류 및 서비스 장애 처리

아키텍처:
    - 비동기 HTTP 클라이언트로 인증 게이트웨이 통신
    - 연결 풀링으로 성능 최적화
    - 구조화된 로깅으로 감사 추적
    - Graceful shutdown 지원
"""

from typing import Any, Callable, Dict, Optional
import httpx
import structlog
from datetime import datetime, timezone

logger = structlog.get_logger(__name__)


class AuthMiddleware:
    """
    JWT 토큰 검증 및 사용자 컨텍스트 설정 미들웨어

    모든 MCP 요청에 대해 인증을 수행하고 인증된 사용자 정보를 요청 컨텍스트에 추가합니다.
    내부 서비스 인증, 사용자 토큰 검증, 익명 접근 등 다양한 인증 방식을 지원합니다.

    인증 처리 과정:
        1. Authorization 헤더에서 토큰 추출
        2. 내부 API 키인지 확인 (서비스간 통신)
        3. JWT 토큰인 경우 인증 게이트웨이로 검증
        4. 인증 성공 시 사용자 정보를 요청에 추가
        5. 인증 실패 시 적절한 에러 응답 반환

    지원하는 인증 타입:
        - Bearer JWT: 일반 사용자 인증
        - Internal API Key: 서비스간 인증
        - Anonymous: 인증 없는 접근 (선택적)
    """

    def __init__(
        self, internal_api_key: str, auth_gateway_url: str, require_auth: bool = True
    ):
        """
        인증 미들웨어 초기화

        Args:
            internal_api_key (str): 서비스간 통신용 내부 API 키
                예: "mcp-internal-key-12345"
                MCP 서버간 또는 내부 서비스간 인증에 사용

            auth_gateway_url (str): 인증 게이트웨이 서버 URL
                예: "http://localhost:8000"
                JWT 토큰 검증을 위한 인증 서버 주소

            require_auth (bool): 모든 요청에 대한 인증 필수 여부
                True: 모든 요청이 인증 필요 (기본값)
                False: 특정 메서드는 익명 접근 허용

        초기화 과정:
            - 설정값 저장 및 검증
            - HTTP 클라이언트 지연 초기화 준비
            - 로깅 컨텍스트 설정
        """
        self.internal_api_key = internal_api_key
        self.auth_gateway_url = auth_gateway_url
        self.require_auth = require_auth
        self._http_client: Optional[httpx.AsyncClient] = None

    @property
    def http_client(self) -> httpx.AsyncClient:
        """
        HTTP 클라이언트 지연 초기화

        인증 게이트웨이와 통신하기 위한 비동기 HTTP 클라이언트를 제공합니다.
        메모리 효율성을 위해 실제 사용 시점에 클라이언트를 생성합니다.

        Returns:
            httpx.AsyncClient: 설정된 비동기 HTTP 클라이언트
                - 타임아웃: 10초
                - Keep-alive 연결: 최대 5개
                - 연결 풀링으로 성능 최적화

        성능 특징:
            - 연결 재사용으로 지연 시간 최소화
            - 적절한 타임아웃으로 응답성 보장
            - 메모리 효율적인 연결 관리
        """
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=10.0, limits=httpx.Limits(max_keepalive_connections=5)
            )
        return self._http_client

    async def __call__(
        self, request: Dict[str, Any], call_next: Callable
    ) -> Dict[str, Any]:
        """
        들어오는 요청에 대한 인증 처리

        MCP 요청을 인터셉트하여 인증을 수행하고 사용자 컨텍스트를 설정합니다.
        인증 성공 시 다음 미들웨어로 요청을 전달하고, 실패 시 에러 응답을 반환합니다.

        Args:
            request (Dict[str, Any]): MCP 요청 데이터
                - method: MCP 메서드명
                - headers: HTTP 헤더 딕셔너리
                - params: 요청 매개변수

            call_next (Callable): 다음 미들웨어 또는 핸들러

        Returns:
            Dict[str, Any]: MCP 응답 또는 에러 응답
                성공 시: 다음 핸들러의 응답
                실패 시: JSON-RPC 2.0 에러 응답

        인증 플로우:
            1. 인증 건너뛰는 메서드 확인 (tools/list, health_check)
            2. Authorization 헤더 추출
            3. 내부 API 키 확인 (서비스간 인증)
            4. JWT 토큰인 경우 인증 게이트웨이로 검증
            5. 사용자 정보를 request['user']에 설정
            6. 다음 핸들러로 요청 전달

        에러 처리:
            - 인증 실패: 401 Unauthorized
            - 네트워크 오류: 503 Service Unavailable
            - 내부 오류: 500 Internal Server Error
        """
        # 로깅을 위한 메서드명 추출
        method = request.get("method", "unknown")

        # 설정에 따라 특정 메서드는 인증 건너뛰기
        skip_auth_methods = ["tools/list", "health_check"]
        if not self.require_auth and method in skip_auth_methods:
            return await call_next(request)

        # Authorization 헤더 추출
        headers = request.get("headers", {})
        auth_header = headers.get("authorization", "")

        # 인증 헤더가 없는 경우
        if not auth_header:
            if self.require_auth:
                logger.warning("인증 헤더 누락", method=method)
                return self._unauthorized_response("Missing authorization header")
            else:
                # 익명 접근 허용
                request["user"] = {"type": "anonymous"}
                return await call_next(request)

        # 내부 API 키 확인
        if auth_header == f"Bearer {self.internal_api_key}":
            # 서비스간 인증
            user_info = {
                "type": "service",
                "service": "internal",
                "authenticated_at": datetime.now(timezone.utc).isoformat(),
            }
            request["user"] = user_info

            logger.info("서비스 인증 성공", method=method, service="internal")

            return await call_next(request)

        # 인증 게이트웨이를 통한 토큰 검증
        try:
            response = await self.http_client.get(
                f"{self.auth_gateway_url}/auth/me",
                headers={"Authorization": auth_header},
            )

            if response.status_code == 200:
                user_info = response.json()
                user_info["authenticated_at"] = datetime.now(timezone.utc).isoformat()
                request["user"] = user_info

                logger.info(
                    "사용자 인증 성공",
                    method=method,
                    user_id=user_info.get("id"),
                    user_email=user_info.get("email"),
                )

                return await call_next(request)
            else:
                logger.warning(
                    "인증 실패", method=method, status_code=response.status_code
                )
                return self._unauthorized_response("Invalid or expired token")

        except httpx.RequestError as e:
            logger.error("인증 게이트웨이 연결 실패", error=str(e), method=method)
            return self._service_unavailable_response()
        except Exception as e:
            logger.error("예상치 못한 인증 오류", error=str(e), method=method)
            return self._internal_error_response()

    def _unauthorized_response(self, message: str = "Unauthorized") -> Dict[str, Any]:
        """
        401 Unauthorized 응답 생성

        JWT 토큰이 유효하지 않거나 인증 정보가 없을 때 반환하는 에러 응답을 생성합니다.
        JSON-RPC 2.0 스펙에 따른 표준 에러 형식으로 응답합니다.

        Args:
            message (str): 구체적인 에러 메시지
                예: "Missing authorization header", "Invalid or expired token"

        Returns:
            Dict[str, Any]: JSON-RPC 2.0 에러 응답
                - error.code: -32603 (Internal error)
                - error.message: 에러 메시지
                - error.data.type: "AuthenticationError"
        """
        return {
            "error": {
                "code": -32603,
                "message": message,
                "data": {"type": "AuthenticationError"},
            }
        }

    def _service_unavailable_response(self) -> Dict[str, Any]:
        """
        503 Service Unavailable 응답 생성

        인증 게이트웨이 서버에 연결할 수 없거나 응답하지 않을 때 반환하는 에러 응답입니다.
        네트워크 오류, 서버 다운, 타임아웃 등의 상황에서 사용됩니다.

        Returns:
            Dict[str, Any]: JSON-RPC 2.0 에러 응답
                - error.code: -32603 (Internal error)
                - error.message: "Authentication service unavailable"
                - error.data.type: "ServiceUnavailable"

        사용 시나리오:
            - 인증 게이트웨이 서버 다운
            - 네트워크 연결 실패
            - 요청 타임아웃
            - DNS 해결 실패
        """
        return {
            "error": {
                "code": -32603,
                "message": "Authentication service unavailable",
                "data": {"type": "ServiceUnavailable"},
            }
        }

    def _internal_error_response(self) -> Dict[str, Any]:
        """Create internal error response."""
        return {
            "error": {
                "code": -32603,
                "message": "Internal authentication error",
                "data": {"type": "InternalError"},
            }
        }

    async def close(self):
        """
        리소스 정리 및 연결 해제

        미들웨어 종료 시 HTTP 클라이언트와 관련 리소스를 안전하게 정리합니다.
        Graceful shutdown을 위해 애플리케이션 종료 시 호출되어야 합니다.

        정리 과정:
            1. HTTP 클라이언트 연결 해제
            2. 연결 풀 정리
            3. 미완료 요청 대기
            4. 메모리 정리

        사용 예시:
            ```python
            auth_middleware = AuthMiddleware(...)
            try:
                # 미들웨어 사용
                pass
            finally:
                await auth_middleware.close()
            ```
        """
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
