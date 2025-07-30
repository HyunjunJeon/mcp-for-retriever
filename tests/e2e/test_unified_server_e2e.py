"""
통합 서버 E2E 테스트

통합 서버의 전체 기능을 직접 테스트합니다.
서버 인스턴스를 생성하고 도구 함수들을 직접 호출하여 테스트합니다.
"""

import pytest
from typing import Any, Dict
from unittest.mock import patch, AsyncMock, Mock
import os
import json

from fastmcp import FastMCP, Context

from src.server_unified import UnifiedMCPServer
from src.config import ServerConfig, ServerProfile


class TestUnifiedServerE2E:
    """통합 서버 E2E 테스트"""
    
    @pytest.fixture
    def basic_server(self):
        """BASIC 프로파일 서버"""
        config = ServerConfig.from_profile(ServerProfile.BASIC)
        config.retriever_config.tavily_api_key = "tvly-e2etest123456789"
        server = UnifiedMCPServer(config)
        return server
    
    @pytest.fixture
    def complete_server(self):
        """COMPLETE 프로파일 서버"""
        config = ServerConfig.from_profile(ServerProfile.COMPLETE)
        # 테스트용 설정
        config.auth_config.internal_api_key = "e2e-internal-api-key-that-is-long-enough"
        config.auth_config.jwt_secret_key = "e2e-jwt-secret-key-that-is-long-enough"
        config.auth_config.require_auth = False
        config.retriever_config.tavily_api_key = "tvly-e2etest123456789"
        config.rate_limit_config.requests_per_hour = 3600
        
        server = UnifiedMCPServer(config)
        return server
    
    @pytest.fixture
    def mock_context(self):
        """Mock FastMCP context"""
        ctx = AsyncMock(spec=Context)
        ctx.info = AsyncMock()
        ctx.error = AsyncMock()
        ctx.warning = AsyncMock()
        return ctx
    
    @pytest.mark.asyncio
    async def test_initialize(self, basic_server):
        """서버 초기화 테스트"""
        response = await basic_server.initialize()
        
        assert response.server_info.name == "mcp-retriever"
        assert response.server_info.version is not None
        assert response.protocol_version == "2024-11-05"
    
    @pytest.mark.asyncio
    async def test_list_tools(self, basic_server):
        """도구 목록 조회 테스트"""
        # 초기화
        await basic_server.initialize()
        
        # 도구 목록 조회
        response = await basic_server.list_tools()
        
        tool_names = [tool.name for tool in response.tools]
        
        # 기본 도구들 확인
        assert "search_web" in tool_names
        assert "search_vectors" in tool_names
        assert "search_database" in tool_names
        assert "search_all" in tool_names
        assert "health_check" in tool_names
    
    @pytest.mark.asyncio
    async def test_health_check_tool(self, basic_server):
        """헬스 체크 도구 테스트"""
        # 초기화
        await basic_server.initialize()
        
        # 헬스 체크 호출
        response = await basic_server.call_tool(
            "health_check",
            arguments={}
        )
        
        assert response.content[0].type == "text"
        
        # 결과 파싱 (JSON 형태로 반환됨)
        import json
        health = json.loads(response.content[0].text)
        
        assert health["status"] in ["healthy", "degraded"]
        assert health["service"] == "mcp-retriever"
        assert "retrievers" in health
    
    @pytest.mark.asyncio
    async def test_search_web_with_mock(self, basic_server):
        """웹 검색 도구 테스트 (모킹)"""
        # 초기화
        await basic_server.initialize()
        
        # Tavily retriever 모킹
        with patch('src.retrievers.tavily.httpx.AsyncClient') as mock_client:
            mock_response = AsyncMock()
            mock_response.json.return_value = {
                "results": [
                    {
                        "title": "Test Result 1",
                        "url": "https://example.com/1",
                        "content": "Test content 1",
                        "score": 0.95
                    },
                    {
                        "title": "Test Result 2",
                        "url": "https://example.com/2", 
                        "content": "Test content 2",
                        "score": 0.85
                    }
                ]
            }
            mock_response.raise_for_status = AsyncMock()
            
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            
            # 검색 실행
            response = await basic_server.call_tool(
                "search_web",
                arguments={
                    "query": "test query",
                    "limit": 2
                }
            )
            
            assert response.content[0].type == "text"
            
            # 결과 확인
            import json
            results = json.loads(response.content[0].text)
            assert len(results) == 2
            assert results[0]["title"] == "Test Result 1"
    
    @pytest.mark.asyncio
    async def test_complete_profile_features(self, complete_server):
        """COMPLETE 프로파일 기능 테스트"""
        # 초기화
        await complete_server.initialize()
        
        # 도구 목록 조회
        response = await complete_server.list_tools()
        tool_names = [tool.name for tool in response.tools]
        
        # 추가 도구들 확인 (캐싱, 메트릭 등)
        assert "invalidate_cache" in tool_names
        assert "cache_stats" in tool_names
        
        # 캐시 통계 조회
        response = await complete_server.call_tool(
            "cache_stats",
            arguments={}
        )
        
        assert response.content[0].type == "text"
        
        # 결과 확인
        import json
        stats = json.loads(response.content[0].text)
        assert isinstance(stats, dict)
    
    @pytest.mark.asyncio
    async def test_error_handling(self, basic_server):
        """오류 처리 테스트"""
        # 초기화
        await basic_server.initialize()
        
        # 잘못된 도구 이름으로 호출
        with pytest.raises(Exception) as exc_info:
            await basic_server.call_tool(
                "non_existent_tool",
                arguments={}
            )
        
        # 오류 메시지 확인
        assert "not found" in str(exc_info.value).lower() or "unknown" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_profile_switching(self):
        """프로파일 전환 테스트"""
        profiles = [
            ServerProfile.BASIC,
            ServerProfile.AUTH,
            ServerProfile.CONTEXT,
            ServerProfile.CACHED,
            ServerProfile.COMPLETE
        ]
        
        for profile in profiles:
            # 프로파일별 설정 생성
            config = ServerConfig.from_profile(profile)
            
            # 테스트용 설정 조정
            if config.auth_config:
                config.auth_config.internal_api_key = "e2e-internal-key-long-enough"
                config.auth_config.jwt_secret_key = "e2e-jwt-key-long-enough"
                config.auth_config.require_auth = False
            
            if config.retriever_config:
                config.retriever_config.tavily_api_key = "tvly-e2etest123456789"
            
            if config.rate_limit_config:
                config.rate_limit_config.requests_per_hour = 3600
            
            # 서버 생성 및 테스트
            server = UnifiedMCPServer(config)
            mcp = server.create_server()
            client = TestClient(mcp)
            
            # 초기화
            response = await client.initialize()
            assert response.server_info.name == "mcp-retriever"
            
            # 도구 목록 확인
            tools_response = await client.list_tools()
            tool_names = [tool.name for tool in tools_response.tools]
            
            # 프로파일별 기능 확인
            if profile in [ServerProfile.CACHED, ServerProfile.COMPLETE]:
                assert "cache_stats" in tool_names
            else:
                assert "cache_stats" not in tool_names
    
    @pytest.mark.asyncio
    async def test_concurrent_tool_calls(self, complete_server):
        """동시 도구 호출 테스트"""
        # 초기화
        await complete_server.initialize()
        
        # 여러 도구를 동시에 호출
        import asyncio
        
        tasks = []
        for i in range(5):
            task = complete_server.call_tool(
                "health_check",
                arguments={}
            )
            tasks.append(task)
        
        # 모든 호출 완료 대기
        responses = await asyncio.gather(*tasks)
        
        # 모든 응답 확인
        for response in responses:
            assert response.content[0].type == "text"
            
            import json
            health = json.loads(response.content[0].text)
            assert health["status"] in ["healthy", "degraded"]


