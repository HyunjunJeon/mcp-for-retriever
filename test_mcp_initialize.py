"""MCP 서버 초기화 테스트"""

import asyncio
import httpx
import json


async def test_mcp_initialize():
    """MCP 서버에 직접 초기화 요청 보내기"""
    print("=== MCP 서버 초기화 테스트 ===")
    
    async with httpx.AsyncClient() as client:
        # 1. initialize 요청
        print("\n--- initialize 요청 ---")
        init_response = await client.post(
            "http://localhost:8001/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "Test Client",
                        "version": "1.0.0"
                    }
                },
                "id": 1
            },
            headers={
                "Authorization": "Bearer test-mcp-key",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            }
        )
        
        print(f"Status: {init_response.status_code}")
        print(f"Headers: {dict(init_response.headers)}")
        
        # SSE 응답 처리
        if init_response.headers.get("content-type", "").startswith("text/event-stream"):
            print("SSE 응답:")
            print(init_response.text)
            
            # SSE에서 JSON 데이터 추출
            for line in init_response.text.split('\n'):
                if line.startswith('data: '):
                    json_data = line[6:]  # "data: " 제거
                    if json_data.strip():
                        try:
                            data = json.loads(json_data)
                            print(f"Parsed data: {json.dumps(data, indent=2, ensure_ascii=False)}")
                        except json.JSONDecodeError:
                            print(f"Raw data: {json_data}")
        else:
            try:
                print(f"JSON Response: {json.dumps(init_response.json(), indent=2, ensure_ascii=False)}")
            except:
                print(f"Raw Response: {init_response.text}")
        
        # 2. initialized 알림 (필요한 경우)
        print("\n--- initialized 알림 ---")
        initialized_response = await client.post(
            "http://localhost:8001/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "initialized",
                "params": {}
            },
            headers={
                "Authorization": "Bearer test-mcp-key",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            }
        )
        print(f"Initialized Status: {initialized_response.status_code}")
        
        # 세션 ID 추출
        session_id = init_response.headers.get("mcp-session-id")
        print(f"Session ID: {session_id}")
        
        # 3. tools/list 요청 (세션 ID 포함)
        print("\n--- tools/list 요청 (세션 ID 포함) ---")
        tools_response = await client.post(
            "http://localhost:8001/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "tools/list",
                "params": {},
                "id": 2
            },
            headers={
                "Authorization": "Bearer test-mcp-key",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "mcp-session-id": session_id
            }
        )
        
        print(f"Tools Status: {tools_response.status_code}")
        
        # SSE 응답 처리
        if tools_response.headers.get("content-type", "").startswith("text/event-stream"):
            print("Tools SSE 응답:")
            print(tools_response.text)
            
            # SSE에서 JSON 데이터 추출
            for line in tools_response.text.split('\n'):
                if line.startswith('data: '):
                    json_data = line[6:]  # "data: " 제거
                    if json_data.strip():
                        try:
                            data = json.loads(json_data)
                            print(f"Tools Parsed data: {json.dumps(data, indent=2, ensure_ascii=False)}")
                        except json.JSONDecodeError:
                            print(f"Tools Raw data: {json_data}")
        else:
            try:
                print(f"Tools JSON Response: {json.dumps(tools_response.json(), indent=2, ensure_ascii=False)}")
            except:
                print(f"Tools Raw Response: {tools_response.text}")


if __name__ == "__main__":
    asyncio.run(test_mcp_initialize())