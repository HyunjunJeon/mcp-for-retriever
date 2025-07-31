#!/usr/bin/env python3
"""FastHTML 렌더링 테스트"""

import requests

def test_fasthtml():
    base_url = "http://localhost:8000"
    session = requests.Session()
    
    # 로그인
    login_data = {
        "email": "admin@example.com",
        "password": "Admin123!"
    }
    
    response = session.post(f"{base_url}/auth/login", json=login_data)
    if response.status_code != 200:
        print("로그인 실패")
        return
    
    # Admin 페이지 HTML 가져오기
    admin_response = session.get(f"{base_url}/admin")
    
    if admin_response.status_code == 200:
        html = admin_response.text
        
        # HTML 첫 100자 출력
        print("HTML 시작 부분:")
        print(html[:200])
        print("\n...")
        
        # DOCTYPE 확인 (대소문자 구분 없이)
        if html.strip().lower().startswith("<!doctype"):
            print("\n✅ HTML이 정상적으로 렌더링됨")
        else:
            print("\n❌ HTML이 텍스트로 출력됨")
            print("첫 번째 태그:", html.split('>')[0] + '>')
    else:
        print(f"Admin 페이지 접근 실패: {admin_response.status_code}")

if __name__ == "__main__":
    test_fasthtml()