#!/usr/bin/env python3
"""
현재 사용자 목록 확인 스크립트
"""

import asyncio
import httpx
import json


async def main():
    """메인 함수"""
    base_url = "http://localhost:8000"
    
    print("🔍 현재 등록된 사용자 확인\n")
    
    # 테스트할 이메일 목록
    test_emails = [
        ("admin@test.com", "Admin123!"),
        ("analyst@test.com", "Analyst123!"),
        ("viewer@test.com", "Viewer123!"),
        ("superadmin@mcp.com", "SuperAdmin123!"),
        # E2E 테스트에서 생성된 사용자들
        ("admin@example.com", "Admin123!"),
        ("analyst@example.com", "Analyst123!"),
        ("viewer@example.com", "Viewer123!"),
    ]
    
    for email, password in test_emails:
        async with httpx.AsyncClient() as client:
            try:
                # 로그인 시도
                login_resp = await client.post(
                    f"{base_url}/auth/login",
                    json={"email": email, "password": password}
                )
                
                if login_resp.status_code == 200:
                    # 사용자 정보 조회
                    token = login_resp.json()["access_token"]
                    me_resp = await client.get(
                        f"{base_url}/auth/me",
                        headers={"Authorization": f"Bearer {token}"}
                    )
                    
                    if me_resp.status_code == 200:
                        user_data = me_resp.json()
                        print(f"✅ {email}")
                        print(f"   ID: {user_data['id']}")
                        print(f"   Roles: {user_data.get('roles', [])}")
                        print()
                else:
                    print(f"❌ {email} - 로그인 실패")
                    
            except Exception as e:
                print(f"❌ {email} - 오류: {e}")


if __name__ == "__main__":
    asyncio.run(main())