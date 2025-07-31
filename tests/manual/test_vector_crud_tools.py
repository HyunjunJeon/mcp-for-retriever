#!/usr/bin/env python3
"""벡터 DB CRUD 도구 테스트"""

import asyncio
import httpx

async def test_vector_crud_tools():
    """벡터 DB CRUD 도구 접근 권한 테스트"""
    auth_base_url = "http://localhost:8000"
    
    # 테스트 사용자
    test_users = {
        "user": {"email": "user@example.com", "password": "User123!", "expected_crud": 0},
        "analyst": {"email": "analyst@example.com", "password": "Analyst123!", "expected_crud": 3},
        "admin": {"email": "admin@example.com", "password": "Admin123!", "expected_crud": 4}
    }
    
    crud_tools = [
        "create_vector_collection",
        "create_vector_document", 
        "update_vector_document",
        "delete_vector_document"
    ]
    
    async with httpx.AsyncClient() as client:
        print("=== 벡터 DB CRUD 도구 접근 권한 테스트 ===\n")
        
        for role, creds in test_users.items():
            # 등록 및 로그인
            try:
                # 이미 존재하는 사용자일 수 있으므로 등록 실패 무시
                register_resp = await client.post(f"{auth_base_url}/auth/register", json=creds)
                
                # 로그인은 항상 시도
                login_resp = await client.post(f"{auth_base_url}/auth/login", json=creds)
                
                if login_resp.status_code == 200:
                    token = login_resp.json()["access_token"]
                    
                    # 도구 목록 조회
                    tools_resp = await client.post(
                        f"{auth_base_url}/mcp/proxy",
                        json={
                            "jsonrpc": "2.0",
                            "method": "tools/list",
                            "id": 1
                        },
                        headers={"Authorization": f"Bearer {token}"}
                    )
                    
                    if tools_resp.status_code == 200:
                        result = tools_resp.json()
                        if "result" in result and "tools" in result["result"]:
                            tools = result["result"]["tools"]
                            tool_names = [tool["name"] for tool in tools]
                            
                            # CRUD 도구 확인
                            available_crud = [tool for tool in crud_tools if tool in tool_names]
                            
                            print(f"{role.upper()} 역할:")
                            print(f"  전체 도구 수: {len(tools)}")
                            print(f"  CRUD 도구 접근: {len(available_crud)}/{len(crud_tools)}")
                            
                            for tool in crud_tools:
                                if tool in tool_names:
                                    print(f"    ✅ {tool}")
                                else:
                                    print(f"    ❌ {tool}")
                            
                            # 예상값과 비교
                            if len(available_crud) != creds["expected_crud"]:
                                print(f"  ⚠️ 경고: 예상 {creds['expected_crud']}개, 실제 {len(available_crud)}개")
                            print()
                        else:
                            print(f"{role.upper()}: 도구 목록 형식 오류")
                    else:
                        print(f"{role.upper()}: 도구 목록 조회 실패 - {tools_resp.status_code}")
                else:
                    print(f"{role.upper()}: 로그인 실패")
                    
            except Exception as e:
                print(f"{role.upper()}: 오류 - {e}")

if __name__ == "__main__":
    asyncio.run(test_vector_crud_tools())