"""MCP 프록시 서비스"""

from typing import Any, Optional

import httpx
from pydantic import BaseModel, Field
import structlog

from .rbac_service import RBACService


logger = structlog.get_logger()


class MCPRequest(BaseModel):
    """MCP 요청 모델"""
    
    jsonrpc: str = "2.0"
    id: int | str
    method: str
    params: Optional[dict[str, Any]] = None


class MCPResponse(BaseModel):
    """MCP 응답 모델"""
    
    jsonrpc: str = "2.0"
    id: int | str
    result: Optional[dict[str, Any]] = None
    error: Optional[dict[str, Any]] = None


class MCPProxyService:
    """MCP 프록시 서비스"""
    
    def __init__(
        self,
        mcp_server_url: str,
        rbac_service: RBACService,
        timeout: float = 30.0,
        internal_api_key: Optional[str] = None,
    ) -> None:
        """MCP 프록시 서비스 초기화
        
        Args:
            mcp_server_url: MCP 서버 URL
            rbac_service: RBAC 서비스
            timeout: 요청 타임아웃 (초)
            internal_api_key: 서버 간 통신용 내부 API 키
        """
        self.mcp_server_url = mcp_server_url
        self.rbac_service = rbac_service
        self.timeout = timeout
        self.internal_api_key = internal_api_key
        self._http_client: Optional[httpx.AsyncClient] = None
    
    @property
    def http_client(self) -> httpx.AsyncClient:
        """HTTP 클라이언트 (lazy initialization)"""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=self.timeout,
                limits=httpx.Limits(
                    max_keepalive_connections=5,
                    max_connections=10,
                ),
            )
        return self._http_client
    
    async def __aenter__(self) -> "MCPProxyService":
        """비동기 컨텍스트 매니저 진입"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """비동기 컨텍스트 매니저 종료"""
        if self._http_client:
            await self._http_client.aclose()
    
    def _extract_tool_name(self, params: Optional[dict[str, Any]]) -> Optional[str]:
        """파라미터에서 도구 이름 추출
        
        Args:
            params: 요청 파라미터
            
        Returns:
            도구 이름 또는 None
        """
        if params and isinstance(params, dict):
            return params.get("name")
        return None
    
    def validate_request_headers(self, headers: dict[str, str]) -> dict[str, str]:
        """요청 헤더 검증 및 정리
        
        Args:
            headers: 원본 헤더
            
        Returns:
            검증된 헤더
        """
        # 민감한 헤더 제거
        sensitive_headers = {"authorization", "cookie", "x-api-key"}
        
        validated_headers = {
            k: v
            for k, v in headers.items()
            if k.lower() not in sensitive_headers
        }
        
        # 필수 헤더 추가
        validated_headers["content-type"] = "application/json"
        
        # 내부 API 키가 있으면 Authorization 헤더 추가
        if self.internal_api_key:
            validated_headers["authorization"] = f"Bearer {self.internal_api_key}"
        
        return validated_headers
    
    async def forward_request(
        self,
        request: MCPRequest,
        user_roles: list[str],
        headers: Optional[dict[str, str]] = None,
    ) -> MCPResponse:
        """MCP 요청 전달
        
        Args:
            request: MCP 요청
            user_roles: 사용자 역할 목록
            headers: 추가 헤더
            
        Returns:
            MCP 응답
        """
        try:
            # 도구 호출인 경우 권한 확인
            if request.method == "tools/call":
                tool_name = self._extract_tool_name(request.params)
                
                if not tool_name:
                    return MCPResponse(
                        id=request.id,
                        error={
                            "code": -32602,
                            "message": "도구 이름이 필요합니다",
                        },
                    )
                
                # 권한 확인
                if not self.rbac_service.check_tool_permission(user_roles, tool_name):
                    logger.warning(
                        "도구 사용 권한 없음",
                        user_roles=user_roles,
                        tool_name=tool_name,
                    )
                    return MCPResponse(
                        id=request.id,
                        error={
                            "code": -32603,
                            "message": f"{tool_name} 도구 사용 권한이 없습니다",
                        },
                    )
                
                logger.info(
                    "도구 사용 권한 확인 완료",
                    user_roles=user_roles,
                    tool_name=tool_name,
                )
            
            # 헤더 준비
            request_headers = self.validate_request_headers(headers or {})
            
            # 사용자 정보를 헤더에 추가 (MCP 서버에서 활용 가능)
            request_headers["x-user-roles"] = ",".join(user_roles)
            
            # MCP 서버로 요청 전달
            response = await self.http_client.post(
                self.mcp_server_url,
                json=request.model_dump(exclude_none=True),
                headers=request_headers,
            )
            response.raise_for_status()
            
            # 응답 변환
            response_data = response.json()
            return MCPResponse(**response_data)
            
        except httpx.HTTPStatusError as e:
            logger.error(
                "MCP 서버 오류",
                status_code=e.response.status_code,
                error=str(e),
            )
            return MCPResponse(
                id=request.id,
                error={
                    "code": -32603,
                    "message": f"MCP 서버 오류: {e.response.status_code}",
                },
            )
            
        except httpx.ConnectError as e:
            logger.error("MCP 서버 연결 실패", error=str(e))
            return MCPResponse(
                id=request.id,
                error={
                    "code": -32603,
                    "message": "MCP 서버에 연결할 수 없습니다",
                },
            )
            
        except Exception as e:
            logger.error("예상치 못한 오류", error=str(e))
            return MCPResponse(
                id=request.id,
                error={
                    "code": -32603,
                    "message": f"내부 오류: {str(e)}",
                },
            )
    
    async def batch_forward_requests(
        self,
        requests: list[MCPRequest],
        user_roles: list[str],
        headers: Optional[dict[str, str]] = None,
    ) -> list[MCPResponse]:
        """배치 요청 전달
        
        Args:
            requests: MCP 요청 목록
            user_roles: 사용자 역할 목록
            headers: 추가 헤더
            
        Returns:
            MCP 응답 목록
        """
        responses = []
        
        for request in requests:
            response = await self.forward_request(request, user_roles, headers)
            responses.append(response)
        
        return responses