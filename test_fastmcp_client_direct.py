"""FastMCP 클라이언트 직접 테스트"""

import asyncio
from fastmcp import Client
import structlog

logger = structlog.get_logger()


async def test_direct_connection():
    """FastMCP 클라이언트로 직접 연결 테스트"""
    try:
        # HTTP 프로토콜로 연결
        async with Client(
            "http://localhost:8001/mcp/",
            auth="Bearer test-mcp-key"
        ) as client:
            print("=== 연결 성공 ===")
            
            # 도구 목록 가져오기
            print("\n=== 도구 목록 조회 ===")
            tools = await client.list_tools()
            for tool in tools:
                print(f"- {tool.name}: {tool.description}")
            
            # health_check 도구 호출
            print("\n=== health_check 호출 ===")
            result = await client.call_tool("health_check", {})
            print(f"Result: {result.data}")
            
            # search_vectors 도구 호출 테스트
            print("\n=== search_vectors 호출 ===")
            try:
                result = await client.call_tool(
                    "search_vectors",
                    {
                        "query": "test query",
                        "collection": "documents",
                        "limit": 5
                    }
                )
                print(f"Result: {result.data}")
            except Exception as e:
                print(f"Error: {e}")
                
    except Exception as e:
        print(f"연결 실패: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_direct_connection())