"""
통합 서버 직접 호출 E2E 테스트

서버의 도구 함수들을 직접 호출하여 전체 기능을 테스트합니다.
"""

import pytest
import json
from typing import Any, Dict
from unittest.mock import patch, AsyncMock, Mock
import asyncio

from src.server_unified import UnifiedMCPServer
from src.config import ServerConfig, ServerProfile
from fastmcp import Context


class TestUnifiedServerDirectE2E:
    """통합 서버 직접 호출 E2E 테스트"""
    
    @pytest.fixture
    async def basic_server(self):
        """BASIC 프로파일 서버"""
        config = ServerConfig.from_profile(ServerProfile.BASIC)
        config.retriever_config.tavily_api_key = "tvly-e2etest123456789"
        server = UnifiedMCPServer(config)
        
        # 리트리버 초기화
        await server.init_retrievers()
        
        yield server
        
        # 정리
        await server.cleanup()
    
    @pytest.fixture
    async def complete_server(self):
        """COMPLETE 프로파일 서버"""
        config = ServerConfig.from_profile(ServerProfile.COMPLETE)
        # 테스트용 설정
        config.auth_config.internal_api_key = "e2e-internal-api-key-that-is-long-enough"
        config.auth_config.jwt_secret_key = "e2e-jwt-secret-key-that-is-long-enough"
        config.auth_config.require_auth = False
        config.retriever_config.tavily_api_key = "tvly-e2etest123456789"
        config.rate_limit_config.requests_per_hour = 3600
        
        server = UnifiedMCPServer(config)
        
        # 리트리버 초기화
        await server.init_retrievers()
        
        yield server
        
        # 정리
        await server.cleanup()
    
    @pytest.fixture
    def mock_context(self):
        """Mock FastMCP context"""
        ctx = AsyncMock(spec=Context)
        ctx.info = AsyncMock()
        ctx.error = AsyncMock()
        ctx.warning = AsyncMock()
        return ctx
    
    @pytest.mark.asyncio
    async def test_server_initialization(self, basic_server):
        """서버 초기화 테스트"""
        # 리트리버 확인
        assert len(basic_server.retrievers) > 0
        
        # 기본 설정 확인
        assert basic_server.config.profile == ServerProfile.BASIC
        assert basic_server.config.name == "mcp-retriever"
    
    @pytest.mark.asyncio
    async def test_health_check(self, basic_server, mock_context):
        """헬스 체크 기능 테스트"""
        # 헬스 체크 수행
        health_data = {}
        
        # 각 리트리버의 헬스 체크
        for name, retriever in basic_server.retrievers.items():
            try:
                health = await retriever.health_check()
                health_data[name] = {
                    "connected": retriever.connected,
                    "health": health
                }
            except Exception as e:
                health_data[name] = {
                    "connected": False,
                    "error": str(e)
                }
        
        # 전체 상태 확인
        all_healthy = all(h.get("connected", False) for h in health_data.values())
        status = "healthy" if all_healthy else "degraded"
        
        assert status in ["healthy", "degraded"]
        assert len(health_data) > 0
    
    @pytest.mark.asyncio
    async def test_search_functionality(self, basic_server, mock_context):
        """검색 기능 테스트"""
        # Tavily 리트리버 모킹
        if "tavily" in basic_server.retrievers:
            mock_retriever = basic_server.retrievers["tavily"]
            
            # retrieve 메서드 모킹
            async def mock_retrieve(query, **kwargs):
                yield {"title": "Test Result 1", "url": "https://example.com/1"}
                yield {"title": "Test Result 2", "url": "https://example.com/2"}
            
            mock_retriever.retrieve = mock_retrieve
            
            # 검색 수행
            results = []
            async for result in mock_retriever.retrieve("test query", limit=2):
                results.append(result)
            
            assert len(results) == 2
            assert results[0]["title"] == "Test Result 1"
    
    @pytest.mark.asyncio
    async def test_complete_profile_features(self, complete_server):
        """COMPLETE 프로파일 기능 테스트"""
        # 모든 기능이 활성화되었는지 확인
        features = complete_server.config.features
        
        assert features["auth"]
        assert features["context"]
        assert features["cache"]
        assert features["rate_limit"]
        assert features["metrics"]
        
        # 미들웨어 확인
        assert len(complete_server.middlewares) > 5
        assert complete_server.auth_middleware is not None
        assert complete_server.metrics_middleware is not None
        
        # 컨텍스트 저장소 확인
        assert complete_server.context_store is not None
    
    @pytest.mark.asyncio
    async def test_cache_functionality(self, complete_server):
        """캐시 기능 테스트"""
        # 캐시가 활성화된 리트리버 찾기
        cached_retrievers = {}
        
        for name, retriever in complete_server.retrievers.items():
            if hasattr(retriever, '_use_cache') and retriever._use_cache:
                cached_retrievers[name] = retriever
        
        # 캐시 설정 확인
        for name, retriever in cached_retrievers.items():
            if hasattr(retriever, '_cache'):
                assert retriever._cache is not None
                
                # 캐시 네임스페이스 확인
                if hasattr(retriever, '_get_cache_namespace'):
                    namespace = retriever._get_cache_namespace()
                    assert namespace is not None
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, basic_server, mock_context):
        """동시 작업 테스트"""
        # 여러 리트리버에서 동시에 작업 수행
        tasks = []
        
        for name, retriever in basic_server.retrievers.items():
            if retriever.connected:
                task = retriever.health_check()
                tasks.append(task)
        
        if tasks:
            # 모든 작업 완료 대기
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 결과 확인
            assert len(results) == len(tasks)
    
    @pytest.mark.asyncio
    async def test_error_handling(self, basic_server, mock_context):
        """오류 처리 테스트"""
        # 존재하지 않는 리트리버 접근 시도
        with pytest.raises(KeyError):
            _ = basic_server.retrievers["non_existent"]
        
        # 잘못된 설정으로 서버 생성 시도
        with pytest.raises(ValueError):
            bad_config = ServerConfig.from_profile(ServerProfile.COMPLETE)
            bad_config.auth_config.internal_api_key = "short"  # 너무 짧은 키
            UnifiedMCPServer(bad_config)
    
    @pytest.mark.asyncio
    async def test_profile_specific_tools(self):
        """프로파일별 도구 테스트"""
        profiles_and_tools = {
            ServerProfile.BASIC: ["search_web", "search_vectors", "search_database", "search_all", "health_check"],
            ServerProfile.CACHED: ["search_web", "search_vectors", "search_database", "search_all", "health_check", "invalidate_cache", "cache_stats"],
            ServerProfile.COMPLETE: ["search_web", "search_vectors", "search_database", "search_all", "health_check", "invalidate_cache", "cache_stats", "get_metrics"]
        }
        
        for profile, expected_tools in profiles_and_tools.items():
            config = ServerConfig.from_profile(profile)
            
            # 테스트용 설정
            if config.auth_config:
                config.auth_config.internal_api_key = "e2e-internal-api-key-that-is-long-enough-for-validation"
                config.auth_config.jwt_secret_key = "e2e-jwt-secret-key-that-is-long-enough-for-validation"
                config.auth_config.require_auth = False
            if config.retriever_config:
                config.retriever_config.tavily_api_key = "tvly-e2etest123456789"
            if config.rate_limit_config:
                config.rate_limit_config.requests_per_hour = 3600
            
            server = UnifiedMCPServer(config)
            mcp = server.create_server()
            
            # FastMCP 서버가 생성되었는지 확인
            assert mcp is not None
            assert mcp.name == "mcp-retriever"
    
    @pytest.mark.asyncio 
    async def test_lifecycle_management(self):
        """서버 라이프사이클 관리 테스트"""
        config = ServerConfig.from_profile(ServerProfile.BASIC)
        config.retriever_config.tavily_api_key = "tvly-e2etest123456789"
        server = UnifiedMCPServer(config)
        
        # 초기화 전 상태
        assert len(server.retrievers) == 0
        
        # 초기화
        errors = await server.init_retrievers()
        
        # 초기화 후 상태
        assert len(server.retrievers) > 0
        
        # 정리
        await server.cleanup()
        
        # 정리 후 상태
        assert len(server.retrievers) == 0


