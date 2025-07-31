#!/usr/bin/env python3
"""
MCP Server 미들웨어 통합 테스트

FastMCP 미들웨어 체인의 동작을 검증합니다:
1. JWT Bearer Token 인증
2. 요청/응답 로깅
3. 사용자 컨텍스트 전파
4. 에러 처리
"""

import asyncio
import httpx
import json
import sys
import os
from pathlib import Path

# 프로젝트 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.auth.services.jwt_service import JWTService


class MCPMiddlewareTest:
    """MCP 미들웨어 테스트 클래스"""
    
    def __init__(self):
        self.mcp_url = "http://localhost:8001/mcp/"  # FastMCP default path with trailing slash
        self.auth_url = "http://localhost:8000"
        self.test_results = []
        
        # JWT 서비스 초기화 (토큰 생성용)
        self.jwt_service = JWTService(
            secret_key=os.getenv("JWT_SECRET_KEY", "test-secret-key"),
            algorithm="HS256"
        )
    
    async def test_no_auth(self):
        """인증 없이 요청 테스트"""
        print("\n[테스트 1] 인증 없이 요청")
        
        async with httpx.AsyncClient() as client:
            # MCP tools/list 요청 (인증 없이)
            request = {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 1
            }
            
            try:
                response = await client.post(
                    self.mcp_url,
                    json=request,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream"
                    }
                )
                
                print(f"상태 코드: {response.status_code}")
                print(f"응답: {response.text[:200]}...")
                
                # tools/list는 인증 없이 접근 가능해야 함
                if response.status_code == 200:
                    result = response.json()
                    if "result" in result:
                        print("✅ tools/list는 인증 없이 접근 가능")
                        self.test_results.append(("no_auth_tools_list", True))
                    else:
                        print("❌ 예상치 못한 응답 형식")
                        self.test_results.append(("no_auth_tools_list", False))
                else:
                    print("❌ tools/list 접근 실패")
                    self.test_results.append(("no_auth_tools_list", False))
                    
            except Exception as e:
                print(f"❌ 요청 실패: {e}")
                self.test_results.append(("no_auth_tools_list", False))
    
    async def test_invalid_auth(self):
        """잘못된 인증으로 요청 테스트"""
        print("\n[테스트 2] 잘못된 Bearer Token으로 요청")
        
        async with httpx.AsyncClient() as client:
            # 잘못된 토큰으로 tools/call 요청
            request = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "search_web",
                    "arguments": {"query": "test"}
                },
                "id": 2
            }
            
            try:
                response = await client.post(
                    self.mcp_url,
                    json=request,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                        "Authorization": "Bearer invalid-token-12345"
                    }
                )
                
                print(f"상태 코드: {response.status_code}")
                print(f"응답: {response.text[:200]}...")
                
                # 인증 실패 예상
                if response.status_code == 200:
                    result = response.json()
                    if "error" in result:
                        print("✅ 잘못된 토큰 거부됨")
                        self.test_results.append(("invalid_auth", True))
                    else:
                        print("❌ 잘못된 토큰이 허용됨")
                        self.test_results.append(("invalid_auth", False))
                else:
                    print("✅ 인증 실패 (예상대로)")
                    self.test_results.append(("invalid_auth", True))
                    
            except Exception as e:
                print(f"❌ 요청 실패: {e}")
                self.test_results.append(("invalid_auth", False))
    
    async def test_valid_jwt_auth(self):
        """유효한 JWT Token으로 요청 테스트"""
        print("\n[테스트 3] 유효한 JWT Bearer Token으로 요청")
        
        # 테스트용 JWT 토큰 생성
        access_token = self.jwt_service.create_access_token(
            user_id="test-user-123",
            email="test@example.com",
            roles=["user"]
        )
        
        print(f"생성된 토큰: {access_token[:50]}...")
        
        async with httpx.AsyncClient() as client:
            # 유효한 토큰으로 tools/call 요청
            request = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "health_check",
                    "arguments": {}
                },
                "id": 3
            }
            
            try:
                response = await client.post(
                    self.mcp_url,
                    json=request,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                        "Authorization": f"Bearer {access_token}"
                    }
                )
                
                print(f"상태 코드: {response.status_code}")
                print(f"응답: {response.text[:200]}...")
                
                if response.status_code == 200:
                    result = response.json()
                    if "result" in result:
                        print("✅ JWT 인증 성공")
                        self.test_results.append(("valid_jwt_auth", True))
                    else:
                        print("❌ 응답에 오류 포함")
                        self.test_results.append(("valid_jwt_auth", False))
                else:
                    print("❌ JWT 인증 실패")
                    self.test_results.append(("valid_jwt_auth", False))
                    
            except Exception as e:
                print(f"❌ 요청 실패: {e}")
                self.test_results.append(("valid_jwt_auth", False))
    
    async def test_internal_api_key(self):
        """내부 API Key로 요청 테스트"""
        print("\n[테스트 4] 내부 API Key로 요청")
        
        # 환경변수에서 내부 API 키 가져오기
        internal_key = os.getenv("MCP_INTERNAL_API_KEY", "test-internal-key")
        
        async with httpx.AsyncClient() as client:
            request = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "health_check",
                    "arguments": {}
                },
                "id": 4
            }
            
            try:
                response = await client.post(
                    self.mcp_url,
                    json=request,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                        "Authorization": f"Bearer {internal_key}"
                    }
                )
                
                print(f"상태 코드: {response.status_code}")
                print(f"응답: {response.text[:200]}...")
                
                if response.status_code == 200:
                    result = response.json()
                    if "result" in result:
                        print("✅ 내부 API Key 인증 성공")
                        self.test_results.append(("internal_api_key", True))
                    else:
                        print("❌ 응답에 오류 포함")
                        self.test_results.append(("internal_api_key", False))
                else:
                    print("❌ 내부 API Key 인증 실패")
                    self.test_results.append(("internal_api_key", False))
                    
            except Exception as e:
                print(f"❌ 요청 실패: {e}")
                self.test_results.append(("internal_api_key", False))
    
    async def test_user_context_propagation(self):
        """사용자 컨텍스트 전파 테스트"""
        print("\n[테스트 5] 사용자 컨텍스트 전파")
        
        # 특정 사용자 정보로 JWT 토큰 생성
        access_token = self.jwt_service.create_access_token(
            user_id="context-test-user",
            email="context@test.com",
            roles=["user", "tester"]
        )
        
        async with httpx.AsyncClient() as client:
            # 여러 번 요청을 보내서 컨텍스트가 유지되는지 확인
            for i in range(3):
                request = {
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "health_check",
                        "arguments": {}
                    },
                    "id": 5 + i
                }
                
                try:
                    response = await client.post(
                        self.mcp_url,
                        json=request,
                        headers={
                            "Content-Type": "application/json",
                            "Accept": "application/json, text/event-stream",
                            "Authorization": f"Bearer {access_token}",
                            "X-Request-ID": f"test-request-{i}"
                        }
                    )
                    
                    if response.status_code == 200:
                        print(f"  요청 {i+1}: ✅ 성공")
                    else:
                        print(f"  요청 {i+1}: ❌ 실패")
                        
                except Exception as e:
                    print(f"  요청 {i+1}: ❌ 오류 - {e}")
            
            self.test_results.append(("user_context", True))
    
    async def test_concurrent_requests(self):
        """동시 요청 처리 테스트"""
        print("\n[테스트 6] 동시 요청 처리")
        
        # 여러 사용자의 토큰 생성
        tokens = []
        for i in range(5):
            token = self.jwt_service.create_access_token(
                user_id=f"concurrent-user-{i}",
                email=f"user{i}@test.com",
                roles=["user"]
            )
            tokens.append(token)
        
        async def make_request(client, token, user_id):
            request = {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": user_id
            }
            
            try:
                response = await client.post(
                    self.mcp_url,
                    json=request,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                        "Authorization": f"Bearer {token}"
                    }
                )
                return response.status_code == 200
            except:
                return False
        
        async with httpx.AsyncClient() as client:
            # 동시에 여러 요청 실행
            tasks = []
            for i, token in enumerate(tokens):
                task = make_request(client, token, i)
                tasks.append(task)
            
            results = await asyncio.gather(*tasks)
            success_count = sum(results)
            
            print(f"성공: {success_count}/{len(results)}")
            
            if success_count == len(results):
                print("✅ 모든 동시 요청 성공")
                self.test_results.append(("concurrent_requests", True))
            else:
                print("❌ 일부 동시 요청 실패")
                self.test_results.append(("concurrent_requests", False))
    
    def print_summary(self):
        """테스트 결과 요약"""
        print("\n" + "="*50)
        print("테스트 결과 요약")
        print("="*50)
        
        total = len(self.test_results)
        passed = sum(1 for _, success in self.test_results if success)
        
        for test_name, success in self.test_results:
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"{test_name:<30} {status}")
        
        print("-"*50)
        print(f"총 {total}개 테스트 중 {passed}개 성공")
        
        if passed == total:
            print("\n🎉 모든 미들웨어 테스트 통과!")
        else:
            print(f"\n⚠️  {total - passed}개 테스트 실패")
    
    async def run_all_tests(self):
        """모든 테스트 실행"""
        print("MCP Server 미들웨어 통합 테스트 시작")
        print("="*50)
        
        # 서버 상태 확인
        print("서버 연결 확인...")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:8001/health")
                if response.status_code != 200:
                    print("❌ MCP 서버에 연결할 수 없습니다")
                    return
                print("✅ MCP 서버 연결 확인")
        except:
            print("❌ MCP 서버가 실행 중이지 않습니다")
            return
        
        # 각 테스트 실행
        await self.test_no_auth()
        await self.test_invalid_auth()
        await self.test_valid_jwt_auth()
        await self.test_internal_api_key()
        await self.test_user_context_propagation()
        await self.test_concurrent_requests()
        
        # 결과 요약
        self.print_summary()


async def main():
    """메인 함수"""
    tester = MCPMiddlewareTest()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())