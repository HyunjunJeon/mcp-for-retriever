"""FastMCP 클라이언트를 사용한 직접 테스트"""

import asyncio
from fastmcp import Client
import json


async def test_with_fastmcp_client():
    """FastMCP 클라이언트로 서버 테스트"""
    # HTTP 프로토콜 사용
    async with Client("http://localhost:8001/mcp/", auth="Bearer test-mcp-key") as client:
        # 도구 목록 가져오기
        print("=== 도구 목록 ===")
        tools = await client.list_tools()
        for tool in tools:
            print(f"- {tool.name}: {tool.description}")
        
        # search_vectors 도구 호출
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
            print(f"Result: {json.dumps(result.data, indent=2)}")
        except Exception as e:
            print(f"Error: {e}")
            # 에러 상세 확인
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_with_fastmcp_client())