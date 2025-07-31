"""FastMCP Client 요청 형식 디버깅"""

import asyncio
import json
from fastmcp import Client
import httpx
from unittest.mock import patch, AsyncMock

# HTTP 요청을 가로채서 로깅하는 패치
original_post = httpx.AsyncClient.post

async def logged_post(self, *args, **kwargs):
    """HTTP POST 요청을 로깅"""
    url = args[0] if args else kwargs.get('url', 'unknown')
    data = kwargs.get('json', kwargs.get('data', {}))
    headers = kwargs.get('headers', {})
    
    print(f"\n🔍 HTTP POST to: {url}")
    print(f"📤 Headers: {json.dumps(dict(headers), indent=2, ensure_ascii=False)}")
    if isinstance(data, dict):
        print(f"📤 JSON Data: {json.dumps(data, indent=2, ensure_ascii=False)}")
    else:
        print(f"📤 Raw Data: {data}")
    
    # 원본 요청 실행
    response = await original_post(self, *args, **kwargs)
    
    print(f"📥 Response Status: {response.status_code}")
    print(f"📥 Response Headers: {json.dumps(dict(response.headers), indent=2, ensure_ascii=False)}")
    
    # 응답 내용 로깅 (텍스트 기반)
    try:
        if response.headers.get("content-type", "").startswith("text/event-stream"):
            print(f"📥 SSE Response: {response.text}")
        else:
            response_json = response.json()
            print(f"📥 JSON Response: {json.dumps(response_json, indent=2, ensure_ascii=False)}")
    except:
        print(f"📥 Raw Response: {response.text}")
    
    print("=" * 80)
    return response


async def debug_fastmcp_client():
    """FastMCP Client의 요청 형식 디버깅"""
    print("=== FastMCP Client 요청 형식 디버깅 ===")
    
    # HTTP 요청 패치
    with patch.object(httpx.AsyncClient, 'post', logged_post):
        try:
            # FastMCP Client로 연결
            async with Client(
                "http://localhost:8001/mcp/",
                auth="Bearer test-mcp-key"
            ) as client:
                print("✅ FastMCP Client 연결 성공")
                
                # 1. list_tools 호출
                print("\n--- FastMCP Client: list_tools() ---")
                tools = await client.list_tools()
                print(f"🔧 Tools found: {[t.name for t in tools]}")
                
                # 2. call_tool 호출 (간단한 것)
                print("\n--- FastMCP Client: call_tool('health_check') ---")
                result = await client.call_tool("health_check", {})
                print(f"🏥 Health result: {result.data}")
                
        except Exception as e:
            print(f"❌ FastMCP Client 오류: {e}")
            import traceback
            traceback.print_exc()


async def debug_direct_http():
    """직접 HTTP 요청 디버깅"""
    print("\n=== 직접 HTTP 요청 디버깅 ===")
    
    async with httpx.AsyncClient() as client:
        # 현재 MCP Proxy가 사용하는 형식 재현
        print("\n--- 현재 MCP Proxy 형식 (실패 케이스) ---")
        response = await client.post(
            "http://localhost:8001/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "tools/list",
                "params": {},  # 빈 params
                "id": 1
            },
            headers={
                "Authorization": "Bearer test-mcp-key",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            }
        )
        print(f"📥 Status: {response.status_code}")
        print(f"📥 Response: {response.text}")
        
        # params 없이 시도
        print("\n--- params 없는 형식 시도 ---")
        response = await client.post(
            "http://localhost:8001/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 1
            },
            headers={
                "Authorization": "Bearer test-mcp-key",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            }
        )
        print(f"📥 Status: {response.status_code}")
        print(f"📥 Response: {response.text}")


async def main():
    """메인 디버깅 함수"""
    await debug_fastmcp_client()
    await debug_direct_http()


if __name__ == "__main__":
    asyncio.run(main())