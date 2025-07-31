"""MCP 서버 직접 연결 테스트"""

import asyncio
from fastmcp import Client
import json


async def test_direct_mcp():
    """MCP 서버에 직접 연결해서 테스트"""
    print("=== MCP 서버 직접 연결 테스트 ===")
    
    try:
        # HTTP 프로토콜로 연결
        async with Client(
            "http://localhost:8001/mcp/",
            auth="Bearer test-mcp-key"
        ) as client:
            print("✅ 연결 성공")
            
            # 1. 도구 목록 가져오기
            print("\n--- 도구 목록 조회 ---")
            tools = await client.list_tools()
            for tool in tools:
                print(f"- {tool.name}")
            
            # 2. health_check 호출
            print("\n--- health_check 호출 ---")
            result = await client.call_tool("health_check", {})
            print(f"Health: {result.data}")
            
            # 3. search_vectors 호출 (권한 관련 테스트)
            print("\n--- search_vectors 호출 ---")
            try:
                result = await client.call_tool(
                    "search_vectors",
                    {
                        "query": "test query",
                        "collection": "documents",
                        "limit": 5
                    }
                )
                print(f"✅ search_vectors 성공: {result.data}")
            except Exception as e:
                print(f"⚠️ search_vectors 오류 (예상됨): {e}")
            
            # 4. 존재하지 않는 도구 호출
            print("\n--- 존재하지 않는 도구 호출 ---")
            try:
                result = await client.call_tool("non_existent_tool", {})
                print(f"❌ 예상치 못한 성공: {result.data}")
            except Exception as e:
                print(f"✅ 예상된 오류: {e}")
                
    except Exception as e:
        print(f"❌ 연결 실패: {e}")
        import traceback
        traceback.print_exc()


async def test_auth_gateway():
    """Auth Gateway 테스트"""
    print("\n=== Auth Gateway 테스트 ===")
    
    import httpx
    
    async with httpx.AsyncClient() as client:
        # 1. 사용자 등록
        print("\n--- 사용자 등록 ---")
        try:
            response = await client.post(
                "http://localhost:8000/auth/register",
                json={
                    "email": "test@example.com",
                    "password": "Test123!"
                }
            )
            print(f"등록 응답: {response.status_code}")
            if response.status_code != 200:
                print(f"등록 실패: {response.text}")
        except Exception as e:
            print(f"등록 오류: {e}")
        
        # 2. 로그인
        print("\n--- 로그인 ---")
        try:
            response = await client.post(
                "http://localhost:8000/auth/login",
                json={
                    "email": "test@example.com",
                    "password": "Test123!"
                }
            )
            print(f"로그인 응답: {response.status_code}")
            if response.status_code == 200:
                token_data = response.json()
                access_token = token_data["access_token"]
                print(f"✅ 로그인 성공, 토큰 획득")
                
                # 3. 인증된 사용자 정보 조회
                print("\n--- 사용자 정보 조회 ---")
                me_response = await client.get(
                    "http://localhost:8000/auth/me",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                print(f"사용자 정보: {me_response.json()}")
                
                # 4. MCP 프록시 테스트 (올바른 형식) - tools/list는 params가 없어야 함
                print("\n--- MCP 프록시 테스트 (tools/list) ---")
                proxy_response = await client.post(
                    "http://localhost:8000/mcp/proxy",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/list",
                        "id": 1
                    },
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                print(f"프록시 응답: {proxy_response.status_code}")
                if proxy_response.status_code == 200:
                    result = proxy_response.json()
                    print(f"프록시 성공: {json.dumps(result, indent=2, ensure_ascii=False)}")
                    
                    # 도구가 제대로 나왔으면 search_vectors 테스트
                    if "result" in result and result["result"]:
                        print("\n--- MCP 프록시 테스트 (search_vectors) ---")
                        search_response = await client.post(
                            "http://localhost:8000/mcp/proxy",
                            json={
                                "jsonrpc": "2.0",
                                "method": "tools/call",
                                "params": {
                                    "name": "search_vectors",
                                    "arguments": {
                                        "query": "test query",
                                        "collection": "documents",
                                        "limit": 5
                                    }
                                },
                                "id": 2
                            },
                            headers={"Authorization": f"Bearer {access_token}"}
                        )
                        search_result = search_response.json()
                        print(f"search_vectors 응답: {json.dumps(search_result, indent=2, ensure_ascii=False)}")
                else:
                    print(f"프록시 실패: {proxy_response.text}")
            else:
                print(f"로그인 실패: {response.text}")
        except Exception as e:
            print(f"로그인 오류: {e}")


async def main():
    """메인 테스트"""
    await test_direct_mcp()
    await test_auth_gateway()


if __name__ == "__main__":
    asyncio.run(main())