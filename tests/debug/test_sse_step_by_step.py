#!/usr/bin/env python3
"""
SSE 통합 테스트를 단계별로 실행하여 문제를 파악합니다.
"""

import asyncio
import httpx
import json
from httpx_sse import aconnect_sse
import sys


class SSEDebugClient:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self.base_url = "http://localhost:8000"
        self.access_token = None
        self.session_id = None
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    async def authenticate(self):
        """인증"""
        print("\n=== 인증 단계 ===")
        
        # 등록 시도
        try:
            await self.client.post(
                f"{self.base_url}/auth/register",
                json={"email": "step_test@example.com", "password": "StepTest123!"}
            )
            print("✅ 사용자 등록 성공")
        except httpx.HTTPStatusError as e:
            print(f"ℹ️ 사용자 이미 존재 (정상)")
        
        # 로그인
        response = await self.client.post(
            f"{self.base_url}/auth/login",
            json={"email": "step_test@example.com", "password": "StepTest123!"}
        )
        response.raise_for_status()
        data = response.json()
        self.access_token = data["access_token"]
        print(f"✅ 로그인 성공, 토큰: {self.access_token[:20]}...")
    
    async def sse_request(self, method, params=None, request_id=1):
        """SSE 요청을 보내고 모든 응답 수집"""
        print(f"\n=== SSE 요청: {method} (ID: {request_id}) ===")
        
        request_data = {
            "jsonrpc": "2.0",
            "method": method,
            "id": request_id,
        }
        if params:
            request_data["params"] = params
        
        headers = {
            "authorization": f"Bearer {self.access_token}",
            "accept": "application/json, text/event-stream",
            "content-type": "application/json"
        }
        
        if self.session_id:
            headers["mcp-session-id"] = self.session_id
            print(f"📌 기존 세션 ID 사용: {self.session_id}")
        else:
            print("⚠️ 세션 ID 없음")
        
        print(f"📤 요청 헤더: {json.dumps({k: v[:50] + '...' if len(v) > 50 else v for k, v in headers.items()}, indent=2)}")
        print(f"📤 요청 데이터: {json.dumps(request_data, indent=2)}")
        
        responses = []
        
        try:
            async with aconnect_sse(
                self.client,
                "POST",
                f"{self.base_url}/mcp/sse",
                json=request_data,
                headers=headers
            ) as event_source:
                print(f"✅ SSE 연결 성공")
                
                # 응답 헤더에서 세션 ID 추출 (있을 경우)
                if "mcp-session-id" in event_source.response.headers:
                    new_session_id = event_source.response.headers["mcp-session-id"]
                    if new_session_id != self.session_id:
                        self.session_id = new_session_id
                        print(f"🔄 헤더에서 새 세션 ID: {self.session_id}")
                
                # 모든 이벤트 수집
                event_count = 0
                async for sse in event_source.aiter_sse():
                    event_count += 1
                    print(f"\n📨 이벤트 #{event_count}:")
                    print(f"   Type: {sse.event}")
                    print(f"   Data: {sse.data[:200] if sse.data else 'None'}...")  # 처음 200자만 표시
                    
                    # 중첩된 SSE 이벤트 처리
                    if sse.data and sse.data.startswith("event: session"):
                        # 중첩된 SSE 형식 파싱
                        lines = sse.data.strip().split('\n')
                        for i, line in enumerate(lines):
                            if line.startswith("data: "):
                                try:
                                    session_data = json.loads(line[6:])
                                    if "session_id" in session_data:
                                        self.session_id = session_data["session_id"]
                                        print(f"   🔄 SSE 이벤트에서 새 세션 ID: {self.session_id}")
                                except json.JSONDecodeError as e:
                                    print(f"   ⚠️ 세션 데이터 파싱 실패: {e}")
                    
                    if sse.data:
                        # 데이터 파싱
                        data_lines = sse.data.strip().split('\n')
                        for line in data_lines:
                            line = line.strip()
                            if line.startswith("data: "):
                                json_str = line[6:].strip()
                                if json_str and json_str != '':
                                    try:
                                        data = json.loads(json_str)
                                        print(f"   ✅ JSON 파싱 성공: {list(data.keys())}")
                                        responses.append(data)
                                        
                                        # 완료 응답 확인
                                        if data.get("id") == request_id:
                                            print(f"   🎯 요청 ID 일치 - 완료 응답 받음")
                                            return responses
                                    except json.JSONDecodeError as e:
                                        print(f"   ⚠️ JSON 파싱 실패: {e}")
                    
                    # 너무 많은 이벤트 방지
                    if event_count > 10:
                        print("   ⚠️ 이벤트가 너무 많음, 중단")
                        break
        
        except Exception as e:
            print(f"❌ SSE 에러: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
        
        return responses


async def main():
    """단계별 테스트 실행"""
    print("SSE 단계별 테스트 시작...")
    
    async with SSEDebugClient() as client:
        # 1. 인증
        await client.authenticate()
        
        # 2. Initialize
        print("\n" + "="*60)
        print("STEP 1: Initialize")
        print("="*60)
        responses = await client.sse_request(
            "initialize",
            params={
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "step-test-client", "version": "1.0.0"}
            },
            request_id=1
        )
        
        print(f"\n초기화 응답 수: {len(responses)}")
        if responses:
            final = responses[-1]
            if "result" in final:
                print("✅ Initialize 성공!")
                print(f"   프로토콜 버전: {final['result'].get('protocolVersion')}")
                print(f"   서버 정보: {final['result'].get('serverInfo')}")
            elif "error" in final:
                print(f"❌ Initialize 실패: {final['error']}")
                return
        
        # 잠시 대기
        print("\n⏳ 1초 대기...")
        await asyncio.sleep(1)
        
        # 3. List tools
        print("\n" + "="*60)
        print("STEP 2: List Tools")
        print("="*60)
        responses = await client.sse_request(
            "tools/list",
            request_id=2
        )
        
        print(f"\n도구 목록 응답 수: {len(responses)}")
        if responses:
            final = responses[-1]
            if "result" in final:
                tools = final["result"].get("tools", [])
                print(f"✅ 도구 목록 성공! 총 {len(tools)}개 도구")
                for tool in tools[:3]:  # 처음 3개만 표시
                    print(f"   - {tool['name']}: {tool.get('description', '')[:50]}...")
            elif "error" in final:
                print(f"❌ 도구 목록 실패: {final['error']}")
                return
        
        # 4. Call health_check
        print("\n" + "="*60)
        print("STEP 3: Call health_check")
        print("="*60)
        responses = await client.sse_request(
            "tools/call",
            params={
                "name": "health_check",
                "arguments": {}
            },
            request_id=3
        )
        
        print(f"\nhealth_check 응답 수: {len(responses)}")
        if responses:
            final = responses[-1]
            if "result" in final:
                print("✅ health_check 성공!")
                print(f"   결과: {json.dumps(final['result'], indent=2)}")
            elif "error" in final:
                print(f"❌ health_check 실패: {final['error']}")
    
    print("\n✨ 테스트 완료!")


if __name__ == "__main__":
    asyncio.run(main())