#!/usr/bin/env python3
"""
세션 ID 헤더 전달 테스트

Auth Gateway가 mcp-session-id 헤더를 제대로 전달하는지 확인합니다.
"""

import asyncio
import httpx
import json


async def main():
    """헤더 전달 테스트"""
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. 로그인
        print("=== 1. 로그인 ===")
        try:
            await client.post(
                "http://localhost:8000/auth/register",
                json={"email": "header_test@example.com", "password": "Test123!"}
            )
        except:
            pass
        
        login_resp = await client.post(
            "http://localhost:8000/auth/login",
            json={"email": "header_test@example.com", "password": "Test123!"}
        )
        token = login_resp.json()["access_token"]
        print(f"✅ 토큰 획득: {token[:20]}...")
        
        # 2. 일반 MCP 요청으로 초기화 (non-SSE)
        print("\n=== 2. 일반 MCP 초기화 요청 ===")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        
        init_resp = await client.post(
            "http://localhost:8000/mcp/proxy",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0.0"}
                }
            },
            headers=headers
        )
        
        print(f"응답 상태: {init_resp.status_code}")
        print(f"응답 헤더: {dict(init_resp.headers)}")
        init_data = init_resp.json()
        print(f"응답 데이터: {json.dumps(init_data, indent=2)}")
        
        # 세션 ID 추출
        session_id = init_resp.headers.get("mcp-session-id")
        if not session_id and "result" in init_data:
            session_id = init_data.get("result", {}).get("sessionId")
        
        if session_id:
            print(f"\n✅ 세션 ID 획득: {session_id}")
        else:
            print("\n❌ 세션 ID를 찾을 수 없음")
            return
        
        # 3. 세션 ID를 포함한 요청
        print("\n=== 3. 세션 ID 포함 요청 ===")
        headers["mcp-session-id"] = session_id
        print(f"요청 헤더: {list(headers.keys())}")
        
        tools_resp = await client.post(
            "http://localhost:8000/mcp/proxy",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list"
            },
            headers=headers
        )
        
        print(f"응답 상태: {tools_resp.status_code}")
        tools_data = tools_resp.json()
        if "error" in tools_data:
            print(f"❌ 에러: {tools_data['error']}")
        else:
            print(f"✅ 성공: {len(tools_data.get('result', {}).get('tools', []))}개 도구")


if __name__ == "__main__":
    asyncio.run(main())