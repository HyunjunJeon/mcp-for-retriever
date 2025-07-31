#!/usr/bin/env python3
"""
테스트 사용자 생성 스크립트

E2E 테스트를 위한 사용자들을 생성하고 적절한 역할을 할당합니다.
"""

import asyncio
import httpx
import uuid
import sys
from typing import Optional


async def create_user(base_url: str, email: str, password: str) -> Optional[dict]:
    """사용자 생성"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{base_url}/auth/register",
                json={"email": email, "password": password}
            )
            
            if response.status_code == 200:
                print(f"✅ 사용자 생성 성공: {email}")
                return response.json()
            elif response.status_code == 400:
                # 이미 존재하는 사용자 - 로그인 시도
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
                        print(f"ℹ️ 기존 사용자 사용: {email}")
                        return me_resp.json()
                
            print(f"❌ 사용자 생성/조회 실패: {email} - {response.text}")
            return None
            
        except Exception as e:
            print(f"❌ 오류 발생: {e}")
            return None


async def update_user_roles(base_url: str, admin_token: str, user_id: str, roles: list[str]) -> bool:
    """사용자 역할 업데이트"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.put(
                f"{base_url}/api/v1/admin/users/{user_id}/roles",
                json=roles,
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            
            if response.status_code == 200:
                print(f"✅ 역할 업데이트 성공: {roles}")
                return True
            else:
                print(f"❌ 역할 업데이트 실패: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ 오류 발생: {e}")
            return False


async def main():
    """메인 함수"""
    base_url = "http://localhost:8000"
    
    print("🚀 테스트 사용자 생성 시작\n")
    
    # 1. 초기 관리자 생성 (초기화 엔드포인트 사용)
    print("1️⃣ 초기 관리자 생성...")
    async with httpx.AsyncClient() as client:
        try:
            init_resp = await client.post(f"{base_url}/api/v1/init/admin")
            if init_resp.status_code == 200:
                admin_data = init_resp.json()
                print(f"✅ 초기 관리자 생성 성공: {admin_data['email']}")
            elif init_resp.status_code == 400:
                print("ℹ️ 이미 관리자가 존재합니다")
            else:
                print(f"❌ 초기 관리자 생성 실패: {init_resp.text}")
        except Exception as e:
            print(f"❌ 초기화 엔드포인트 호출 실패: {e}")
            return
    
    # 슈퍼 관리자 로그인 (기존 admin@example.com 사용)
    super_admin_email = "admin@example.com"
    super_admin_password = "Admin123!"
    
    async with httpx.AsyncClient() as client:
        login_resp = await client.post(
            f"{base_url}/auth/login",
            json={"email": super_admin_email, "password": super_admin_password}
        )
        
        if login_resp.status_code != 200:
            print("❌ 슈퍼 관리자 로그인 실패")
            return
            
        admin_token = login_resp.json()["access_token"]
        
        # 슈퍼 관리자 권한 확인
        me_resp = await client.get(
            f"{base_url}/auth/me",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        if me_resp.status_code == 200:
            admin_data = me_resp.json()
            if "admin" not in admin_data.get("roles", []):
                print("\n⚠️ 슈퍼 관리자에게 admin 역할이 없습니다.")
                print(f"User ID: {admin_data['id']}")
                print(f"Current roles: {admin_data.get('roles', [])}")
                print("\n수동으로 admin 역할을 부여한 후 다시 실행하세요.")
                return
    
    print("✅ 슈퍼 관리자 인증 성공\n")
    
    # 2. 테스트 사용자들 생성
    test_users = [
        {
            "email": "admin@test.com",
            "password": "Admin123!",
            "roles": ["admin"],
            "description": "테스트 관리자"
        },
        {
            "email": "analyst@test.com",
            "password": "Analyst123!",
            "roles": ["analyst"],
            "description": "테스트 분석가"
        },
        {
            "email": "viewer@test.com",
            "password": "Viewer123!",
            "roles": ["viewer"],
            "description": "테스트 뷰어"
        }
    ]
    
    for user_config in test_users:
        print(f"\n2️⃣ {user_config['description']} 생성...")
        
        # 사용자 생성
        user = await create_user(base_url, user_config["email"], user_config["password"])
        if not user:
            continue
        
        # 역할 업데이트
        print(f"   역할 업데이트 중: {user_config['roles']}")
        success = await update_user_roles(
            base_url,
            admin_token,
            user["id"],
            user_config["roles"]
        )
        
        if success:
            print(f"✅ {user_config['description']} 설정 완료")
        else:
            print(f"❌ {user_config['description']} 역할 설정 실패")
    
    print("\n✅ 테스트 사용자 생성 완료!")
    print("\n다음 명령으로 E2E 테스트를 실행할 수 있습니다:")
    print("PYTHONPATH=/Users/jhj/Desktop/personal/make-mcp-server-vibe uv run python tests/e2e/test_fine_grained_permissions_e2e.py")


if __name__ == "__main__":
    asyncio.run(main())