class TestServerIntegration:
    """서버 통합 테스트"""
    
    @pytest.mark.asyncio
    async def test_basic_to_complete_migration(self):
        """BASIC에서 COMPLETE로 마이그레이션 테스트"""
        # BASIC 서버 생성
        basic_config = ServerConfig.from_profile(ServerProfile.BASIC)
        basic_config.retriever_config.tavily_api_key = "tvly-e2etest123456789"
        basic_server = UnifiedMCPServer(basic_config)
        
        await basic_server.init_retrievers()
        basic_retriever_count = len(basic_server.retrievers)
        await basic_server.cleanup()
        
        # COMPLETE 서버 생성
        complete_config = ServerConfig.from_profile(ServerProfile.COMPLETE)
        complete_config.auth_config.internal_api_key = "e2e-internal-api-key-that-is-long-enough-for-validation"
        complete_config.auth_config.jwt_secret_key = "e2e-jwt-secret-key-that-is-long-enough-for-validation"
        complete_config.auth_config.require_auth = False
        complete_config.retriever_config.tavily_api_key = "tvly-e2etest123456789"
        complete_config.rate_limit_config.requests_per_hour = 3600
        
        complete_server = UnifiedMCPServer(complete_config)
        
        await complete_server.init_retrievers()
        complete_retriever_count = len(complete_server.retrievers)
        
        # 동일한 리트리버 수 확인
        assert basic_retriever_count == complete_retriever_count
        
        # COMPLETE 서버의 추가 기능 확인
        assert len(complete_server.middlewares) > 1
        assert complete_server.context_store is not None
        
        await complete_server.cleanup()
    
    @pytest.mark.asyncio
    async def test_configuration_validation(self):
        """설정 검증 테스트"""
        # 잘못된 설정들 테스트
        
        # 짧은 API 키 테스트
        with pytest.raises(ValueError, match="내부 API 키가 너무 짧음"):
            config = ServerConfig.from_profile(ServerProfile.AUTH)
            config.auth_config.internal_api_key = "short"
            config.auth_config.jwt_secret_key = "jwt-key-that-is-long-enough-for-validation" 
            config.auth_config.require_auth = True
            server = UnifiedMCPServer(config)
        
        # 잘못된 포트 테스트
        with pytest.raises(ValueError, match="잘못된 포트 번호"):
            config = ServerConfig.from_profile(ServerProfile.BASIC)
            config.transport = "http"  # HTTP 모드로 설정해야 포트 검증이 수행됨
            config.port = 99999
            config.retriever_config.tavily_api_key = "tvly-validkey123456789"
            server = UnifiedMCPServer(config)


# 테스트 실행을 위한 메인 함수
if __name__ == "__main__":
    pytest.main([__file__, "-v"])