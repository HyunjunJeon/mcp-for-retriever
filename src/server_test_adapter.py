"""
기존 테스트와의 호환성을 위한 어댑터 모듈

기존 server.py의 인터페이스를 통합 서버로 매핑합니다.
이를 통해 기존 테스트를 최소한의 수정으로 재사용할 수 있습니다.
"""

from typing import Any, Dict, List, Optional
import asyncio
from contextlib import AsyncExitStack

from src.server_unified import UnifiedMCPServer, UserContext
from src.config import ServerConfig, ServerProfile
from src.retrievers.base import Retriever
from fastmcp import FastMCP

# 전역 서버 인스턴스
_unified_server: Optional[UnifiedMCPServer] = None
_mcp_server: Optional[FastMCP] = None

# 전역 리트리버 (테스트 호환성을 위해)
retrievers: Dict[str, Retriever] = {}

# 전역 팩토리 (테스트 호환성을 위해)
from src.retrievers.factory import RetrieverFactory
factory = None


def create_server(profile: ServerProfile = ServerProfile.BASIC) -> FastMCP:
    """
    기존 create_server 함수와 호환되는 인터페이스
    
    Returns:
        FastMCP 서버 인스턴스
    """
    global _unified_server, _mcp_server, retrievers, factory
    
    # 기본 설정으로 서버 생성
    config = ServerConfig.from_profile(profile)
    
    # 테스트를 위한 설정 조정
    if not config.retriever_config.tavily_api_key:
        config.retriever_config.tavily_api_key = "tvly-mockkey123456789"
    
    _unified_server = UnifiedMCPServer(config)
    _mcp_server = _unified_server.create_server()
    
    # 전역 리트리버 참조 설정 (테스트 호환성)
    retrievers = _unified_server.retrievers
    factory = _unified_server.factory
    
    return _mcp_server


async def startup():
    """
    기존 startup 함수와 호환되는 인터페이스
    """
    global _unified_server, retrievers, factory
    
    if _unified_server is None:
        # 서버가 없으면 기본 프로파일로 생성
        create_server()
    
    # 테스트에서 factory가 모킹된 경우 처리
    if factory and hasattr(factory, 'create'):
        # 모킹된 factory 사용
        _unified_server.factory = factory
    
    # 리트리버 초기화
    await _unified_server.init_retrievers()
    
    # 전역 리트리버 참조 업데이트
    retrievers.clear()
    retrievers.update(_unified_server.retrievers)


async def shutdown():
    """
    기존 shutdown 함수와 호환되는 인터페이스
    """
    global _unified_server, retrievers
    
    if _unified_server:
        await _unified_server.cleanup()
        retrievers.clear()


async def search_web_tool(
    query: str,
    limit: int = 10,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    기존 search_web_tool 함수와 호환되는 인터페이스
    
    웹 검색 도구를 직접 호출합니다.
    """
    global retrievers
    
    # Tavily 리트리버 확인
    if "tavily" not in retrievers:
        return {
            "status": "error",
            "error": "Web search is not available. Please check your Tavily API key."
        }
    
    retriever = retrievers["tavily"]
    if not retriever.connected:
        return {
            "status": "error",
            "error": "Web search is not available. Retriever not connected."
        }
    
    try:
        # 검색 옵션 설정
        search_kwargs = {}
        if include_domains:
            search_kwargs["include_domains"] = include_domains
        if exclude_domains:
            search_kwargs["exclude_domains"] = exclude_domains
        
        # 검색 실행
        results = []
        async for result in retriever.retrieve(query, limit=limit, **search_kwargs):
            results.append(result)
        
        return {
            "status": "success",
            "results": results,
            "count": len(results)
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


async def search_all_tool(
    query: str,
    limit: int = 10
) -> Dict[str, Any]:
    """
    기존 search_all_tool 함수와 호환되는 인터페이스
    
    모든 리트리버에서 동시에 검색합니다.
    """
    global retrievers
    
    if not retrievers:
        return {
            "status": "error",
            "error": "No retrievers available"
        }
    
    all_results = {}
    errors = {}
    
    # 모든 리트리버에서 동시에 검색
    async def search_source(name: str, retriever: Retriever) -> None:
        if not retriever.connected:
            errors[name] = "Not connected"
            return
        
        try:
            source_results = []
            async for result in retriever.retrieve(query, limit=limit):
                result["source"] = name
                source_results.append(result)
            all_results[name] = source_results
        except Exception as e:
            errors[name] = str(e)
    
    # 동시에 모든 검색 실행
    tasks = [
        search_source(name, retriever)
        for name, retriever in retrievers.items()
    ]
    await asyncio.gather(*tasks)
    
    return {
        "status": "success",
        "results": all_results,
        "errors": errors,
        "sources_searched": list(retrievers.keys())
    }


# 하위 호환성을 위한 추가 내보내기
__all__ = [
    "create_server",
    "startup",
    "shutdown",
    "search_web_tool",
    "search_all_tool",
    "retrievers",
    "factory",
    "RetrieverFactory"  # 테스트에서 패치하기 위해 필요
]