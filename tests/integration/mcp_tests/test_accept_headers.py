"""Accept 헤더 형식 테스트"""

import asyncio
import httpx
import json


async def test_accept_header_variations():
    """다양한 Accept 헤더 형식 테스트"""
    print("=== Accept 헤더 형식 테스트 ===")
    
    # 다양한 Accept 헤더 형식
    accept_variations = [
        "application/json, text/event-stream",
        "application/json,text/event-stream", 
        "text/event-stream, application/json",
        "text/event-stream,application/json",
        "application/json; text/event-stream",
        "text/event-stream; application/json",
        "*/*",
        "application/json",
        "text/event-stream",
        "application/json, text/event-stream, */*",
        "text/event-stream; q=0.9, application/json; q=1.0",
        "application/json; q=1.0, text/event-stream; q=0.9"
    ]
    
    base_headers = {
        "Authorization": "Bearer test-mcp-key",
        "Content-Type": "application/json"
    }
    
    test_payload = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "Test", "version": "1.0"}
        },
        "id": 1
    }
    
    async with httpx.AsyncClient() as client:
        for i, accept_header in enumerate(accept_variations, 1):
            print(f"\n--- 테스트 {i}: Accept = '{accept_header}' ---")
            
            headers = base_headers.copy()
            headers["Accept"] = accept_header
            
            try:
                response = await client.post(
                    "http://localhost:8001/mcp/",
                    json=test_payload,
                    headers=headers
                )
                
                print(f"상태: {response.status_code}")
                
                if response.status_code == 200:
                    print("✅ 성공!")
                    session_id = response.headers.get("mcp-session-id")
                    print(f"세션 ID: {session_id}")
                    
                    if session_id:
                        # 이 헤더로 tools/list도 시도
                        print("  tools/list 시도...")
                        tools_response = await client.post(
                            "http://localhost:8001/mcp/",
                            json={
                                "jsonrpc": "2.0",
                                "method": "tools/list",
                                "id": 2
                            },
                            headers={
                                **headers,
                                "mcp-session-id": session_id
                            }
                        )
                        print(f"  tools/list 상태: {tools_response.status_code}")
                        if "tools" in tools_response.text:
                            print("  ✅ tools/list 성공!")
                            return accept_header
                        else:
                            print(f"  ❌ tools/list 실패: {tools_response.text[:100]}")
                
                elif response.status_code == 406:
                    print("❌ 406 Not Acceptable")
                else:
                    print(f"❌ 오류: {response.text[:100]}")
                    
            except Exception as e:
                print(f"❌ 예외: {e}")
    
    return None


async def test_fastmcp_client_headers():
    """FastMCP Client가 실제로 사용하는 헤더 분석"""
    print("\n=== FastMCP Client 헤더 분석 ===")
    
    # HTTP 요청을 가로채서 헤더 확인
    import logging
    logging.basicConfig(level=logging.DEBUG)
    
    # httpx 로깅 활성화
    httpx_logger = logging.getLogger("httpx")
    httpx_logger.setLevel(logging.DEBUG)
    
    from fastmcp import Client
    
    try:
        async with Client(
            "http://localhost:8001/mcp/",
            auth="Bearer test-mcp-key"
        ) as client:
            print("✅ FastMCP Client 연결 성공")
            
            # 간단한 작업 수행
            tools = await client.list_tools()
            print(f"도구 수: {len(tools)}")
            
    except Exception as e:
        print(f"❌ FastMCP Client 오류: {e}")


async def test_precise_headers():
    """정확한 헤더 조합 테스트"""
    print("\n=== 정확한 헤더 조합 테스트 ===")
    
    # FastMCP Client와 동일한 헤더 시도
    precise_headers = {
        "Authorization": "Bearer test-mcp-key",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": "FastMCP/2.10.6",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive"
    }
    
    async with httpx.AsyncClient() as client:
        print("정확한 헤더로 initialize 시도...")
        
        response = await client.post(
            "http://localhost:8001/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "Test", "version": "1.0"}
                },
                "id": 1
            },
            headers=precise_headers
        )
        
        print(f"상태: {response.status_code}")
        print(f"응답 헤더: {dict(response.headers)}")
        
        if response.status_code == 200:
            session_id = response.headers.get("mcp-session-id")
            print(f"✅ 세션 ID: {session_id}")
            
            if session_id:
                # tools/list 시도
                tools_headers = precise_headers.copy()
                tools_headers["mcp-session-id"] = session_id
                
                tools_response = await client.post(
                    "http://localhost:8001/mcp/",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/list",
                        "id": 2
                    },
                    headers=tools_headers
                )
                
                print(f"tools/list 상태: {tools_response.status_code}")
                print(f"tools/list 응답: {tools_response.text[:200]}")
        else:
            print(f"❌ 실패: {response.text}")


async def main():
    """메인 함수"""
    # Accept 헤더 테스트
    successful_accept = await test_accept_header_variations()
    
    if successful_accept:
        print(f"\n🎉 성공한 Accept 헤더: {successful_accept}")
    else:
        print("\n😞 모든 Accept 헤더 실패")
    
    # FastMCP Client 헤더 분석
    await test_fastmcp_client_headers()
    
    # 정확한 헤더 조합 테스트
    await test_precise_headers()


if __name__ == "__main__":
    asyncio.run(main())