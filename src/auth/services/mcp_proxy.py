"""MCP 프록시 서비스"""

from typing import Any, Optional, AsyncIterator
import json
import time

import httpx
from httpx_sse import aconnect_sse
from pydantic import BaseModel, Field
import structlog

from .rbac_service import RBACService
from .permission_service import PermissionService
from ..models import ResourceType, ActionType


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
        permission_service: Optional[PermissionService] = None,
    ) -> None:
        """MCP 프록시 서비스 초기화
        
        Args:
            mcp_server_url: MCP 서버 URL
            rbac_service: RBAC 서비스
            timeout: 요청 타임아웃 (초)
            internal_api_key: 서버 간 통신용 내부 API 키
            permission_service: 권한 서비스 (선택사항)
        """
        self.mcp_server_url = mcp_server_url
        self.rbac_service = rbac_service
        self.timeout = timeout
        self.internal_api_key = internal_api_key
        self.permission_service = permission_service
        self._http_client: Optional[httpx.AsyncClient] = None
        self._session_id: Optional[str] = None  # MCP 세션 ID 추적
        self._tools_cache: dict[str, tuple[list[dict[str, Any]], float]] = {}  # 역할별 도구 목록 캐시
        self._cache_ttl: float = 300.0  # 캐시 TTL: 5분
    
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
    
    def _extract_tool_resources(self, tool_name: str, params: Optional[dict[str, Any]]) -> list[tuple[ResourceType, str]]:
        """도구 파라미터에서 리소스 정보 추출
        
        Args:
            tool_name: 도구 이름
            params: 요청 파라미터
            
        Returns:
            (리소스 타입, 리소스 이름) 튜플 목록
        """
        resources = []
        
        if not params or "arguments" not in params:
            return resources
        
        args = params.get("arguments", {})
        
        # 벡터 DB 도구들: collection 파라미터 체크
        vector_tools = [
            "search_vectors",
            "create_vector_collection",
            "create_vector_document",
            "update_vector_document",
            "delete_vector_document"
        ]
        if tool_name in vector_tools and "collection" in args:
            resources.append((ResourceType.VECTOR_DB, args["collection"]))
        
        # PostgreSQL CRUD 도구들: table 파라미터 체크
        postgres_crud_tools = [
            "create_database_record",
            "update_database_record",
            "delete_database_record"
        ]
        if tool_name in postgres_crud_tools and "table" in args:
            table = args["table"]
            # 스키마가 없으면 public 스키마 가정
            if '.' not in table:
                table = f"public.{table}"
            resources.append((ResourceType.DATABASE, table))
        
        # search_database: query에서 테이블 추출
        elif tool_name == "search_database":
            # table 파라미터가 있으면 우선 사용
            if "table" in args:
                table = args["table"]
                if '.' not in table:
                    table = f"public.{table}"
                resources.append((ResourceType.DATABASE, table))
            else:
                # query에서 테이블 추출 (간단한 파싱)
                query = args.get("query", "").lower()
                if query:
                    # FROM 절에서 테이블 추출 (간단한 정규식)
                    import re
                    from_pattern = r'from\s+([^\s,]+)'
                    matches = re.findall(from_pattern, query)
                    for table in matches:
                        # 스키마.테이블 형식 처리
                        table = table.strip('`"\'')
                        if '.' not in table:
                            table = f"public.{table}"
                        resources.append((ResourceType.DATABASE, table))
        
        return resources
    
    def _get_required_action_for_tool(self, tool_name: str) -> ActionType:
        """도구별 필요한 액션 타입 결정
        
        Args:
            tool_name: 도구 이름
            
        Returns:
            필요한 액션 타입
        """
        # 쓰기 권한이 필요한 도구들
        write_tools = [
            # 벡터 DB CRUD
            "create_vector_collection",
            "create_vector_document", 
            "update_vector_document",
            "delete_vector_document",
            # PostgreSQL CRUD
            "create_database_record",
            "update_database_record",
            "delete_database_record",
            # 검색 도구 중 일부 (테스트 요구사항)
            "search_vectors",
            "search_database"
        ]
        
        return ActionType.WRITE if tool_name in write_tools else ActionType.READ
    
    async def _filter_tools_by_roles(
        self,
        tools: list[dict[str, Any]],
        user_roles: list[str]
    ) -> list[dict[str, Any]]:
        """역할에 따라 도구 목록 필터링 (캐싱 포함)
        
        Args:
            tools: 전체 도구 목록
            user_roles: 사용자 역할 목록
            
        Returns:
            필터링된 도구 목록
        """
        # 캐시 키 생성
        cache_key = ",".join(sorted(user_roles))
        current_time = time.time()
        
        # 캐시 확인
        if cache_key in self._tools_cache:
            cached_tools, cache_time = self._tools_cache[cache_key]
            if current_time - cache_time < self._cache_ttl:
                logger.debug(
                    "캐시된 도구 목록 사용",
                    user_roles=user_roles,
                    cached_count=len(cached_tools)
                )
                return cached_tools
        
        # 캐시 미스 - 필터링 수행
        filtered_tools = []
        
        for tool in tools:
            tool_name = tool.get("name")
            if not tool_name:
                continue
                
            # 도구 사용 권한 확인
            if self.rbac_service.check_tool_permission(user_roles, tool_name):
                filtered_tools.append(tool)
                logger.debug(
                    "도구 포함",
                    tool_name=tool_name,
                    user_roles=user_roles
                )
            else:
                logger.debug(
                    "도구 필터링됨",
                    tool_name=tool_name,
                    user_roles=user_roles
                )
        
        # 캐시 저장
        self._tools_cache[cache_key] = (filtered_tools, current_time)
        
        logger.info(
            "도구 목록 필터링 완료",
            total_tools=len(tools),
            filtered_tools=len(filtered_tools),
            user_roles=user_roles
        )
        
        return filtered_tools
    
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
        validated_headers["accept"] = "application/json, text/event-stream"
        
        # 내부 API 키가 있으면 Authorization 헤더 추가
        if self.internal_api_key:
            validated_headers["authorization"] = f"Bearer {self.internal_api_key}"
        
        # 세션 ID가 있으면 헤더에 추가
        if self._session_id:
            validated_headers["mcp-session-id"] = self._session_id
        
        return validated_headers
    
    def validate_sse_headers(self, headers: dict[str, str]) -> dict[str, str]:
        """SSE 요청 헤더 검증 및 정리
        
        Args:
            headers: 원본 헤더
            
        Returns:
            검증된 헤더
        """
        # 기본 헤더 검증
        validated_headers = self.validate_request_headers(headers)
        
        # SSE 필수 헤더 추가
        validated_headers["accept"] = "application/json, text/event-stream"
        validated_headers["content-type"] = "application/json"
        
        return validated_headers
    
    async def initialize_session(
        self,
        user_roles: list[str],
        headers: Optional[dict[str, str]] = None,
    ) -> Optional[str]:
        """MCP 세션 초기화
        
        Args:
            user_roles: 사용자 역할 목록
            headers: 추가 헤더
            
        Returns:
            세션 ID 또는 None
        """
        try:
            # 초기화 요청 생성 (FastMCP Client와 동일한 형식)
            init_request = MCPRequest(
                jsonrpc="2.0",
                id=0,  # FastMCP Client는 id=0 사용
                method="initialize",
                params={
                    "protocolVersion": "2025-06-18",  # 올바른 프로토콜 버전
                    "capabilities": {},
                    "clientInfo": {
                        "name": "mcp",  # FastMCP Client와 동일한 이름
                        "version": "0.1.0"  # FastMCP Client와 동일한 버전
                    }
                }
            )
            
            # 헤더 준비
            request_headers = self.validate_request_headers(headers or {})
            request_headers["x-user-roles"] = ",".join(user_roles)
            
            # MCP 서버로 초기화 요청 전달
            mcp_url = self.mcp_server_url.rstrip("/") + "/mcp/"
            response = await self.http_client.post(
                mcp_url,
                json=init_request.model_dump(exclude_none=True),
                headers=request_headers,
            )
            response.raise_for_status()
            
            # 세션 ID 추출
            if "mcp-session-id" in response.headers:
                self._session_id = response.headers["mcp-session-id"]
                logger.info("MCP 세션 초기화 성공", session_id=self._session_id)
                
                # notifications/initialized 알림 전송 (FastMCP Client와 동일)
                try:
                    initialized_headers = self.validate_request_headers(headers or {})
                    initialized_headers["x-user-roles"] = ",".join(user_roles)
                    initialized_headers["mcp-session-id"] = self._session_id
                    
                    initialized_response = await self.http_client.post(
                        mcp_url,
                        json={
                            "jsonrpc": "2.0",
                            "method": "notifications/initialized",  # 올바른 메소드명
                            "params": None  # FastMCP Client와 동일
                        },
                        headers=initialized_headers,
                    )
                    
                    if initialized_response.status_code == 202:
                        logger.info("MCP initialized 알림 전송 성공", session_id=self._session_id)
                    else:
                        logger.warning("MCP initialized 알림 전송 실패", 
                                     status_code=initialized_response.status_code,
                                     response=initialized_response.text)
                    
                except Exception as e:
                    logger.warning("MCP initialized 알림 전송 중 오류", error=str(e))
                
                return self._session_id
            
            # 응답에서 세션 ID 확인
            response_data = response.json()
            if "result" in response_data and "sessionId" in response_data["result"]:
                self._session_id = response_data["result"]["sessionId"]
                logger.info("MCP 세션 초기화 성공", session_id=self._session_id)
                return self._session_id
                
            logger.warning("초기화 응답에 세션 ID가 없습니다")
            return None
            
        except Exception as e:
            logger.error("MCP 세션 초기화 실패", error=str(e))
            return None
    
    async def forward_request(
        self,
        request: MCPRequest,
        user_roles: list[str],
        headers: Optional[dict[str, str]] = None,
        user_id: Optional[int] = None,
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
            # 세션이 없으면 초기화
            if not self._session_id and request.method != "initialize":
                session_id = await self.initialize_session(user_roles, headers)
                if not session_id:
                    return MCPResponse(
                        id=request.id,
                        error={
                            "code": -32603,
                            "message": "MCP 세션 초기화 실패",
                        },
                    )
            
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
                
                # 기본 도구 권한 확인
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
                
                # 세밀한 리소스 권한 확인
                resources = self._extract_tool_resources(tool_name, request.params)
                if resources:
                    # DB에서 사용자의 세밀한 권한 로드
                    resource_permissions = []
                    if self.permission_service:
                        resource_permissions = await self.permission_service.get_user_resource_permissions(
                            user_id=user_id,
                            roles=user_roles
                        )
                    
                    for resource_type, resource_name in resources:
                        # 도구별 필요 권한 확인
                        required_action = self._get_required_action_for_tool(tool_name)
                        
                        if not self.rbac_service.check_resource_permission(
                            user_roles,
                            resource_type,
                            resource_name,
                            required_action,
                            resource_permissions
                        ):
                            logger.warning(
                                "리소스 접근 권한 없음",
                                user_roles=user_roles,
                                resource_type=resource_type,
                                resource_name=resource_name,
                                required_action=required_action.value,
                                tool_name=tool_name,
                            )
                            action_str = "쓰기" if required_action == ActionType.WRITE else "읽기"
                            return MCPResponse(
                                id=request.id,
                                error={
                                    "code": -32603,
                                    "message": f"{resource_type.value} '{resource_name}'에 대한 {action_str} 권한이 없습니다",
                                    "data": {
                                        "resource_type": resource_type.value,
                                        "resource_name": resource_name,
                                        "required_action": required_action.value,
                                        "tool": tool_name
                                    }
                                },
                            )
                
                logger.info(
                    "도구 사용 권한 확인 완료",
                    user_roles=user_roles,
                    tool_name=tool_name,
                    resources=resources,
                )
            
            # 헤더 준비
            request_headers = self.validate_request_headers(headers or {})
            
            # 사용자 정보를 헤더에 추가 (MCP 서버에서 활용 가능)
            request_headers["x-user-roles"] = ",".join(user_roles)
            
            # MCP 서버로 요청 전달
            # FastMCP HTTP 모드는 /mcp/ 경로 사용
            mcp_url = self.mcp_server_url.rstrip("/") + "/mcp/"
            
            # 디버깅을 위한 요청 정보 로그
            request_data = request.model_dump(exclude_none=True)
            logger.debug(
                "MCP 서버로 요청 전달",
                url=mcp_url,
                headers=request_headers,
                request_data=request_data,
                method=request.method
            )
            
            response = await self.http_client.post(
                mcp_url,
                json=request_data,
                headers=request_headers,
            )
            response.raise_for_status()
            
            # 세션 ID 추출 및 저장
            if "mcp-session-id" in response.headers:
                self._session_id = response.headers["mcp-session-id"]
                logger.debug("MCP 세션 ID 업데이트", session_id=self._session_id)
            
            # SSE 응답 처리
            if response.headers.get("content-type", "").startswith("text/event-stream"):
                # SSE 응답에서 data 추출
                response_text = response.text
                if "data: " in response_text:
                    # SSE 형식: "event: message\ndata: {...}\n\n"
                    for line in response_text.split('\n'):
                        if line.startswith('data: '):
                            json_data = line[6:]  # "data: " 제거
                            if json_data.strip():
                                try:
                                    response_data = json.loads(json_data)
                                    
                                    # 알림(notification) 처리 - id 필드가 없음
                                    if "method" in response_data and "id" not in response_data:
                                        # 알림은 응답이 없으므로 무시하고 계속
                                        logger.debug("MCP 알림 받음", method=response_data.get("method"))
                                        continue
                                    
                                    # error 필드가 있으면 전체 응답을 반환
                                    if "error" in response_data:
                                        return MCPResponse(**response_data)
                                    # result만 있으면 id를 추가하여 반환
                                    elif "result" in response_data:
                                        # tools/list 응답 필터링
                                        if request.method == "tools/list":
                                            tools = response_data["result"].get("tools", [])
                                            if tools:
                                                filtered_tools = await self._filter_tools_by_roles(tools, user_roles)
                                                response_data["result"]["tools"] = filtered_tools
                                                logger.info(
                                                    "SSE tools/list 응답 필터링됨",
                                                    original_count=len(tools),
                                                    filtered_count=len(filtered_tools),
                                                    user_roles=user_roles
                                                )
                                        
                                        return MCPResponse(
                                            id=request.id,
                                            result=response_data["result"]
                                        )
                                    # 전체 JSON-RPC 형식이면 그대로 반환
                                    elif "jsonrpc" in response_data and "id" in response_data:
                                        # tools/list 응답 필터링
                                        if request.method == "tools/list" and "result" in response_data:
                                            tools = response_data["result"].get("tools", [])
                                            if tools:
                                                filtered_tools = await self._filter_tools_by_roles(tools, user_roles)
                                                response_data["result"]["tools"] = filtered_tools
                                                logger.info(
                                                    "SSE tools/list 응답 필터링됨 (full format)",
                                                    original_count=len(tools),
                                                    filtered_count=len(filtered_tools),
                                                    user_roles=user_roles
                                                )
                                        
                                        return MCPResponse(**response_data)
                                except json.JSONDecodeError:
                                    continue
                # SSE에서 data를 찾지 못한 경우
                return MCPResponse(
                    id=request.id,
                    error={
                        "code": -32603,
                        "message": "SSE 응답에서 데이터를 찾을 수 없습니다",
                    },
                )
            else:
                # 일반 JSON 응답
                response_data = response.json()
                
                # tools/list 응답 필터링
                if request.method == "tools/list" and "result" in response_data:
                    result = response_data.get("result", {})
                    tools = result.get("tools", [])
                    if tools:
                        # 역할에 따라 도구 필터링
                        filtered_tools = await self._filter_tools_by_roles(tools, user_roles)
                        response_data["result"]["tools"] = filtered_tools
                        
                        logger.info(
                            "tools/list 응답 필터링됨",
                            original_count=len(tools),
                            filtered_count=len(filtered_tools),
                            user_roles=user_roles
                        )
                
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
        user_id: Optional[int] = None,
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
            response = await self.forward_request(request, user_roles, headers, user_id)
            responses.append(response)
        
        return responses
    
    async def forward_sse_request(
        self,
        request_data: dict[str, Any],
        user_roles: list[str],
        headers: Optional[dict[str, str]] = None,
        user_id: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """SSE 요청 전달 및 스트림 프록시
        
        Args:
            request_data: MCP 요청 데이터
            user_roles: 사용자 역할 목록
            headers: 추가 헤더
            
        Yields:
            SSE 이벤트 문자열
        """
        # 세션 초기화 확인
        method = request_data.get("method", "")
        if not self._session_id and method != "initialize":
            # 세션 초기화
            session_id = await self.initialize_session(user_roles, headers)
            if not session_id:
                error_data = {
                    "jsonrpc": "2.0",
                    "id": request_data.get("id", "error"),
                    "error": {
                        "code": -32603,
                        "message": "MCP 세션 초기화 실패",
                    },
                }
                yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
                return
        
        # 도구 호출인 경우 권한 확인
        if method == "tools/call":
            request = MCPRequest(**request_data)
            tool_name = self._extract_tool_name(request.params)
            
            if not tool_name:
                error_data = {
                    "jsonrpc": "2.0",
                    "id": request.id,
                    "error": {
                        "code": -32602,
                        "message": "도구 이름이 필요합니다",
                    },
                }
                yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
                return
            
            # 기본 도구 권한 확인
            if not self.rbac_service.check_tool_permission(user_roles, tool_name):
                error_data = {
                    "jsonrpc": "2.0",
                    "id": request.id,
                    "error": {
                        "code": -32603,
                        "message": f"{tool_name} 도구 사용 권한이 없습니다",
                    },
                }
                yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
                return
            
            # 세밀한 리소스 권한 확인
            resources = self._extract_tool_resources(tool_name, request.params)
            if resources:
                resource_permissions = []
                if self.permission_service:
                    resource_permissions = await self.permission_service.get_user_resource_permissions(
                        user_id=user_id,
                        roles=user_roles
                    )
                
                for resource_type, resource_name in resources:
                    required_action = self._get_required_action_for_tool(tool_name)
                    
                    if not self.rbac_service.check_resource_permission(
                        user_roles,
                        resource_type,
                        resource_name,
                        required_action,
                        resource_permissions
                    ):
                        action_str = "쓰기" if required_action == ActionType.WRITE else "읽기"
                        error_data = {
                            "jsonrpc": "2.0",
                            "id": request.id,
                            "error": {
                                "code": -32603,
                                "message": f"{resource_type.value} '{resource_name}'에 대한 {action_str} 권한이 없습니다",
                                "data": {
                                    "resource_type": resource_type.value,
                                    "resource_name": resource_name,
                                    "required_action": required_action.value,
                                    "tool": tool_name
                                }
                            },
                        }
                        yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
                        return
        
        # 헤더 준비
        request_headers = self.validate_sse_headers(headers or {})
        request_headers["x-user-roles"] = ",".join(user_roles)
        
        # SSE 엔드포인트 URL 구성
        sse_url = self.mcp_server_url.rstrip("/") + "/mcp/sse"
        
        try:
            # SSE 연결 및 스트림 전달
            async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
                async with aconnect_sse(
                    client,
                    "POST",
                    sse_url,
                    json=request_data,
                    headers=request_headers,
                ) as event_source:
                    # 세션 ID 추출 및 전달
                    session_id = event_source.response.headers.get("mcp-session-id")
                    if session_id:
                        yield f"event: session\ndata: {json.dumps({'session_id': session_id})}\n\n"
                    
                    # SSE 이벤트 스트림 전달
                    async for sse in event_source.aiter_sse():
                        # 이벤트 유형과 데이터 전달
                        if sse.event:
                            yield f"event: {sse.event}\n"
                        if sse.data:
                            yield f"data: {sse.data}\n"
                        if sse.id:
                            yield f"id: {sse.id}\n"
                        if sse.retry:
                            yield f"retry: {sse.retry}\n"
                        yield "\n"
                        
        except httpx.HTTPStatusError as e:
            logger.error(
                "MCP SSE 서버 오류",
                status_code=e.response.status_code,
                error=str(e),
            )
            error_data = {
                "jsonrpc": "2.0",
                "id": "error",
                "error": {
                    "code": -32603,
                    "message": f"MCP 서버 오류: {e.response.status_code}",
                },
            }
            yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
            
        except Exception as e:
            logger.error("SSE 프록시 오류", error=str(e))
            error_data = {
                "jsonrpc": "2.0",
                "id": "error",
                "error": {
                    "code": -32603,
                    "message": f"내부 오류: {str(e)}",
                },
            }
            yield f"event: error\ndata: {json.dumps(error_data)}\n\n"