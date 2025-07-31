#!/usr/bin/env python3
"""
MCP 서버 검색 도구 디버깅 스크립트
"""

import asyncio
import httpx
import json


async def test_auth_and_search():
    """Auth Gateway를 통한 검색 테스트"""
    
    async with httpx.AsyncClient() as client:
        # 1. 사용자 등록 및 로그인
        print("=== 사용자 등록 및 로그인 ===")
        
        # 등록 (실패해도 계속 진행)
        register_resp = await client.post(
            "http://localhost:8000/auth/register",
            json={
                "email": "debug2@test.com",
                "password": "Debug123!",
                "username": "debug_user2"
            }
        )
        print(f"등록 결과: {register_resp.status_code}")
        if register_resp.status_code != 200:
            print(f"등록 실패 (기존 사용자로 로그인 시도): {register_resp.text}")
        
        # 로그인
        login_resp = await client.post(
            "http://localhost:8000/auth/login",
            json={"email": "debug2@test.com", "password": "Debug123!"}
        )
        print(f"로그인 결과: {login_resp.status_code}")
        if login_resp.status_code != 200:
            print(f"로그인 실패: {login_resp.text}")
            return
        
        token_data = login_resp.json()
        access_token = token_data["access_token"]
        print(f"토큰 획득: {access_token[:20]}...")
        
        # 2. 도구 목록 확인
        print("\n=== 도구 목록 확인 ===")
        headers = {"Authorization": f"Bearer {access_token}"}
        
        tools_resp = await client.post(
            "http://localhost:8000/mcp/proxy",
            json={
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 1
            },
            headers=headers
        )
        print(f"도구 목록 응답: {tools_resp.status_code}")
        tools_result = tools_resp.json()
        print(f"응답 내용: {json.dumps(tools_result, indent=2, ensure_ascii=False)}")
        
        if "result" in tools_result and "tools" in tools_result["result"]:
            tools = tools_result["result"]["tools"]
            print(f"사용 가능한 도구 수: {len(tools)}")
            for tool in tools:
                print(f"  - {tool['name']}: {tool.get('description', 'No description')[:50]}...")
        
        # 3. health_check 도구 테스트
        print("\n=== health_check 도구 테스트 ===")
        health_resp = await client.post(
            "http://localhost:8000/mcp/proxy",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "health_check",
                    "arguments": {}
                },
                "id": 2
            },
            headers=headers
        )
        print(f"health_check 응답: {health_resp.status_code}")
        health_result = health_resp.json()
        print(f"응답 내용: {json.dumps(health_result, indent=2, ensure_ascii=False)}")
        
        # 4. search_database 도구 테스트 (간단한 쿼리)
        print("\n=== search_database 도구 테스트 ===")
        search_resp = await client.post(
            "http://localhost:8000/mcp/proxy",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "search_database",
                    "arguments": {
                        "query": "SELECT 1 as test_column",
                        "limit": 1
                    }
                },
                "id": 3
            },
            headers=headers
        )
        print(f"search_database 응답: {search_resp.status_code}")
        search_result = search_resp.json()
        print(f"응답 내용: {json.dumps(search_result, indent=2, ensure_ascii=False)}")


if __name__ == "__main__":
    asyncio.run(test_auth_and_search())