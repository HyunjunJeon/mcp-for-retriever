"""올바른 MCP 프로토콜 형식으로 테스트"""

import asyncio
import httpx
import json


async def test_correct_mcp_protocol():
    """FastMCP Client와 동일한 형식으로 MCP 프로토콜 테스트"""
    print("=== 올바른 MCP 프로토콜 형식 테스트 ===")
    
    async with httpx.AsyncClient() as client:
        # 1. initialize 요청 (FastMCP Client와 동일한 형식)
        print("\n--- initialize 요청 (올바른 형식) ---")
        init_response = await client.post(
            "http://localhost:8001/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",  # FastMCP Client가 사용하는 버전
                    "capabilities": {},
                    "clientInfo": {
                        "name": "mcp",
                        "version": "0.1.0"
                    }
                },
                "id": 0
            },
            headers={
                "Authorization": "Bearer test-mcp-key",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            }
        )
        
        print(f"초기화 상태: {init_response.status_code}")
        session_id = init_response.headers.get("mcp-session-id")
        print(f"세션 ID: {session_id}")
        
        if init_response.status_code != 200 or not session_id:
            print("❌ 초기화 실패")
            print(f"응답: {init_response.text}")
            return False
        
        # 2. notifications/initialized 알림 (정확한 메소드명)
        print("\n--- notifications/initialized 알림 ---")
        initialized_response = await client.post(
            "http://localhost:8001/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",  # 정확한 메소드명!
                "params": None  # FastMCP Client가 사용하는 형식
            },
            headers={
                "Authorization": "Bearer test-mcp-key",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "mcp-session-id": session_id
            }
        )
        print(f"Initialized 상태: {initialized_response.status_code}")
        
        # 3. tools/list 요청 (params=None 사용)
        print("\n--- tools/list 요청 (params=None) ---")
        tools_response = await client.post(
            "http://localhost:8001/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "tools/list",
                "params": None,  # 빈 객체가 아닌 None!
                "id": 1
            },
            headers={
                "Authorization": "Bearer test-mcp-key",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "mcp-session-id": session_id
            }
        )
        
        print(f"Tools/list 상태: {tools_response.status_code}")
        
        # SSE 응답 처리
        if tools_response.headers.get("content-type", "").startswith("text/event-stream"):
            print("SSE 응답:")
            for line in tools_response.text.split('\n'):
                if line.startswith('data: '):
                    json_data = line[6:]  # "data: " 제거
                    if json_data.strip():
                        try:
                            data = json.loads(json_data)
                            print(f"📤 {json.dumps(data, indent=2, ensure_ascii=False)}")
                            
                            # 성공한 경우 도구 목록 확인
                            if "result" in data and "tools" in data["result"]:
                                tools = data["result"]["tools"]
                                print(f"\n🎉 성공! 도구 목록 ({len(tools)}개):")
                                for tool in tools:
                                    print(f"  ✅ {tool.get('name', 'unknown')}")
                                return True
                            elif "error" in data:
                                print(f"\n❌ 오류: {data['error']['message']}")
                                return False
                        except json.JSONDecodeError:
                            print(f"Raw data: {json_data}")
        else:
            try:
                response_data = tools_response.json()
                print(f"📤 {json.dumps(response_data, indent=2, ensure_ascii=False)}")
                
                if "result" in response_data and "tools" in response_data["result"]:
                    tools = response_data["result"]["tools"]
                    print(f"\n🎉 성공! 도구 목록 ({len(tools)}개):")
                    for tool in tools:
                        print(f"  ✅ {tool.get('name', 'unknown')}")
                    return True
            except:
                print(f"Raw Response: {tools_response.text}")
        
        return False


async def test_variations():
    """다양한 params 형식 테스트"""
    print("\n=== params 형식 변형 테스트 ===")
    
    async with httpx.AsyncClient() as client:
        # 초기화
        init_response = await client.post(
            "http://localhost:8001/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"}
                },
                "id": 0
            },
            headers={
                "Authorization": "Bearer test-mcp-key",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            }
        )
        
        session_id = init_response.headers.get("mcp-session-id")
        if not session_id:
            print("❌ 초기화 실패")
            return
        
        # notifications/initialized 알림
        await client.post(
            "http://localhost:8001/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": None
            },
            headers={
                "Authorization": "Bearer test-mcp-key",
                "Content-Type": "application/json", 
                "Accept": "application/json, text/event-stream",
                "mcp-session-id": session_id
            }
        )
        
        # 다양한 tools/list 형식 시도
        variations = [
            {"name": "params: None", "payload": {"jsonrpc": "2.0", "method": "tools/list", "params": None, "id": 1}},
            {"name": "params 없음", "payload": {"jsonrpc": "2.0", "method": "tools/list", "id": 2}},
            {"name": "params: {}", "payload": {"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 3}},
        ]
        
        for variation in variations:
            print(f"\n--- {variation['name']} ---")
            
            response = await client.post(
                "http://localhost:8001/mcp/",
                json=variation['payload'],
                headers={
                    "Authorization": "Bearer test-mcp-key",
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                    "mcp-session-id": session_id
                }
            )
            
            print(f"상태: {response.status_code}")
            
            if response.status_code == 200:
                if "tools" in response.text:
                    print("✅ 성공 - 도구 목록 포함")
                    return True
                else:
                    error_match = json.loads(response.text.split('data: ')[1].split('\n')[0])
                    if "error" in error_match:
                        print(f"❌ 오류: {error_match['error']['message']}")
                    else: 
                        print("⚠️ 성공이지만 도구 목록 없음")
        
        return False


async def main():
    """메인 테스트"""
    print("🚀 올바른 MCP 프로토콜 형식으로 테스트 시작")
    
    success = await test_correct_mcp_protocol()
    
    if success:
        print("\n🎉🎉🎉 드디어 성공! MCP 프로토콜 문제 해결됨!")
    else:
        print("\n😞 여전히 실패. 추가 테스트 실행...")
        await test_variations()


if __name__ == "__main__":
    asyncio.run(main())