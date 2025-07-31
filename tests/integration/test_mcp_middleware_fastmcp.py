#!/usr/bin/env python3
"""
MCP Server 미들웨어 통합 테스트 (FastMCP Client 사용)

FastMCP 클라이언트를 사용하여 미들웨어 체인의 동작을 검증합니다:
1. JWT Bearer Token 인증
2. 내부 API Key 인증
3. 미들웨어 동작 확인
"""

import asyncio
import os
import sys
from pathlib import Path

# 프로젝트 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastmcp import Client
from src.auth.services.jwt_service import JWTService


async def test_with_no_auth():
    """인증 없이 연결 테스트"""
    print("\n[테스트 1] 인증 없이 MCP 서버 연결")
    
    try:
        async with Client("http://localhost:8001/mcp/") as client:
            # 도구 목록 조회
            tools = await client.list_tools()
            print(f"✅ 도구 목록 조회 성공: {len(tools)} 개의 도구")
            for tool in tools[:3]:  # 처음 3개만 출력
                print(f"  - {tool.name}: {tool.description[:50]}...")
            return True
    except Exception as e:
        print(f"❌ 연결 실패: {e}")
        return False


async def test_with_invalid_token():
    """잘못된 토큰으로 연결 테스트"""
    print("\n[테스트 2] 잘못된 Bearer Token으로 연결")
    
    try:
        async with Client(
            "http://localhost:8001/mcp/",
            auth="invalid-token-12345"
        ) as client:
            # health_check 도구 호출
            result = await client.call_tool("health_check", {})
            print(f"❌ 잘못된 토큰이 허용됨: {result}")
            return False
    except Exception as e:
        print(f"✅ 예상대로 인증 실패: {str(e)[:100]}...")
        return True


async def test_with_valid_jwt():
    """유효한 JWT 토큰으로 연결 테스트"""
    print("\n[테스트 3] 유효한 JWT Bearer Token으로 연결")
    
    # JWT 서비스 초기화
    jwt_service = JWTService(
        secret_key=os.getenv("JWT_SECRET_KEY", "test-secret-key"),
        algorithm="HS256"
    )
    
    # 테스트용 JWT 토큰 생성
    access_token = jwt_service.create_access_token(
        user_id="test-user-123",
        email="test@example.com",
        roles=["user"]
    )
    
    print(f"생성된 토큰: {access_token[:50]}...")
    
    try:
        async with Client(
            "http://localhost:8001/mcp/",
            auth=access_token
        ) as client:
            # health_check 도구 호출
            result = await client.call_tool("health_check", {})
            print(f"✅ JWT 인증 성공")
            print(f"  서버 상태: {result.get('status', 'unknown')}")
            print(f"  활성 리트리버: {result.get('retrievers', {})}")
            return True
    except Exception as e:
        print(f"❌ JWT 인증 실패: {e}")
        return False


async def test_with_internal_key():
    """내부 API Key로 연결 테스트"""
    print("\n[테스트 4] 내부 API Key로 연결")
    
    # 환경변수에서 내부 API 키 가져오기
    internal_key = os.getenv("MCP_INTERNAL_API_KEY", "test-internal-key")
    
    try:
        async with Client(
            "http://localhost:8001/mcp/",
            auth=internal_key
        ) as client:
            # health_check 도구 호출
            result = await client.call_tool("health_check", {})
            print(f"✅ 내부 API Key 인증 성공")
            print(f"  서버 상태: {result.get('status', 'unknown')}")
            return True
    except Exception as e:
        print(f"❌ 내부 API Key 인증 실패: {e}")
        return False


async def test_concurrent_users():
    """여러 사용자의 동시 접속 테스트"""
    print("\n[테스트 5] 동시 다중 사용자 연결")
    
    # JWT 서비스 초기화
    jwt_service = JWTService(
        secret_key=os.getenv("JWT_SECRET_KEY", "test-secret-key"),
        algorithm="HS256"
    )
    
    # 여러 사용자의 토큰 생성
    users = []
    for i in range(3):
        token = jwt_service.create_access_token(
            user_id=f"concurrent-user-{i}",
            email=f"user{i}@test.com",
            roles=["user"]
        )
        users.append((f"User {i}", token))
    
    async def user_task(name, token):
        try:
            async with Client(
                "http://localhost:8001/mcp/",
                auth=token
            ) as client:
                # 각 사용자가 도구 목록 조회
                tools = await client.list_tools()
                print(f"  {name}: {len(tools)} 개 도구 확인")
                return True
        except Exception as e:
            print(f"  {name}: 실패 - {e}")
            return False
    
    # 동시에 모든 사용자 연결
    tasks = [user_task(name, token) for name, token in users]
    results = await asyncio.gather(*tasks)
    
    success_count = sum(results)
    print(f"\n  결과: {success_count}/{len(results)} 사용자 성공")
    
    return success_count == len(results)


async def test_tool_execution_with_auth():
    """인증된 상태에서 도구 실행 테스트"""
    print("\n[테스트 6] 인증된 사용자의 도구 실행")
    
    # JWT 서비스 초기화
    jwt_service = JWTService(
        secret_key=os.getenv("JWT_SECRET_KEY", "test-secret-key"),
        algorithm="HS256"
    )
    
    # Admin 권한 토큰 생성
    admin_token = jwt_service.create_access_token(
        user_id="admin-user",
        email="admin@example.com",
        roles=["admin", "user"]
    )
    
    try:
        async with Client(
            "http://localhost:8001/mcp/",
            auth=admin_token
        ) as client:
            # 웹 검색 도구 실행
            print("  웹 검색 도구 테스트...")
            result = await client.call_tool(
                "search_web",
                {"query": "FastMCP middleware", "limit": 3}
            )
            
            if isinstance(result, list) and len(result) > 0:
                print(f"  ✅ 웹 검색 성공: {len(result)} 개 결과")
                for item in result[:2]:
                    print(f"    - {item.get('title', 'No title')[:50]}...")
                return True
            else:
                print(f"  ⚠️  웹 검색 결과 없음")
                return True  # 결과가 없어도 도구 실행은 성공
                
    except Exception as e:
        print(f"  ❌ 도구 실행 실패: {e}")
        return False


async def main():
    """메인 테스트 함수"""
    print("FastMCP 미들웨어 통합 테스트")
    print("="*50)
    
    # 서버 연결 확인
    print("서버 연결 테스트...")
    try:
        # 간단히 클라이언트 생성 시도
        async with Client("http://localhost:8001/mcp/") as client:
            print("✅ MCP 서버 연결 확인")
    except Exception as e:
        print(f"❌ MCP 서버 연결 실패: {e}")
        return
    
    # 테스트 실행
    results = []
    
    # 각 테스트 실행
    results.append(("no_auth", await test_with_no_auth()))
    results.append(("invalid_token", await test_with_invalid_token()))
    results.append(("valid_jwt", await test_with_valid_jwt()))
    results.append(("internal_key", await test_with_internal_key()))
    results.append(("concurrent_users", await test_concurrent_users()))
    results.append(("tool_execution", await test_tool_execution_with_auth()))
    
    # 결과 요약
    print("\n" + "="*50)
    print("테스트 결과 요약")
    print("="*50)
    
    total = len(results)
    passed = sum(1 for _, success in results if success)
    
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{test_name:<20} {status}")
    
    print("-"*50)
    print(f"총 {total}개 테스트 중 {passed}개 성공")
    
    if passed == total:
        print("\n🎉 모든 미들웨어 테스트 통과!")
    else:
        print(f"\n⚠️  {total - passed}개 테스트 실패")


if __name__ == "__main__":
    asyncio.run(main())