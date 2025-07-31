#!/usr/bin/env python3
"""
FastMCP Bearer 인증 테스트

FastMCP의 표준 Bearer 인증 방식이 올바르게 동작하는지 검증합니다.
특히 잘못된 인증 정보 제공 시 무조건 거부되는지 확인합니다.
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastmcp import Client
from src.auth.services.jwt_service import JWTService


async def test_no_auth_required_methods():
    """인증이 필요 없는 메서드 테스트"""
    print("\n[테스트 1] 인증 없이 허용되는 메서드")
    
    try:
        async with Client("http://localhost:8001/mcp/") as client:
            # tools/list는 인증 없이 접근 가능해야 함
            tools = await client.list_tools()
            print(f"✅ tools/list 성공: {len(tools)} 개 도구")
            return True
    except Exception as e:
        print(f"❌ 실패: {e}")
        return False


async def test_invalid_token_rejection():
    """잘못된 토큰 거부 테스트"""
    print("\n[테스트 2] 잘못된 토큰으로 도구 호출 (반드시 거부되어야 함)")
    
    try:
        async with Client(
            "http://localhost:8001/mcp/",
            auth="invalid-jwt-token-12345"
        ) as client:
            # 잘못된 토큰으로 도구 호출 시도
            result = await client.call_tool("health_check", {})
            print(f"❌ 잘못된 토큰이 허용됨! 결과: {result}")
            return False
    except Exception as e:
        print(f"✅ 예상대로 거부됨: {str(e)[:100]}...")
        return True


async def test_expired_token_rejection():
    """만료된 토큰 거부 테스트"""
    print("\n[테스트 3] 만료된 JWT 토큰으로 도구 호출")
    
    # 만료된 토큰 생성 (과거 시간으로)
    jwt_service = JWTService(
        secret_key=os.getenv("JWT_SECRET_KEY", "test-secret-key"),
        algorithm="HS256",
        access_token_expire_minutes=-1  # 이미 만료됨
    )
    
    expired_token = jwt_service.create_access_token(
        user_id="expired-user",
        email="expired@example.com",
        roles=["user"]
    )
    
    try:
        async with Client(
            "http://localhost:8001/mcp/",
            auth=expired_token
        ) as client:
            result = await client.call_tool("health_check", {})
            print(f"❌ 만료된 토큰이 허용됨! 결과: {result}")
            return False
    except Exception as e:
        print(f"✅ 예상대로 거부됨: {str(e)[:100]}...")
        return True


async def test_valid_token_acceptance():
    """유효한 토큰 허용 테스트"""
    print("\n[테스트 4] 유효한 JWT 토큰으로 도구 호출")
    
    jwt_service = JWTService(
        secret_key=os.getenv("JWT_SECRET_KEY", "test-secret-key"),
        algorithm="HS256"
    )
    
    valid_token = jwt_service.create_access_token(
        user_id="valid-user",
        email="valid@example.com",
        roles=["user"]
    )
    
    try:
        async with Client(
            "http://localhost:8001/mcp/",
            auth=valid_token
        ) as client:
            result = await client.call_tool("health_check", {})
            print(f"✅ 유효한 토큰 허용됨")
            return True
    except Exception as e:
        print(f"❌ 유효한 토큰이 거부됨: {e}")
        return False


async def test_internal_api_key():
    """내부 API 키 테스트"""
    print("\n[테스트 5] 내부 API 키로 도구 호출")
    
    internal_key = os.getenv("MCP_INTERNAL_API_KEY", "your-internal-api-key-change-in-production")
    
    try:
        async with Client(
            "http://localhost:8001/mcp/",
            auth=internal_key
        ) as client:
            result = await client.call_tool("health_check", {})
            print(f"✅ 내부 API 키 허용됨")
            return True
    except Exception as e:
        print(f"❌ 내부 API 키 거부됨: {e}")
        return False


async def test_wrong_internal_key_rejection():
    """잘못된 내부 API 키 거부 테스트"""
    print("\n[테스트 6] 잘못된 내부 API 키로 도구 호출")
    
    try:
        async with Client(
            "http://localhost:8001/mcp/",
            auth="wrong-internal-api-key"
        ) as client:
            result = await client.call_tool("health_check", {})
            print(f"❌ 잘못된 내부 키가 허용됨! 결과: {result}")
            return False
    except Exception as e:
        print(f"✅ 예상대로 거부됨: {str(e)[:100]}...")
        return True


async def test_empty_auth_header():
    """빈 인증 헤더 테스트"""
    print("\n[테스트 7] 빈 인증 헤더로 도구 호출")
    
    try:
        async with Client(
            "http://localhost:8001/mcp/",
            auth=""  # 빈 문자열
        ) as client:
            result = await client.call_tool("health_check", {})
            print(f"❌ 빈 인증 헤더가 허용됨! 결과: {result}")
            return False
    except Exception as e:
        print(f"✅ 예상대로 거부됨: {str(e)[:100]}...")
        return True


async def main():
    """메인 테스트 함수"""
    print("FastMCP Bearer 인증 테스트")
    print("="*50)
    print("중요: 잘못된 인증 정보는 무조건 거부되어야 합니다!")
    print("="*50)
    
    # 서버 연결 확인
    try:
        async with Client("http://localhost:8001/mcp/") as client:
            print("✅ MCP 서버 연결 확인")
    except Exception as e:
        print(f"❌ MCP 서버 연결 실패: {e}")
        return
    
    # 테스트 실행
    results = []
    
    results.append(("no_auth_required", await test_no_auth_required_methods()))
    results.append(("invalid_token_rejection", await test_invalid_token_rejection()))
    results.append(("expired_token_rejection", await test_expired_token_rejection()))
    results.append(("valid_token_acceptance", await test_valid_token_acceptance()))
    results.append(("internal_api_key", await test_internal_api_key()))
    results.append(("wrong_internal_key", await test_wrong_internal_key_rejection()))
    results.append(("empty_auth_header", await test_empty_auth_header()))
    
    # 결과 요약
    print("\n" + "="*50)
    print("테스트 결과 요약")
    print("="*50)
    
    total = len(results)
    passed = sum(1 for _, success in results if success)
    
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{test_name:<30} {status}")
    
    print("-"*50)
    print(f"총 {total}개 테스트 중 {passed}개 성공")
    
    # 중요한 테스트 강조
    critical_tests = [
        "invalid_token_rejection",
        "expired_token_rejection", 
        "wrong_internal_key",
        "empty_auth_header"
    ]
    
    critical_passed = sum(
        1 for name, success in results 
        if name in critical_tests and success
    )
    
    print(f"\n중요: 거부 테스트 {critical_passed}/{len(critical_tests)} 성공")
    
    if critical_passed < len(critical_tests):
        print("⚠️  경고: 잘못된 인증이 거부되지 않고 있습니다!")
    else:
        print("✅ 모든 잘못된 인증이 올바르게 거부됩니다!")


if __name__ == "__main__":
    asyncio.run(main())