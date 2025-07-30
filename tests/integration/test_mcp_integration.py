"""MCP server integration tests with authentication flow."""

import asyncio
import os
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import httpx
from fastapi.testclient import TestClient

from src.auth.server import app
from src.server import create_server
from tests.fixtures.mock_retriever import MockRetriever


class TestMCPIntegration:
    """Integration tests for the complete MCP system."""
    
    @pytest.fixture
    async def auth_app(self):
        """Get auth server app for testing."""
        return app
    
    @pytest.fixture
    async def auth_client(self, auth_app):
        """Create test client for auth server."""
        return TestClient(auth_app)
    
    @pytest.fixture
    async def mcp_server(self):
        """Create MCP server instance."""
        return create_server()
    
    @pytest.fixture
    async def mock_retrievers(self):
        """Create mock retrievers for testing."""
        # Mock Tavily retriever
        tavily_mock = MockRetriever({
            "type": "tavily",
            "mock_data": [
                {
                    "title": "Test Result 1",
                    "url": "https://example.com/1",
                    "content": "Test content 1",
                    "score": 0.9,
                    "source": "web"
                }
            ]
        })
        
        # Mock PostgreSQL retriever  
        postgres_mock = MockRetriever({
            "type": "postgres",
            "mock_data": [
                {
                    "id": 1,
                    "name": "Test User",
                    "email": "test@example.com",
                    "source": "database"
                }
            ]
        })
        
        # Mock Qdrant retriever
        qdrant_mock = MockRetriever({
            "type": "qdrant",
            "mock_data": [
                {
                    "id": "vec-1",
                    "text": "Similar document",
                    "score": 0.85,
                    "source": "vectors"
                }
            ]
        })
        
        return {
            "tavily": tavily_mock,
            "postgres": postgres_mock,
            "qdrant": qdrant_mock
        }

    async def test_full_user_flow(self, auth_client, mock_retrievers):
        """Test complete user flow from registration to API usage."""
        # 1. 사용자 등록
        register_response = auth_client.post(
            "/api/v1/auth/register",
            json={
                "email": "test@example.com",
                "password": "StrongPassword123!",
                "name": "Test User"
            }
        )
        assert register_response.status_code == 201
        user_data = register_response.json()
        assert user_data["email"] == "test@example.com"
        assert "id" in user_data
        
        # 2. 로그인 및 토큰 발급
        login_response = auth_client.post(
            "/api/v1/auth/token",
            data={
                "username": "test@example.com",
                "password": "StrongPassword123!"
            }
        )
        assert login_response.status_code == 200
        token_data = login_response.json()
        assert "access_token" in token_data
        assert "refresh_token" in token_data
        assert token_data["token_type"] == "bearer"
        
        access_token = token_data["access_token"]
        
        # 3. MCP 서버 모의 설정
        with patch('src.server.retrievers', mock_retrievers):
            # 4. Web 검색 요청 (search_web)
            web_search_request = {
                "jsonrpc": "2.0",
                "method": "search_web",
                "params": {
                    "query": "test query",
                    "limit": 5
                },
                "id": 1
            }
            
            web_response = auth_client.post(
                "/api/v1/mcp/execute",
                json=web_search_request,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            assert web_response.status_code == 200
            web_result = web_response.json()
            assert web_result["jsonrpc"] == "2.0"
            assert web_result["id"] == 1
            assert "result" in web_result
            assert web_result["result"]["status"] == "success"
            assert len(web_result["result"]["results"]) == 1
            assert web_result["result"]["results"][0]["source"] == "web"
            
            # 5. Database 검색 요청 (search_database)
            db_search_request = {
                "jsonrpc": "2.0",
                "method": "search_database",
                "params": {
                    "query": "SELECT * FROM users",
                    "limit": 10
                },
                "id": 2
            }
            
            db_response = auth_client.post(
                "/api/v1/mcp/execute",
                json=db_search_request,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            assert db_response.status_code == 200
            db_result = db_response.json()
            assert db_result["result"]["status"] == "success"
            assert db_result["result"]["results"][0]["source"] == "database"
            
            # 6. Vector 검색 요청 (search_vectors)
            vector_search_request = {
                "jsonrpc": "2.0",
                "method": "search_vectors",
                "params": {
                    "query": "similar text",
                    "collection": "documents",
                    "limit": 5,
                    "score_threshold": 0.7
                },
                "id": 3
            }
            
            vector_response = auth_client.post(
                "/api/v1/mcp/execute",
                json=vector_search_request,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            assert vector_response.status_code == 200
            vector_result = vector_response.json()
            assert vector_result["result"]["status"] == "success"
            assert vector_result["result"]["results"][0]["source"] == "vectors"
            
            # 7. 모든 소스 동시 검색 (search_all)
            all_search_request = {
                "jsonrpc": "2.0",
                "method": "search_all",
                "params": {
                    "query": "comprehensive search",
                    "limit": 5
                },
                "id": 4
            }
            
            all_response = auth_client.post(
                "/api/v1/mcp/execute",
                json=all_search_request,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            assert all_response.status_code == 200
            all_result = all_response.json()
            assert all_result["result"]["status"] == "success"
            assert "results" in all_result["result"]
            assert len(all_result["result"]["results"]) == 3  # All three sources
            
            # 8. 배치 요청 테스트
            batch_request = [
                {
                    "jsonrpc": "2.0",
                    "method": "search_web",
                    "params": {"query": "batch test 1", "limit": 3},
                    "id": 5
                },
                {
                    "jsonrpc": "2.0",
                    "method": "search_database",
                    "params": {"query": "SELECT * FROM products", "limit": 5},
                    "id": 6
                }
            ]
            
            batch_response = auth_client.post(
                "/api/v1/mcp/execute",
                json=batch_request,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            assert batch_response.status_code == 200
            batch_results = batch_response.json()
            assert isinstance(batch_results, list)
            assert len(batch_results) == 2
            assert all(r["jsonrpc"] == "2.0" for r in batch_results)
            
            # 9. 권한 없는 도구 접근 테스트 (사용자에게 특정 도구 권한이 없는 경우)
            # 관리자 권한이 필요한 도구 호출 시도
            admin_request = {
                "jsonrpc": "2.0",
                "method": "admin_only_tool",  # 가상의 관리자 전용 도구
                "params": {},
                "id": 7
            }
            
            admin_response = auth_client.post(
                "/api/v1/mcp/execute",
                json=admin_request,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            # 권한 오류 확인
            assert admin_response.status_code == 200  # JSON-RPC는 항상 200 반환
            admin_result = admin_response.json()
            assert "error" in admin_result or admin_result["result"]["status"] == "error"

    async def test_mcp_protocol_compliance(self, auth_client, mock_retrievers):
        """Test MCP protocol compliance."""
        # 로그인
        login_response = auth_client.post(
            "/api/v1/auth/token",
            data={
                "username": "test@example.com",
                "password": "StrongPassword123!"
            }
        )
        token = login_response.json()["access_token"]
        
        with patch('src.server.retrievers', mock_retrievers):
            # 1. JSON-RPC 2.0 형식 검증
            valid_request = {
                "jsonrpc": "2.0",
                "method": "search_web",
                "params": {"query": "test"},
                "id": 1
            }
            
            response = auth_client.post(
                "/api/v1/mcp/execute",
                json=valid_request,
                headers={"Authorization": f"Bearer {token}"}
            )
            result = response.json()
            
            # MCP 응답 형식 검증
            assert result["jsonrpc"] == "2.0"
            assert result["id"] == 1
            assert "result" in result or "error" in result
            
            # 2. 잘못된 JSON-RPC 버전
            invalid_version = {
                "jsonrpc": "1.0",  # 잘못된 버전
                "method": "search_web",
                "params": {"query": "test"},
                "id": 2
            }
            
            response = auth_client.post(
                "/api/v1/mcp/execute",
                json=invalid_version,
                headers={"Authorization": f"Bearer {token}"}
            )
            result = response.json()
            assert "error" in result
            
            # 3. method 누락
            no_method = {
                "jsonrpc": "2.0",
                "params": {"query": "test"},
                "id": 3
            }
            
            response = auth_client.post(
                "/api/v1/mcp/execute",
                json=no_method,
                headers={"Authorization": f"Bearer {token}"}
            )
            result = response.json()
            assert "error" in result
            
            # 4. 알 수 없는 메서드
            unknown_method = {
                "jsonrpc": "2.0",
                "method": "unknown_method",
                "params": {},
                "id": 4
            }
            
            response = auth_client.post(
                "/api/v1/mcp/execute",
                json=unknown_method,
                headers={"Authorization": f"Bearer {token}"}
            )
            result = response.json()
            assert "error" in result

    async def test_error_handling(self, auth_client):
        """Test error handling throughout the system."""
        # 1. 인증되지 않은 요청
        unauthorized_request = {
            "jsonrpc": "2.0",
            "method": "search_web",
            "params": {"query": "test"},
            "id": 1
        }
        
        response = auth_client.post(
            "/api/v1/mcp/execute",
            json=unauthorized_request
        )
        assert response.status_code == 401
        
        # 2. 잘못된 토큰
        response = auth_client.post(
            "/api/v1/mcp/execute",
            json=unauthorized_request,
            headers={"Authorization": "Bearer invalid_token"}
        )
        assert response.status_code == 401
        
        # 3. 만료된 토큰 시뮬레이션
        with patch('src.auth.services.jwt_service.decode_token', side_effect=Exception("Token expired")):
            response = auth_client.post(
                "/api/v1/mcp/execute",
                json=unauthorized_request,
                headers={"Authorization": "Bearer expired_token"}
            )
            assert response.status_code == 401

    async def test_concurrent_requests(self, auth_client, mock_retrievers):
        """Test handling of concurrent requests."""
        # 로그인
        login_response = auth_client.post(
            "/api/v1/auth/token",
            data={
                "username": "test@example.com", 
                "password": "StrongPassword123!"
            }
        )
        token = login_response.json()["access_token"]
        
        with patch('src.server.retrievers', mock_retrievers):
            # 여러 동시 요청 생성
            requests = [
                {
                    "jsonrpc": "2.0",
                    "method": "search_web",
                    "params": {"query": f"concurrent test {i}"},
                    "id": i
                }
                for i in range(10)
            ]
            
            # 동시에 모든 요청 전송
            import concurrent.futures
            
            def send_request(req):
                return auth_client.post(
                    "/api/v1/mcp/execute",
                    json=req,
                    headers={"Authorization": f"Bearer {token}"}
                )
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(send_request, req) for req in requests]
                responses = [f.result() for f in concurrent.futures.as_completed(futures)]
            
            # 모든 요청이 성공했는지 확인
            assert all(r.status_code == 200 for r in responses)
            results = [r.json() for r in responses]
            assert all("result" in r for r in results)
            assert all(r["result"]["status"] == "success" for r in results)

    @pytest.mark.asyncio
    async def test_mcp_client_compatibility(self, auth_client):
        """Test compatibility with MCP client specifications."""
        # MCP 클라이언트가 기대하는 엔드포인트와 응답 형식 테스트
        
        # 1. 도구 목록 조회 (MCP discovery)
        tools_response = auth_client.get("/api/v1/mcp/tools")
        assert tools_response.status_code == 200
        tools = tools_response.json()
        
        # 도구 정보 형식 검증
        expected_tools = ["search_web", "search_vectors", "search_database", "search_all"]
        assert all(tool in tools for tool in expected_tools)
        
        for tool_name, tool_info in tools.items():
            assert "description" in tool_info
            assert "parameters" in tool_info
            assert isinstance(tool_info["parameters"], dict)
        
        # 2. 서버 정보 조회
        info_response = auth_client.get("/api/v1/mcp/info")
        assert info_response.status_code == 200
        info = info_response.json()
        
        assert "name" in info
        assert info["name"] == "mcp-retriever"
        assert "version" in info
        assert "capabilities" in info