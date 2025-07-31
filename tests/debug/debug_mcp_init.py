#!/usr/bin/env python3
"""
MCP 서버 초기화 디버깅 스크립트
"""

import asyncio
import httpx
import json


async def test_mcp_server_init():
    """MCP 서버 직접 초기화 테스트"""
    
    async with httpx.AsyncClient() as client:
        print("=== MCP 서버 직접 초기화 테스트 ===")
        
        # 1. 초기화 요청 (Auth Gateway와 동일한 방식)
        init_request = {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {
                    "name": "mcp",
                    "version": "0.1.0"
                }
            }
        }
        
        headers = {
            "content-type": "application/json",
            "accept": "application/json, text/event-stream",
            "authorization": "Bearer your-internal-api-key-change-in-production",
            "x-user-roles": "user"  # Auth Gateway에서 보내는 역할과 동일
        }
        
        print(f"요청 헤더: {json.dumps(headers, indent=2)}")
        print(f"요청 본문: {json.dumps(init_request, indent=2)}")
        
        try:
            response = await client.post(
                "http://localhost:8001/mcp/",
                json=init_request,
                headers=headers,
                timeout=10.0
            )
            
            print(f"\n초기화 응답 상태: {response.status_code}")
            print(f"응답 헤더: {dict(response.headers)}")
            
            if response.status_code == 200:
                # SSE 응답 처리
                response_text = response.text
                print(f"응답 텍스트: {response_text}")
                
                # SSE 형식에서 JSON 데이터 추출
                result = None
                if "data: " in response_text:
                    for line in response_text.split('\n'):
                        if line.startswith('data: '):
                            json_data = line[6:]  # "data: " 제거
                            if json_data.strip():
                                try:
                                    result = json.loads(json_data)
                                    break
                                except:
                                    continue
                
                if result:
                    print(f"응답 내용: {json.dumps(result, indent=2, ensure_ascii=False)}")
                else:
                    print("JSON 데이터를 추출할 수 없습니다")
                
                # 세션 ID 확인
                session_id = response.headers.get("mcp-session-id")
                if session_id:
                    print(f"세션 ID: {session_id}")
                    
                    # 2. notifications/initialized 알림 전송
                    print("\n=== initialized 알림 전송 ===")
                    
                    notif_request = {
                        "jsonrpc": "2.0",
                        "method": "notifications/initialized",
                        "params": {}
                    }
                    
                    headers["mcp-session-id"] = session_id
                    
                    notif_response = await client.post(
                        "http://localhost:8001/mcp/",
                        json=notif_request,
                        headers=headers,
                        timeout=10.0
                    )
                    
                    print(f"알림 응답 상태: {notif_response.status_code}")
                    
                    # 3. 도구 목록 요청
                    print("\n=== 도구 목록 요청 ===")
                    
                    tools_request = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/list"
                    }
                    
                    tools_response = await client.post(
                        "http://localhost:8001/mcp/",
                        json=tools_request,
                        headers=headers,
                        timeout=10.0
                    )
                    
                    print(f"도구 목록 응답 상태: {tools_response.status_code}")
                    if tools_response.status_code == 200:
                        tools_result = tools_response.json()
                        print(f"도구 목록: {json.dumps(tools_result, indent=2, ensure_ascii=False)}")
                    else:
                        print(f"도구 목록 오류: {tools_response.text}")
                        
                else:
                    print("세션 ID가 응답에 없습니다")
            else:
                print(f"초기화 실패: {response.text}")
                
        except Exception as e:
            print(f"요청 오류: {e}")


if __name__ == "__main__":
    asyncio.run(test_mcp_server_init())