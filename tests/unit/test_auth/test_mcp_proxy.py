"""MCP 프록시 서비스 테스트"""

from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
import httpx
from httpx import Response

from src.auth.services.mcp_proxy import MCPProxyService, MCPRequest, MCPResponse
from src.auth.services.rbac_service import RBACService, PermissionDeniedError
from src.auth.models import ResourceType, ActionType


class TestMCPProxyService:
    """MCP 프록시 서비스 테스트"""

    @pytest.fixture
    def mock_rbac_service(self) -> Mock:
        """Mock RBACService"""
        return Mock(spec=RBACService)

    @pytest.fixture
    def mcp_proxy_service(self, mock_rbac_service: Mock) -> MCPProxyService:
        """MCPProxyService 픽스처"""
        return MCPProxyService(
            mcp_server_url="http://localhost:8001",
            rbac_service=mock_rbac_service,
        )

    @pytest.fixture
    def sample_mcp_request(self) -> MCPRequest:
        """샘플 MCP 요청"""
        return MCPRequest(
            jsonrpc="2.0",
            id=1,
            method="tools/call",
            params={
                "name": "search_web",
                "arguments": {
                    "query": "Python FastAPI tutorial",
                },
            },
        )

    @pytest.mark.asyncio
    async def test_forward_request_success(
        self,
        mcp_proxy_service: MCPProxyService,
        mock_rbac_service: Mock,
        sample_mcp_request: MCPRequest,
    ) -> None:
        """요청 전달 성공 테스트"""
        # Given
        user_roles = ["user", "admin"]
        mock_rbac_service.check_tool_permission.return_value = True
        
        mock_response_data = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": "Search results for Python FastAPI tutorial",
                    }
                ],
            },
        }
        
        # Mock httpx client
        with patch.object(mcp_proxy_service, "_http_client") as mock_client:
            mock_response = Mock(spec=Response)
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status = Mock()
            
            mock_client.post = AsyncMock(return_value=mock_response)

            # When
            response = await mcp_proxy_service.forward_request(
                request=sample_mcp_request,
                user_roles=user_roles,
            )

            # Then
            assert isinstance(response, MCPResponse)
            assert response.id == sample_mcp_request.id
            assert response.result is not None
            assert "content" in response.result
            
            mock_rbac_service.check_tool_permission.assert_called_once_with(
                user_roles,
                "search_web",
            )
            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_forward_request_permission_denied(
        self,
        mcp_proxy_service: MCPProxyService,
        mock_rbac_service: Mock,
        sample_mcp_request: MCPRequest,
    ) -> None:
        """권한 없는 요청 전달 테스트"""
        # Given
        user_roles = ["guest"]
        mock_rbac_service.check_tool_permission.return_value = False

        # When
        response = await mcp_proxy_service.forward_request(
            request=sample_mcp_request,
            user_roles=user_roles,
        )

        # Then
        assert isinstance(response, MCPResponse)
        assert response.error is not None
        assert response.error["code"] == -32603  # Internal error
        assert "권한이 없습니다" in response.error["message"]
        assert response.result is None

    @pytest.mark.asyncio
    async def test_forward_request_non_tool_method(
        self,
        mcp_proxy_service: MCPProxyService,
        mock_rbac_service: Mock,
    ) -> None:
        """도구 호출이 아닌 메서드 전달 테스트"""
        # Given
        request = MCPRequest(
            jsonrpc="2.0",
            id=1,
            method="initialize",
            params={},
        )
        user_roles = ["user"]
        
        mock_response_data = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "protocolVersion": "1.0",
                "capabilities": {},
            },
        }
        
        with patch.object(mcp_proxy_service, "_http_client") as mock_client:
            mock_response = Mock(spec=Response)
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status = Mock()
            
            mock_client.post = AsyncMock(return_value=mock_response)

            # When
            response = await mcp_proxy_service.forward_request(
                request=request,
                user_roles=user_roles,
            )

            # Then
            assert response.result is not None
            # 권한 확인이 호출되지 않아야 함
            mock_rbac_service.check_tool_permission.assert_not_called()

    @pytest.mark.asyncio
    async def test_forward_request_mcp_server_error(
        self,
        mcp_proxy_service: MCPProxyService,
        mock_rbac_service: Mock,
        sample_mcp_request: MCPRequest,
    ) -> None:
        """MCP 서버 오류 처리 테스트"""
        # Given
        user_roles = ["admin"]
        mock_rbac_service.check_tool_permission.return_value = True
        
        with patch.object(mcp_proxy_service, "_http_client") as mock_client:
            mock_client.post = AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "Server error",
                    request=Mock(),
                    response=Mock(status_code=500),
                )
            )

            # When
            response = await mcp_proxy_service.forward_request(
                request=sample_mcp_request,
                user_roles=user_roles,
            )

            # Then
            assert response.error is not None
            assert response.error["code"] == -32603
            assert "MCP 서버 오류" in response.error["message"]

    @pytest.mark.asyncio
    async def test_forward_request_network_error(
        self,
        mcp_proxy_service: MCPProxyService,
        mock_rbac_service: Mock,
        sample_mcp_request: MCPRequest,
    ) -> None:
        """네트워크 오류 처리 테스트"""
        # Given
        user_roles = ["admin"]
        mock_rbac_service.check_tool_permission.return_value = True
        
        with patch.object(mcp_proxy_service, "_http_client") as mock_client:
            mock_client.post = AsyncMock(
                side_effect=httpx.ConnectError("Connection failed")
            )

            # When
            response = await mcp_proxy_service.forward_request(
                request=sample_mcp_request,
                user_roles=user_roles,
            )

            # Then
            assert response.error is not None
            assert response.error["code"] == -32603
            assert "MCP 서버에 연결할 수 없습니다" in response.error["message"]

    @pytest.mark.asyncio
    async def test_forward_request_invalid_tool_name(
        self,
        mcp_proxy_service: MCPProxyService,
        mock_rbac_service: Mock,
    ) -> None:
        """잘못된 도구 이름 처리 테스트"""
        # Given
        request = MCPRequest(
            jsonrpc="2.0",
            id=1,
            method="tools/call",
            params={
                # name이 없는 경우
                "arguments": {"query": "test"},
            },
        )
        user_roles = ["admin"]

        # When
        response = await mcp_proxy_service.forward_request(
            request=request,
            user_roles=user_roles,
        )

        # Then
        assert response.error is not None
        assert response.error["code"] == -32602  # Invalid params
        assert "도구 이름이 필요합니다" in response.error["message"]

    @pytest.mark.asyncio
    async def test_batch_forward_requests(
        self,
        mcp_proxy_service: MCPProxyService,
        mock_rbac_service: Mock,
    ) -> None:
        """배치 요청 전달 테스트"""
        # Given
        requests = [
            MCPRequest(
                jsonrpc="2.0",
                id=1,
                method="tools/call",
                params={"name": "search_web", "arguments": {"query": "Python"}},
            ),
            MCPRequest(
                jsonrpc="2.0",
                id=2,
                method="tools/call",
                params={"name": "search_vectors", "arguments": {"query": "FastAPI"}},
            ),
        ]
        user_roles = ["admin"]
        
        # 첫 번째는 허용, 두 번째는 거부
        mock_rbac_service.check_tool_permission.side_effect = [True, False]
        
        mock_response_data = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"type": "text", "text": "Python results"}]},
        }
        
        with patch.object(mcp_proxy_service, "_http_client") as mock_client:
            mock_response = Mock(spec=Response)
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status = Mock()
            
            mock_client.post = AsyncMock(return_value=mock_response)

            # When
            responses = await mcp_proxy_service.batch_forward_requests(
                requests=requests,
                user_roles=user_roles,
            )

            # Then
            assert len(responses) == 2
            
            # 첫 번째 요청은 성공
            assert responses[0].result is not None
            assert responses[0].error is None
            
            # 두 번째 요청은 권한 오류
            assert responses[1].result is None
            assert responses[1].error is not None
            assert "권한이 없습니다" in responses[1].error["message"]

    @pytest.mark.asyncio
    async def test_validate_request_headers(
        self,
        mcp_proxy_service: MCPProxyService,
    ) -> None:
        """요청 헤더 검증 테스트"""
        # Given
        headers = {
            "content-type": "application/json",
            "authorization": "Bearer token123",
            "x-custom-header": "value",
        }

        # When
        validated_headers = mcp_proxy_service.validate_request_headers(headers)

        # Then
        assert "content-type" in validated_headers
        assert "authorization" not in validated_headers  # 민감한 헤더 제거
        assert "x-custom-header" in validated_headers

    def test_extract_tool_name_from_params(
        self,
        mcp_proxy_service: MCPProxyService,
    ) -> None:
        """파라미터에서 도구 이름 추출 테스트"""
        # Given
        params_with_name = {"name": "search_web", "arguments": {}}
        params_without_name = {"arguments": {}}
        params_none = None

        # When & Then
        assert mcp_proxy_service._extract_tool_name(params_with_name) == "search_web"
        assert mcp_proxy_service._extract_tool_name(params_without_name) is None
        assert mcp_proxy_service._extract_tool_name(params_none) is None

    @pytest.mark.asyncio
    async def test_connection_pooling(
        self,
        mcp_proxy_service: MCPProxyService,
        mock_rbac_service: Mock,
        sample_mcp_request: MCPRequest,
    ) -> None:
        """HTTP 연결 풀링 테스트"""
        # Given
        user_roles = ["admin"]
        mock_rbac_service.check_tool_permission.return_value = True
        
        # When - 여러 요청을 보내 연결 재사용 확인
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            
            mock_response = Mock(spec=Response)
            mock_response.status_code = 200
            mock_response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": {}}
            mock_response.raise_for_status = Mock()
            
            mock_client.post = AsyncMock(return_value=mock_response)
            
            # 새 인스턴스로 클라이언트 재생성
            proxy = MCPProxyService(
                mcp_server_url="http://localhost:8001",
                rbac_service=mock_rbac_service,
            )
            
            # 여러 요청 전송
            for _ in range(3):
                await proxy.forward_request(sample_mcp_request, user_roles)
            
            # Then - 클라이언트는 한 번만 생성되어야 함
            mock_client_class.assert_called_once()