#!/usr/bin/env python3
"""
SSE 연결 문제 디버깅 스크립트

MCP Gateway와 MCP Server 간의 SSE 통신 문제를 디버깅합니다.
"""

import asyncio
import httpx
import json
from httpx_sse import aconnect_sse


async def test_direct_mcp_server():
    """MCP Server에 직접 연결 테스트"""
    print("\n=== MCP Server 직접 연결 테스트 ===")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. 일반 POST 요청 테스트
        print("\n1. 일반 POST 요청 테스트")
        try:
            response = await client.post(
                "http://localhost:8001/mcp/",
                json={
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "id": 1,
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "debug-client", "version": "1.0.0"}
                    }
                },
                headers={
                    "content-type": "application/json",
                    "accept": "application/json"
                }
            )
            print(f"Status: {response.status_code}")
            print(f"Headers: {dict(response.headers)}")
            print(f"Response: {response.text[:500]}")
        except Exception as e:
            print(f"Error: {type(e).__name__}: {e}")
        
        # 2. SSE 엔드포인트 테스트
        print("\n\n2. SSE 엔드포인트 테스트 (/mcp/sse)")
        try:
            async with aconnect_sse(
                client,
                "POST",
                "http://localhost:8001/mcp/sse",
                json={
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "id": 2,
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "debug-sse-client", "version": "1.0.0"}
                    }
                },
                headers={
                    "content-type": "application/json",
                    "accept": "text/event-stream"
                }
            ) as event_source:
                print("SSE 연결 성공")
                print(f"Response headers: {dict(event_source.response.headers)}")
                
                count = 0
                async for sse in event_source.aiter_sse():
                    count += 1
                    print(f"\nEvent #{count}:")
                    print(f"  Type: {sse.event}")
                    print(f"  Data: {sse.data}")
                    if count > 5:
                        break
                        
        except Exception as e:
            print(f"SSE Error: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()


async def test_auth_gateway_proxy():
    """Auth Gateway를 통한 프록시 테스트"""
    print("\n\n=== Auth Gateway 프록시 테스트 ===")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. 로그인
        print("\n1. 로그인")
        try:
            # 먼저 등록 시도
            await client.post(
                "http://localhost:8000/auth/register",
                json={"email": "debug@example.com", "password": "Debug123!"}
            )
        except:
            pass
        
        login_resp = await client.post(
            "http://localhost:8000/auth/login",
            json={"email": "debug@example.com", "password": "Debug123!"}
        )
        token = login_resp.json()["access_token"]
        print(f"Token: {token[:20]}...")
        
        # 2. MCP 일반 요청
        print("\n2. MCP 일반 POST 요청")
        try:
            response = await client.post(
                "http://localhost:8000/mcp/",
                json={
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "id": 3,
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "debug-proxy-client", "version": "1.0.0"}
                    }
                },
                headers={
                    "authorization": f"Bearer {token}",
                    "content-type": "application/json",
                    "accept": "application/json"
                }
            )
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text[:500]}")
        except Exception as e:
            print(f"Error: {type(e).__name__}: {e}")
        
        # 3. SSE 프록시
        print("\n3. SSE 프록시 요청")
        try:
            headers = {
                "authorization": f"Bearer {token}",
                "content-type": "application/json",
                "accept": "text/event-stream"
            }
            
            # Debug: 실제 요청 정보 출력
            request_data = {
                "jsonrpc": "2.0",
                "method": "initialize",
                "id": 4,
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "debug-proxy-sse", "version": "1.0.0"}
                }
            }
            print(f"Request headers: {headers}")
            print(f"Request body: {json.dumps(request_data, indent=2)}")
            
            async with aconnect_sse(
                client,
                "POST",
                "http://localhost:8000/mcp/sse",
                json=request_data,
                headers=headers
            ) as event_source:
                print("SSE 프록시 연결 성공")
                print(f"Response headers: {dict(event_source.response.headers)}")
                
                count = 0
                async for sse in event_source.aiter_sse():
                    count += 1
                    print(f"\nEvent #{count}:")
                    print(f"  Type: {sse.event}")
                    print(f"  Data: {sse.data}")
                    if count > 5:
                        break
                        
        except Exception as e:
            print(f"SSE Proxy Error: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()


async def main():
    """메인 디버그 함수"""
    print("SSE 연결 디버깅 시작...")
    
    # 1. 직접 연결 테스트
    await test_direct_mcp_server()
    
    # 2. 프록시 테스트
    await test_auth_gateway_proxy()
    
    print("\n\n=== 디버깅 완료 ===")


if __name__ == "__main__":
    asyncio.run(main())