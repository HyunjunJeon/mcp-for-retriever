"""initialized 단계를 건너뛰고 직접 tools/list 테스트"""

import asyncio
import httpx
import json


async def test_skip_initialized():
    """initialized 없이 직접 tools/list 호출"""
    print("=== initialized 건너뛰기 테스트 ===")
    
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
        
        print(f"초기화 상태: {init_response.status_code}")
        session_id = init_response.headers.get("mcp-session-id")
        print(f"세션 ID: {session_id}")
        
        if init_response.status_code != 200 or not session_id:
            print("❌ 초기화 실패")
            return
        
        # 2. initialized 건너뛰고 바로 tools/list 호출
        print("\n--- initialized 건너뛰고 tools/list 직접 호출 ---")
        tools_response = await client.post(
            "http://localhost:8001/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 2
            },
            headers={
                "Authorization": "Bearer test-mcp-key",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "mcp-session-id": session_id
            }
        )
        
        print(f"Tools/list 상태: {tools_response.status_code}")
        
        # 응답 처리
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
                                print(f"✅ 도구 목록 ({len(tools)}개):")
                                for tool in tools:
                                    print(f"  - {tool.get('name', 'unknown')}")
                                return True
                        except json.JSONDecodeError:
                            print(f"Raw data: {json_data}")
        else:
            try:
                response_data = tools_response.json()
                print(f"📤 {json.dumps(response_data, indent=2, ensure_ascii=False)}")
                
                # 성공한 경우 도구 목록 확인
                if "result" in response_data and "tools" in response_data["result"]:
                    tools = response_data["result"]["tools"]
                    print(f"✅ 도구 목록 ({len(tools)}개):")
                    for tool in tools:
                        print(f"  - {tool.get('name', 'unknown')}")
                    return True
            except:
                print(f"Raw Response: {tools_response.text}")
        
        return False


async def test_with_params_variations():
    """다양한 params 형식으로 tools/list 테스트"""
    print("\n=== 다양한 params 형식 테스트 ===")
    
    async with httpx.AsyncClient() as client:
        # 초기화
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
        
        session_id = init_response.headers.get("mcp-session-id")
        if not session_id:
            print("❌ 세션 ID 없음")
            return
        
        # 다양한 형식 시도
        variations = [
            {"name": "params 없음", "payload": {"jsonrpc": "2.0", "method": "tools/list", "id": 2}},
            {"name": "빈 params", "payload": {"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 3}},
            {"name": "null params", "payload": {"jsonrpc": "2.0", "method": "tools/list", "params": None, "id": 4}},
        ]
        
        for variation in variations:
            print(f"\n--- {variation['name']} ---")
            
            # None 값 제거
            payload = {k: v for k, v in variation['payload'].items() if v is not None}
            
            response = await client.post(
                "http://localhost:8001/mcp/",
                json=payload,
                headers={
                    "Authorization": "Bearer test-mcp-key",
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                    "mcp-session-id": session_id
                }
            )
            
            print(f"상태: {response.status_code}")
            
            # 간단한 응답 체크
            if response.status_code == 200:
                if "tools" in response.text:
                    print("✅ 성공 - 도구 목록 포함")
                    return True
                else:
                    print("⚠️ 성공이지만 도구 목록 없음")
            else:
                print(f"❌ 실패: {response.text[:100]}")
        
        return False


async def main():
    """메인 테스트"""
    success1 = await test_skip_initialized()
    if success1:
        print("\n🎉 initialized 없이 성공!")
        return
    
    success2 = await test_with_params_variations()
    if success2:
        print("\n🎉 다른 형식으로 성공!")
        return
    
    print("\n😞 모든 시도 실패")


if __name__ == "__main__":
    asyncio.run(main())