class TestMCPProtocolCompliance:
    """MCP 프로토콜 준수 테스트"""
    
    @pytest.fixture
    def test_server(self):
        """테스트용 서버"""
        config = ServerConfig.from_profile(ServerProfile.BASIC)
        config.retriever_config.tavily_api_key = "tvly-e2etest123456789"
        server = UnifiedMCPServer(config)
        mcp = server.create_server()
        return TestClient(mcp)
    
    @pytest.mark.asyncio
    async def test_protocol_version(self, test_server):
        """프로토콜 버전 확인"""
        response = await test_server.initialize()
        assert response.protocol_version == "2024-11-05"
    
    @pytest.mark.asyncio
    async def test_server_capabilities(self, test_server):
        """서버 기능 확인"""
        response = await test_server.initialize()
        
        # 도구 기능 지원 확인
        assert hasattr(response.capabilities, 'tools')
        
        # 서버 정보 확인
        assert response.server_info.name == "mcp-retriever"
        assert response.server_info.version is not None
    
    @pytest.mark.asyncio
    async def test_tool_schema(self, test_server):
        """도구 스키마 검증"""
        await test_server.initialize()
        
        response = await test_server.list_tools()
        
        for tool in response.tools:
            # 필수 필드 확인
            assert hasattr(tool, 'name')
            assert hasattr(tool, 'description')
            assert hasattr(tool, 'input_schema')
            
            # 스키마 형식 확인
            schema = tool.input_schema
            assert schema.get('type') == 'object'
            assert 'properties' in schema
    
    @pytest.mark.asyncio
    async def test_tool_response_format(self, test_server):
        """도구 응답 형식 검증"""
        await test_server.initialize()
        
        # 도구 호출
        response = await test_server.call_tool(
            "health_check",
            arguments={}
        )
        
        # 응답 형식 확인
        assert hasattr(response, 'content')
        assert len(response.content) > 0
        assert response.content[0].type in ["text", "image", "resource"]


# 테스트 실행을 위한 메인 함수
if __name__ == "__main__":
    pytest.main([__file__, "-v"])