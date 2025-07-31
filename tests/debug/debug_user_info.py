#!/usr/bin/env python3
"""
사용자 정보 확인 스크립트
"""

import asyncio
import httpx
import json


async def check_user_info():
    """사용자 정보 확인"""
    
    async with httpx.AsyncClient() as client:
        # 로그인
        login_resp = await client.post(
            "http://localhost:8000/auth/login",
            json={"email": "debug2@test.com", "password": "Debug123!"}
        )
        
        if login_resp.status_code != 200:
            print(f"로그인 실패: {login_resp.text}")
            return
        
        token_data = login_resp.json()
        access_token = token_data["access_token"]
        print(f"토큰 획득: {access_token[:20]}...")
        
        # 사용자 정보 확인
        headers = {"Authorization": f"Bearer {access_token}"}
        me_resp = await client.get("http://localhost:8000/auth/me", headers=headers)
        
        if me_resp.status_code == 200:
            user_info = me_resp.json()
            print(f"사용자 정보: {json.dumps(user_info, indent=2, ensure_ascii=False)}")
            
            # 역할 정보 확인
            roles = user_info.get("roles", [])
            print(f"사용자 역할: {roles}")
            
            # 역할이 없거나 guest인 경우 문제일 수 있음
            if not roles or roles == ["guest"]:
                print("⚠️  사용자가 guest 역할이거나 역할이 없습니다.")
                print("   이것이 MCP 요청 실패의 원인일 수 있습니다.")
        else:
            print(f"사용자 정보 조회 실패: {me_resp.text}")


if __name__ == "__main__":
    asyncio.run(check_user_info())