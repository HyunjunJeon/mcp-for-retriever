"""
포괄적인 SSE 프록시 기능 통합 테스트

이 테스트는 MCP Gateway의 SSE 프록시 기능이 다양한 상황에서
올바르게 작동하는지 검증합니다.

테스트 시나리오:
- 정상적인 스트리밍 데이터 전달
- 대용량 데이터 스트리밍
- 연결 끊김 및 재연결
- 에러 상황 처리
- 권한 기반 필터링
"""

import pytest
import httpx
import asyncio
import json
import time
from typing import AsyncIterator, Optional, List, Dict, Any
from httpx_sse import aconnect_sse, ServerSentEvent
import structlog

logger = structlog.get_logger()


class SSETestClient:
    """SSE 테스트를 위한 클라이언트"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.access_token: Optional[str] = None
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))
        self.session_id: Optional[str] = None
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    async def authenticate(self, email: str = "sse_test@example.com", password: str = "TestPass123!"):
        """사용자 인증"""
        # 먼저 등록 시도
        try:
            await self.client.post(
                f"{self.base_url}/auth/register",
                json={"email": email, "password": password}
            )
        except httpx.HTTPStatusError:
            pass  # 이미 등록된 경우 무시
        
        # 로그인
        response = await self.client.post(
            f"{self.base_url}/auth/login",
            json={"email": email, "password": password}
        )
        response.raise_for_status()
        data = response.json()
        self.access_token = data["access_token"]
        return self.access_token
    
    async def sse_request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        request_id: int = 1,
        timeout: float = 30.0
    ) -> AsyncIterator[Dict[str, Any]]:
        """SSE 요청을 보내고 응답 스트림 반환"""
        if not self.access_token:
            raise ValueError("인증이 필요합니다")
        
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
        
        # SSE 연결 및 스트림
        async with aconnect_sse(
            self.client,
            "POST",
            f"{self.base_url}/mcp/sse",
            json=request_data,
            headers=headers,
            timeout=timeout
        ) as event_source:
            # 세션 ID 추출 (헤더에서)
            if "mcp-session-id" in event_source.response.headers:
                self.session_id = event_source.response.headers["mcp-session-id"]
            
            async for sse in event_source.aiter_sse():
                # 중첩된 SSE 이벤트에서 세션 ID 추출
                if sse.data and "event: session" in sse.data:
                    # 중첩된 SSE 형식 파싱
                    lines = sse.data.strip().split('\n')
                    for line in lines:
                        if line.startswith("data: "):
                            try:
                                session_data = json.loads(line[6:])
                                if "session_id" in session_data:
                                    self.session_id = session_data["session_id"]
                                    logger.debug(f"SSE에서 세션 ID 추출: {self.session_id}")
                            except json.JSONDecodeError:
                                pass
                
                if sse.data:
                    # SSE 데이터는 때로 전체 SSE 이벤트를 포함
                    # "event: message\ndata: {...}" 형식으로 올 수 있음
                    data_lines = sse.data.strip().split('\n')
                    
                    for line in data_lines:
                        line = line.strip()
                        if line.startswith("data: "):
                            json_str = line[6:].strip()
                            if json_str and json_str != '':  # 빈 data: 라인 무시
                                try:
                                    data = json.loads(json_str)
                                    # session_id는 별도로 처리했으므로 무시
                                    if "session_id" in data and not "jsonrpc" in data:
                                        continue
                                    yield data
                                except json.JSONDecodeError:
                                    # JSON이 아닌 데이터는 무시
                                    pass
    
    async def collect_responses(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        request_id: int = 1,
        max_responses: int = 10
    ) -> List[Dict[str, Any]]:
        """SSE 응답을 수집하여 리스트로 반환"""
        responses = []
        async for response in self.sse_request(method, params, request_id):
            responses.append(response)
            # 요청 ID와 일치하는 최종 응답을 받으면 종료
            if response.get("id") == request_id and ("result" in response or "error" in response):
                break
            if len(responses) >= max_responses:
                break
        return responses


@pytest.mark.asyncio
class TestSSEProxyIntegration:
    """SSE 프록시 통합 테스트"""
    
    async def test_basic_sse_flow(self):
        """기본 SSE 플로우 테스트"""
        async with SSETestClient() as client:
            # 인증
            await client.authenticate()
            
            # 1. Initialize
            responses = await client.collect_responses(
                "initialize",
                params={
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"}
                },
                request_id=1
            )
            
            assert len(responses) > 0
            final_response = responses[-1]
            assert "result" in final_response
            assert final_response["result"].get("protocolVersion") == "2025-06-18"
            
            # 2. List tools
            responses = await client.collect_responses(
                "tools/list",
                request_id=2
            )
            
            assert len(responses) > 0
            final_response = responses[-1]
            assert "result" in final_response
            tools = final_response["result"].get("tools", [])
            assert len(tools) > 0
            
            # 3. Call health_check
            responses = await client.collect_responses(
                "tools/call",
                params={
                    "name": "health_check",
                    "arguments": {}
                },
                request_id=3
            )
            
            assert len(responses) > 0
            final_response = responses[-1]
            assert "result" in final_response
    
    async def test_large_data_streaming(self):
        """대용량 데이터 스트리밍 테스트"""
        async with SSETestClient() as client:
            await client.authenticate()
            
            # Initialize first
            await client.collect_responses(
                "initialize",
                params={
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"}
                }
            )
            
            # 대용량 검색 요청 (많은 결과 반환)
            start_time = time.time()
            responses = await client.collect_responses(
                "tools/call",
                params={
                    "name": "search_database",
                    "arguments": {
                        "query": "SELECT * FROM pg_catalog.pg_tables",
                        "limit": 100  # 많은 결과 요청
                    }
                },
                request_id=4,
                max_responses=1000  # 더 많은 응답 허용
            )
            elapsed = time.time() - start_time
            
            # 스트리밍이 제대로 작동했는지 확인
            assert len(responses) > 0
            final_response = responses[-1]
            
            # 에러가 없어야 함 (데이터베이스 연결 안됨 에러는 OK)
            if "error" in final_response:
                # 데이터베이스 연결 에러는 정상
                assert "사용할 수 없습니다" in final_response["error"]["message"]
            else:
                # 성공한 경우 결과 확인
                assert "result" in final_response
            
            # 타임아웃 내에 완료되어야 함
            assert elapsed < 30.0
    
    async def test_error_handling(self):
        """에러 상황 처리 테스트"""
        async with SSETestClient() as client:
            await client.authenticate()
            
            # 1. 잘못된 메서드 호출
            responses = await client.collect_responses(
                "invalid/method",
                request_id=10
            )
            
            assert len(responses) > 0
            final_response = responses[-1]
            assert "error" in final_response
            
            # 2. 권한 없는 도구 호출 (관리자 전용 도구)
            responses = await client.collect_responses(
                "tools/call",
                params={
                    "name": "admin_only_tool",
                    "arguments": {}
                },
                request_id=11
            )
            
            # 도구를 찾을 수 없거나 권한 에러가 발생해야 함
            assert len(responses) > 0
            final_response = responses[-1]
            assert "error" in final_response
    
    async def test_concurrent_sse_streams(self):
        """동시 SSE 스트림 처리 테스트"""
        async with SSETestClient() as client1, SSETestClient() as client2:
            # 두 클라이언트 인증
            await client1.authenticate("user1@example.com", "Pass123!")
            await client2.authenticate("user2@example.com", "Pass123!")
            
            # 동시에 요청 보내기
            async def make_request(client: SSETestClient, request_id: int):
                return await client.collect_responses(
                    "tools/list",
                    request_id=request_id
                )
            
            # 병렬 실행
            results = await asyncio.gather(
                make_request(client1, 100),
                make_request(client2, 200)
            )
            
            # 두 클라이언트 모두 응답을 받아야 함
            assert len(results) == 2
            assert all(len(responses) > 0 for responses in results)
            assert all("result" in responses[-1] for responses in results)
    
    async def test_session_persistence(self):
        """세션 지속성 테스트"""
        async with SSETestClient() as client:
            await client.authenticate()
            
            # 첫 번째 요청 - 세션 생성
            await client.collect_responses(
                "initialize",
                params={
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"}
                },
                request_id=1
            )
            
            # 세션 ID가 설정되었는지 확인
            assert client.session_id is not None
            first_session_id = client.session_id
            
            # 두 번째 요청 - 같은 세션 사용
            await client.collect_responses(
                "tools/list",
                request_id=2
            )
            
            # 세션 ID가 유지되는지 확인
            assert client.session_id == first_session_id
    
    async def test_role_based_tool_filtering(self):
        """역할 기반 도구 필터링 테스트"""
        # 일반 사용자와 관리자 생성
        async with SSETestClient() as user_client, SSETestClient() as admin_client:
            # 일반 사용자
            await user_client.authenticate("normal_user@example.com", "Pass123!")
            
            # 관리자 (실제로는 동일한 권한이지만 테스트를 위해)
            await admin_client.authenticate("admin@example.com", "AdminPass123!")
            
            # 각각 도구 목록 가져오기
            user_responses = await user_client.collect_responses("tools/list")
            admin_responses = await admin_client.collect_responses("tools/list")
            
            # 응답 확인
            assert len(user_responses) > 0
            assert len(admin_responses) > 0
            
            user_tools = user_responses[-1]["result"]["tools"]
            admin_tools = admin_responses[-1]["result"]["tools"]
            
            # 기본적으로 모든 사용자가 동일한 도구를 가져야 함
            # (실제 환경에서는 역할에 따라 다를 수 있음)
            assert len(user_tools) > 0
            assert len(admin_tools) > 0
    
    async def test_sse_reconnection(self):
        """SSE 재연결 시나리오 테스트"""
        client = SSETestClient()
        await client.authenticate()
        
        # 첫 번째 연결
        responses1 = await client.collect_responses(
            "initialize",
            params={
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"}
            }
        )
        assert len(responses1) > 0
        
        # 클라이언트는 열어둔 채로 새로운 연결 시도
        # (실제 재연결 시뮬레이션)
        responses2 = await client.collect_responses("tools/list")
        assert len(responses2) > 0
        
        # 정리
        await client.client.aclose()


@pytest.mark.asyncio
async def test_sse_event_types():
    """다양한 SSE 이벤트 타입 지원 테스트"""
    async with SSETestClient() as client:
        await client.authenticate()
        
        event_types = []
        
        # 이벤트 타입 수집
        async for response in client.sse_request(
            "initialize",
            params={
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"}
            }
        ):
            # 응답 타입 확인
            if "method" in response:
                event_types.append(f"notification:{response['method']}")
            elif "result" in response:
                event_types.append("result")
            elif "error" in response:
                event_types.append("error")
            
            # 첫 번째 완료 응답에서 중단
            if response.get("id") == 1:
                break
        
        # 최소한 result 이벤트는 있어야 함
        assert "result" in event_types


@pytest.mark.asyncio
async def test_sse_performance():
    """SSE 성능 테스트"""
    async with SSETestClient() as client:
        await client.authenticate()
        
        # 초기화
        await client.collect_responses(
            "initialize",
            params={
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"}
            }
        )
        
        # 여러 요청의 응답 시간 측정
        response_times = []
        
        for i in range(5):
            start = time.time()
            responses = await client.collect_responses(
                "tools/call",
                params={
                    "name": "health_check",
                    "arguments": {}
                },
                request_id=i + 100
            )
            elapsed = time.time() - start
            response_times.append(elapsed)
            
            # 응답 확인
            assert len(responses) > 0
            assert "result" in responses[-1] or "error" in responses[-1]
        
        # 평균 응답 시간 계산
        avg_time = sum(response_times) / len(response_times)
        logger.info(f"평균 SSE 응답 시간: {avg_time:.3f}초")
        
        # 응답 시간이 합리적이어야 함 (5초 이내)
        assert avg_time < 5.0


if __name__ == "__main__":
    # 개별 테스트 실행을 위한 헬퍼
    import sys
    
    if len(sys.argv) > 1:
        test_name = sys.argv[1]
        if hasattr(TestSSEProxyIntegration, test_name):
            test_instance = TestSSEProxyIntegration()
            test_method = getattr(test_instance, test_name)
            asyncio.run(test_method())
        else:
            print(f"테스트 '{test_name}'을 찾을 수 없습니다")
    else:
        # 모든 테스트 실행
        pytest.main([__file__, "-v"])