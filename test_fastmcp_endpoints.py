"""FastMCP 서버 엔드포인트 분석"""

import asyncio
import httpx
import json


async def test_fastmcp_endpoints():
    """FastMCP 서버의 실제 엔드포인트 확인"""
    print("=== FastMCP 서버 엔드포인트 분석 ===")
    
    base_url = "http://localhost:8001"
    endpoints_to_test = [
        "/",
        "/mcp",
        "/mcp/",
        "/mcp/tools",
        "/mcp/tools/list",
        "/tools/list",
        "/docs",
        "/openapi.json",
        "/health"
    ]
    
    async with httpx.AsyncClient() as client:
        for endpoint in endpoints_to_test:
            url = f"{base_url}{endpoint}"
            print(f"\n--- 테스트: {url} ---")
            
            try:
                # GET 요청
                get_response = await client.get(url)
                print(f"GET {url}: {get_response.status_code}")
                if get_response.status_code in [200, 404, 405]:
                    print(f"  Response: {get_response.text[:200]}")
            except Exception as e:
                print(f"GET {url}: 오류 - {e}")
            
            try:
                # POST 요청 (JSON-RPC)
                post_response = await client.post(
                    url,
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/list",
                        "id": 1
                    },
                    headers={
                        "Authorization": "Bearer test-mcp-key",
                        "Content-Type": "application/json"
                    }
                )
                print(f"POST {url}: {post_response.status_code}")
                if post_response.status_code not in [404, 500]:
                    print(f"  Response: {post_response.text[:200]}")
            except Exception as e:
                print(f"POST {url}: 오류 - {e}")


async def test_fastmcp_client_behavior():
    """FastMCP Client가 실제로 사용하는 URL 확인"""
    print("\n=== FastMCP Client 실제 동작 확인 ===")
    
    from fastmcp import Client
    
    # 다양한 URL 형식으로 Client 생성 시도
    urls_to_test = [
        "http://localhost:8001/mcp/",
        "http://localhost:8001/mcp",
        "http://localhost:8001/",
        "http://localhost:8001"
    ]
    
    for url in urls_to_test:
        print(f"\n--- FastMCP Client 테스트: {url} ---")
        try:
            async with Client(url, auth="Bearer test-mcp-key") as client:
                print(f"✅ 연결 성공: {url}")
                
                # 간単한 작업 수행
                tools = await client.list_tools()
                print(f"  도구 수: {len(tools)}")
                if tools:
                    print(f"  첫 번째 도구: {tools[0].name}")
                break
                
        except Exception as e:
            print(f"❌ 연결 실패: {url} - {e}")


async def analyze_fastmcp_internals():
    """FastMCP 내부 구조 분석"""
    print("\n=== FastMCP 내부 구조 분석 ===")
    
    from fastmcp import FastMCP
    
    # FastMCP 객체의 속성과 메소드 확인
    print("FastMCP 클래스 속성:")
    fastmcp_attrs = [attr for attr in dir(FastMCP) if not attr.startswith('_')]
    for attr in fastmcp_attrs[:20]:  # 처음 20개만
        print(f"  - {attr}")
    
    print("\nFastMCP 인스턴스 메소드:")
    from src.server_unified import UnifiedMCPServer, ServerConfig
    config = ServerConfig.from_env()
    unified_server = UnifiedMCPServer(config)
    mcp = unified_server.create_server()
    
    mcp_attrs = [attr for attr in dir(mcp) if not attr.startswith('_')]
    for attr in mcp_attrs[:20]:
        print(f"  - {attr}")


async def main():
    """메인 함수"""
    await test_fastmcp_endpoints()
    await test_fastmcp_client_behavior()
    await analyze_fastmcp_internals()


if __name__ == "__main__":
    asyncio.run(main())