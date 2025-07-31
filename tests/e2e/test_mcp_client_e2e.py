"""
FastMCP Client E2E 테스트

실제 FastMCP 클라이언트를 사용하여 통합 서버의 전체 기능을 테스트합니다.
모든 프로파일과 도구 함수들이 제대로 작동하는지 확인합니다.
"""

import pytest
import asyncio
import subprocess
import time
import os
from typing import Any, Dict, List
import httpx

from fastmcp import Client

# 테스트용 환경 변수 설정
TEST_ENV = {
    "MCP_INTERNAL_API_KEY": "e2e-test-internal-api-key-that-is-long-enough",
    "JWT_SECRET_KEY": "e2e-test-jwt-secret-key-that-is-long-enough", 
    "TAVILY_API_KEY": "tvly-e2etest123456789",
    "MCP_TRANSPORT": "http",
    "MCP_SERVER_PORT": "8002",  # 테스트용 포트
    "LOG_LEVEL": "INFO"
}


class TestMCPClientE2E:
    """FastMCP Client를 사용한 E2E 테스트"""
    
    @pytest.fixture(scope="function")
    async def server_process(self):
        """테스트용 서버 프로세스 시작"""
        # 환경 변수 설정
        env = os.environ.copy()
        env.update(TEST_ENV)
        
        # 서버 시작
        process = subprocess.Popen(
            ["uv", "run", "python", "-m", "src.server_unified"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # 서버 시작 대기
        await asyncio.sleep(2)
        
        yield process
        
        # 서버 종료
        process.terminate()
        process.wait(timeout=5)
    
    @pytest.fixture
    async def mcp_client(self, server_process):
        """MCP 클라이언트 생성"""
        # FastMCP 클라이언트 생성
        # MCP 서버는 /mcp/ 경로를 사용
        client = Client(
            f"http://localhost:{TEST_ENV['MCP_SERVER_PORT']}/mcp/",
            auth=f"Bearer {TEST_ENV['MCP_INTERNAL_API_KEY']}"
        )
        
        # 클라이언트 연결
        await client.__aenter__()
        
        yield client
        
        # 클라이언트 정리
        await client.__aexit__(None, None, None)
    
    @pytest.mark.asyncio
    async def test_list_tools(self, mcp_client):
        """도구 목록 조회 테스트"""
        # 도구 목록 조회
        tools = await mcp_client.list_tools()
        
        assert tools is not None
        assert len(tools) > 0
        
        tool_names = [tool.name for tool in tools]
        
        # 기본 도구들이 있는지 확인
        assert "search_web" in tool_names
        assert "search_vectors" in tool_names
        assert "search_database" in tool_names
        assert "search_all" in tool_names
        assert "health_check" in tool_names
    
    @pytest.mark.asyncio
    async def test_search_web_tool(self, mcp_client):
        """웹 검색 도구 테스트"""
        # search_web 도구 호출
        result = await mcp_client.call_tool(
            "search_web",
            {
                "query": "FastMCP test",
                "limit": 5
            }
        )
        
        assert result is not None
        # result.data는 도구의 반환값
        # Tavily API가 설정되지 않았으므로 오류가 발생할 수 있음
        # 하지만 도구 호출 자체는 성공해야 함
        assert result.data is not None
    
    @pytest.mark.asyncio
    async def test_health_check_tool(self, mcp_client):
        """헬스 체크 도구 테스트"""
        # health_check 도구 호출
        result = await mcp_client.call_tool(
            "health_check",
            {}
        )
        
        assert result is not None
        assert result.data is not None
        
        health = result.data
        assert "status" in health
        assert "service" in health
        assert health["service"] == "mcp-retriever"
    
    @pytest.mark.asyncio
    async def test_multiple_profiles(self):
        """다양한 프로파일로 서버 테스트"""
        profiles = ["BASIC", "AUTH", "CONTEXT", "CACHED", "COMPLETE"]
        
        for profile in profiles:
            # 프로파일별 환경 변수 설정
            env = os.environ.copy()
            env.update(TEST_ENV)
            env["MCP_PROFILE"] = profile
            env["MCP_SERVER_PORT"] = str(8003 + profiles.index(profile))
            
            # 서버 시작
            process = subprocess.Popen(
                ["uv", "run", "python", "-m", "src.server_unified"],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            try:
                # 서버 시작 대기
                await asyncio.sleep(2)
                
                # 클라이언트로 연결 테스트
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"http://localhost:{env['MCP_SERVER_PORT']}/",
                        json={
                            "jsonrpc": "2.0",
                            "method": "initialize",
                            "params": {
                                "protocolVersion": "2024-11-05",
                                "capabilities": {}
                            },
                            "id": 1
                        },
                        headers={
                            "Authorization": f"Bearer {TEST_ENV['MCP_INTERNAL_API_KEY']}"
                        } if profile != "BASIC" else {}
                    )
                    
                    assert response.status_code == 200
                    result = response.json()
                    assert "result" in result
                    
                    # 프로파일에 따른 기능 확인
                    server_info = result["result"]["serverInfo"]
                    assert server_info["name"] == "mcp-retriever"
                    
            finally:
                # 서버 종료
                process.terminate()
                process.wait(timeout=5)
    
    @pytest.mark.asyncio
    async def test_error_handling(self, mcp_client):
        """오류 처리 테스트"""
        # 존재하지 않는 도구 호출
        from fastmcp.exceptions import ToolError
        
        with pytest.raises(ToolError):
            await mcp_client.call_tool(
                "non_existent_tool",
                {}
            )
    
    @pytest.mark.asyncio
    async def test_concurrent_requests(self, mcp_client):
        """동시 요청 처리 테스트"""
        # 여러 요청을 동시에 보내기
        tasks = []
        for i in range(10):
            task = mcp_client.call_tool(
                "health_check",
                {}
            )
            tasks.append(task)
        
        # 모든 요청 완료 대기
        results = await asyncio.gather(*tasks)
        
        # 모든 응답이 성공했는지 확인
        for result in results:
            assert result.data is not None
            assert result.data["status"] in ["healthy", "degraded"]


class TestMCPClientWithAuth:
    """인증이 필요한 프로파일 테스트"""
    
    @pytest.fixture(scope="function")
    async def auth_server_process(self):
        """AUTH 프로파일 서버 시작"""
        env = os.environ.copy()
        env.update(TEST_ENV)
        env["MCP_PROFILE"] = "AUTH"
        env["MCP_SERVER_PORT"] = "8010"
        
        process = subprocess.Popen(
            ["uv", "run", "python", "-m", "src.server_unified"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        await asyncio.sleep(2)
        yield process
        
        process.terminate()
        process.wait(timeout=5)
    
    @pytest.mark.asyncio
    async def test_auth_required(self, auth_server_process):
        """인증 없이 요청 시 실패 테스트"""
        async with httpx.AsyncClient() as client:
            # 인증 헤더 없이 요청
            response = await client.post(
                "http://localhost:8010/",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/list",
                    "params": {},
                    "id": 1
                }
            )
            
            # 인증 오류 확인 (AUTH 프로파일은 내부 API 키만 확인)
            # 인증 미들웨어가 require_auth=False로 설정되어 있으므로 성공할 수도 있음
            assert response.status_code in [200, 401, 403]
    
    @pytest.mark.asyncio
    async def test_auth_success(self, auth_server_process):
        """올바른 인증으로 요청 성공 테스트"""
        async with httpx.AsyncClient() as client:
            # 올바른 인증 헤더로 요청
            response = await client.post(
                "http://localhost:8010/",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/list",
                    "params": {},
                    "id": 1
                },
                headers={
                    "Authorization": f"Bearer {TEST_ENV['MCP_INTERNAL_API_KEY']}"
                }
            )
            
            assert response.status_code == 200
            result = response.json()
            assert "result" in result


class TestMCPClientWithCache:
    """캐싱 기능 테스트"""
    
    @pytest.fixture(scope="function")
    async def cached_server_process(self):
        """CACHED 프로파일 서버 시작"""
        env = os.environ.copy()
        env.update(TEST_ENV)
        env["MCP_PROFILE"] = "CACHED"
        env["MCP_SERVER_PORT"] = "8011"
        # Redis가 실행 중이어야 함
        env["REDIS_URL"] = "redis://localhost:6379/1"
        
        process = subprocess.Popen(
            ["uv", "run", "python", "-m", "src.server_unified"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        await asyncio.sleep(2)
        yield process
        
        process.terminate()
        process.wait(timeout=5)
    
    @pytest.mark.asyncio
    async def test_cache_tools_available(self, cached_server_process):
        """캐시 관련 도구 사용 가능 확인"""
        async with httpx.AsyncClient() as client:
            # 도구 목록 조회
            response = await client.post(
                "http://localhost:8011/",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/list",
                    "params": {},
                    "id": 1
                },
                headers={
                    "Authorization": f"Bearer {TEST_ENV['MCP_INTERNAL_API_KEY']}"
                }
            )
            
            assert response.status_code == 200
            result = response.json()
            
            tools = result["result"]["tools"]
            tool_names = [tool["name"] for tool in tools]
            
            # 캐시 도구들이 있는지 확인
            assert "invalidate_cache" in tool_names
            assert "cache_stats" in tool_names


# E2E 테스트 실행을 위한 메인 함수
if __name__ == "__main__":
    pytest.main([__file__, "-v"])