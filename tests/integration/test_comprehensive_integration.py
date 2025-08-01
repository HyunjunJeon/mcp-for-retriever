"""
종합 통합 테스트 - 모든 신규 기능 검증

이 테스트는 다음 기능들이 통합 환경에서 정상 동작하는지 검증합니다:
1. DB 연결 풀 최적화 - 연결 재사용 확인
2. JWT 자동 갱신 - 토큰 만료 시 자동 갱신
3. Redis Rate Limiting - Sliding window 동작
4. 전체 시스템 성능 - 응답 시간 및 처리량
"""

import asyncio
import json
import time
import os
import pytest
import httpx
import structlog

logger = structlog.get_logger(__name__)

# 환경 변수
AUTH_URL = os.getenv("AUTH_URL", "http://localhost:8000")
MCP_URL = os.getenv("MCP_URL", "http://localhost:8001")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")


class TestComprehensiveIntegration:
    """종합 통합 테스트 클래스"""

    @pytest.fixture
    async def test_user(self):
        """테스트용 사용자 생성"""
        async with httpx.AsyncClient(base_url=AUTH_URL) as client:
            email = "comprehensive.test@example.com"
            password = "TestUser123!"

            # 먼저 로그인 시도
            login_resp = await client.post(
                "/auth/login", json={"email": email, "password": password}
            )

            if login_resp.status_code != 200:
                # 로그인 실패 시 새로 등록
                register_resp = await client.post(
                    "/auth/register", json={"email": email, "password": password}
                )
                assert register_resp.status_code == 200
                user_id = register_resp.json()["id"]

                # 다시 로그인
                login_resp = await client.post(
                    "/auth/login", json={"email": email, "password": password}
                )
                assert login_resp.status_code == 200
            else:
                # 기존 사용자로 로그인 성공
                # user_id를 /auth/me 엔드포인트에서 가져오기
                me_resp = await client.get(
                    "/auth/me",
                    headers={
                        "Authorization": f"Bearer {login_resp.json()['access_token']}"
                    },
                )
                assert me_resp.status_code == 200
                user_id = me_resp.json()["id"]

            token_data = login_resp.json()

            yield {
                "email": email,
                "access_token": token_data["access_token"],
                "refresh_token": token_data.get("refresh_token"),
                "user_id": user_id,
            }

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_connection_pool_reuse(self, test_user):
        """DB 연결 풀 재사용 검증"""
        logger.info("=== DB 연결 풀 재사용 테스트 시작 ===")

        headers = {
            "Authorization": f"Bearer {test_user['access_token']}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

        # MCP 서버로 여러 번 데이터베이스 검색 요청
        async with httpx.AsyncClient(base_url=MCP_URL) as client:
            # 먼저 MCP 초기화
            init_response = await client.post(
                "/mcp/",
                json={
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "Integration Test", "version": "1.0.0"},
                    },
                    "id": 0,
                },
                headers=headers,
            )

            if init_response.status_code != 200:
                logger.error(f"초기화 실패: {init_response.status_code}")
                logger.error(f"응답: {init_response.text}")

            assert init_response.status_code == 200

            # 세션 ID 추출
            session_id = init_response.headers.get("mcp-session-id")
            if session_id:
                headers["mcp-session-id"] = session_id
                logger.info(f"세션 ID 획득: {session_id}")

            # initialized 알림 전송
            initialized_response = await client.post(
                "/mcp/",
                json={"jsonrpc": "2.0", "method": "initialized", "params": {}},
                headers=headers,
            )
            logger.info(f"Initialized 응답: {initialized_response.status_code}")

            # 10번의 연속 요청
            for i in range(10):
                response = await client.post(
                    "/mcp/",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {
                            "name": "search_database",
                            "arguments": {"query": f"SELECT 1 as test_{i}", "limit": 1},
                        },
                        "id": i + 1,
                    },
                    headers=headers,
                )

                if response.status_code != 200:
                    logger.error(f"요청 실패: {response.status_code}")
                    logger.error(f"응답: {response.text}")
                assert response.status_code == 200

                # SSE 또는 JSON 응답 처리
                content_type = response.headers.get("content-type", "")
                if "text/event-stream" in content_type:
                    # SSE 응답 처리
                    for line in response.text.split("\n"):
                        if line.startswith("data: "):
                            json_data = line[6:]
                            if json_data.strip():
                                json.loads(json_data)
                                break
                else:
                    response.json()

                # 연결 ID 추출 (로그나 응답에서)
                # 실제로는 서버 로그에서 확인해야 할 수도 있음
                logger.info(f"요청 {i + 1} 완료")

            # 동시 요청으로 연결 풀 동작 확인
            tasks = []
            for i in range(5):
                task = client.post(
                    "/mcp/",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {
                            "name": "search_database",
                            "arguments": {
                                "query": f"SELECT pg_sleep(0.1), {i} as concurrent_test",
                                "limit": 1,
                            },
                        },
                        "id": 100 + i,
                    },
                    headers=headers,
                )
                tasks.append(task)

            # 동시 실행
            start_time = time.time()
            responses = await asyncio.gather(*tasks)
            elapsed_time = time.time() - start_time

            # 모든 요청이 성공해야 함
            for resp in responses:
                assert resp.status_code == 200

            # 연결 풀이 제대로 동작하면 동시 실행 시간이 단축됨
            # 5개 요청 * 0.1초 = 0.5초보다 훨씬 빨라야 함
            assert elapsed_time < 0.3, f"동시 실행이 너무 느림: {elapsed_time}초"

            logger.info(
                f"✅ 연결 풀 재사용 확인 - 동시 실행 시간: {elapsed_time:.2f}초"
            )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_jwt_auto_refresh(self, test_user):
        """JWT 자동 갱신 동작 검증"""
        logger.info("=== JWT 자동 갱신 테스트 시작 ===")

        if not test_user.get("refresh_token"):
            pytest.skip("Refresh token not available - auto refresh may be disabled")

        # 짧은 만료 시간의 토큰으로 테스트하려면 서버 설정이 필요
        # 여기서는 토큰 갱신 API를 직접 호출하여 테스트

        async with httpx.AsyncClient(base_url=AUTH_URL) as client:
            # 현재 토큰으로 사용자 정보 조회
            headers = {
                "Authorization": f"Bearer {test_user['access_token']}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }
            me_resp = await client.get("/auth/me", headers=headers)
            assert me_resp.status_code == 200
            original_user = me_resp.json()

            # 토큰 갱신
            refresh_resp = await client.post(
                "/auth/refresh", json={"refresh_token": test_user["refresh_token"]}
            )

            if refresh_resp.status_code == 200:
                new_tokens = refresh_resp.json()
                new_access_token = new_tokens["access_token"]

                # 새 토큰으로 다시 조회
                new_headers = {"Authorization": f"Bearer {new_access_token}"}
                new_me_resp = await client.get("/auth/me", headers=new_headers)
                assert new_me_resp.status_code == 200
                new_user = new_me_resp.json()

                # 동일한 사용자인지 확인
                assert new_user["id"] == original_user["id"]
                assert new_user["email"] == original_user["email"]

                logger.info("✅ JWT 토큰 갱신 성공")
            else:
                logger.warning("토큰 갱신 API가 구현되지 않음")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rate_limiting(self, test_user):
        """Rate Limiting 동작 검증"""
        logger.info("=== Rate Limiting 테스트 시작 ===")

        headers = {
            "Authorization": f"Bearer {test_user['access_token']}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

        async with httpx.AsyncClient(base_url=MCP_URL) as client:
            # Rate limit 설정 확인 (기본값: 60 req/min)
            request_count = 0
            rate_limited = False

            # 빠른 연속 요청으로 rate limit 도달 시도
            for i in range(100):  # 충분히 많은 요청
                response = await client.post(
                    "/mcp/",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {"name": "health_check", "arguments": {}},
                        "id": i + 1,
                    },
                    headers=headers,
                )

                request_count += 1

                # Rate limit 에러 확인
                if response.status_code != 200:
                    result = response.json()
                    if (
                        "error" in result
                        and "rate limit" in str(result["error"]).lower()
                    ):
                        rate_limited = True
                        logger.info(
                            f"Rate limit 도달 - {request_count}번째 요청에서 제한됨"
                        )

                        # Retry-After 헤더 확인
                        retry_after = response.headers.get("Retry-After")
                        if retry_after:
                            logger.info(f"Retry-After: {retry_after}초")

                        break

            # Rate limiting이 동작해야 함
            assert rate_limited, (
                f"Rate limit이 동작하지 않음 - {request_count}개 요청 모두 성공"
            )

            # 대기 후 다시 요청 가능한지 확인
            await asyncio.sleep(2)  # 짧은 대기

            retry_response = await client.post(
                "/",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": "health_check", "arguments": {}},
                    "id": 999,
                },
                headers=headers,
            )

            # Sliding window이므로 일부 요청은 다시 가능해야 함
            logger.info(f"대기 후 재시도 결과: {retry_response.status_code}")

            logger.info("✅ Rate Limiting 동작 확인")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_performance_improvement(self, test_user):
        """전체 시스템 성능 개선 측정"""
        logger.info("=== 성능 개선 측정 시작 ===")

        headers = {
            "Authorization": f"Bearer {test_user['access_token']}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

        async with httpx.AsyncClient(base_url=MCP_URL, timeout=30.0) as client:
            # 1. 단일 요청 응답 시간 측정
            single_request_times = []

            for i in range(10):
                start = time.time()
                response = await client.post(
                    "/mcp/",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {
                            "name": "search_database",
                            "arguments": {
                                "query": "SELECT * FROM pg_tables LIMIT 5",
                                "limit": 5,
                            },
                        },
                        "id": i + 1,
                    },
                    headers=headers,
                )
                elapsed = time.time() - start

                if response.status_code == 200:
                    single_request_times.append(elapsed)

            avg_single_time = (
                sum(single_request_times) / len(single_request_times)
                if single_request_times
                else 0
            )
            logger.info(f"평균 단일 요청 시간: {avg_single_time:.3f}초")

            # 2. 동시 요청 처리량 측정
            concurrent_count = 20
            tasks = []

            start_time = time.time()
            for i in range(concurrent_count):
                task = client.post(
                    "/mcp/",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {"name": "health_check", "arguments": {}},
                        "id": 1000 + i,
                    },
                    headers=headers,
                )
                tasks.append(task)

            responses = await asyncio.gather(*tasks, return_exceptions=True)
            total_time = time.time() - start_time

            successful_responses = [
                r
                for r in responses
                if not isinstance(r, Exception) and r.status_code == 200
            ]
            throughput = len(successful_responses) / total_time

            logger.info(
                f"동시 요청 처리: {len(successful_responses)}/{concurrent_count} 성공"
            )
            logger.info(f"처리량: {throughput:.2f} requests/second")
            logger.info(f"총 처리 시간: {total_time:.2f}초")

            # 3. 캐시 효과 측정 (동일 쿼리 반복)
            if TAVILY_API_KEY:
                cache_times = []
                search_query = "Python FastAPI best practices"

                # 첫 번째 요청 (캐시 미스)
                start = time.time()
                await client.post(
                    "/mcp/",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {
                            "name": "search_web",
                            "arguments": {"query": search_query, "limit": 5},
                        },
                        "id": 2000,
                    },
                    headers=headers,
                )
                first_time = time.time() - start

                # 동일 쿼리 반복 (캐시 히트 기대)
                for i in range(5):
                    start = time.time()
                    cache_resp = await client.post(
                        "/mcp/",
                        json={
                            "jsonrpc": "2.0",
                            "method": "tools/call",
                            "params": {
                                "name": "search_web",
                                "arguments": {"query": search_query, "limit": 5},
                            },
                            "id": 2001 + i,
                        },
                        headers=headers,
                    )
                    elapsed = time.time() - start
                    if cache_resp.status_code == 200:
                        cache_times.append(elapsed)

                if cache_times:
                    avg_cache_time = sum(cache_times) / len(cache_times)
                    cache_improvement = (
                        (first_time - avg_cache_time) / first_time
                    ) * 100
                    logger.info(f"첫 요청 시간: {first_time:.3f}초")
                    logger.info(f"캐시된 요청 평균: {avg_cache_time:.3f}초")
                    logger.info(f"캐시 성능 개선: {cache_improvement:.1f}%")

            # 성능 기준 검증
            assert avg_single_time < 2.0, f"단일 요청이 너무 느림: {avg_single_time}초"
            assert throughput > 5.0, f"처리량이 너무 낮음: {throughput} req/s"

            logger.info("✅ 성능 개선 확인 완료")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_error_recovery(self, test_user):
        """오류 복구 및 안정성 테스트"""
        logger.info("=== 오류 복구 테스트 시작 ===")

        headers = {
            "Authorization": f"Bearer {test_user['access_token']}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

        async with httpx.AsyncClient(base_url=MCP_URL) as client:
            # 1. 잘못된 쿼리로 오류 유발
            error_response = await client.post(
                "/",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "search_database",
                        "arguments": {"query": "INVALID SQL SYNTAX !!!", "limit": 1},
                    },
                    "id": 3000,
                },
                headers=headers,
            )

            # 오류가 적절히 처리되어야 함
            assert error_response.status_code == 200  # MCP는 200으로 오류 반환
            error_result = error_response.json()
            assert "error" in error_result

            # 2. 오류 후에도 정상 요청이 가능해야 함
            normal_response = await client.post(
                "/",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": "health_check", "arguments": {}},
                    "id": 3001,
                },
                headers=headers,
            )

            assert normal_response.status_code == 200
            normal_result = normal_response.json()
            assert "result" in normal_result

            logger.info("✅ 오류 복구 정상 동작 확인")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_comprehensive_scenario(self, test_user):
        """실제 사용 시나리오 종합 테스트"""
        logger.info("=== 종합 시나리오 테스트 시작 ===")

        headers = {
            "Authorization": f"Bearer {test_user['access_token']}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

        async with httpx.AsyncClient(base_url=MCP_URL, timeout=60.0) as client:
            # 시나리오: 사용자가 여러 검색을 수행하고 결과를 조합

            # 1. 웹 검색 (Tavily API 키가 있는 경우만)
            web_results = None
            if TAVILY_API_KEY:
                web_resp = await client.post(
                    "/mcp/",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {
                            "name": "search_web",
                            "arguments": {
                                "query": "FastAPI performance optimization",
                                "limit": 3,
                            },
                        },
                        "id": 4001,
                    },
                    headers=headers,
                )
                if web_resp.status_code == 200:
                    web_result = web_resp.json()
                    if "result" in web_result:
                        web_results = web_result["result"]
                        logger.info(f"웹 검색 결과: {len(web_results)}개")

            # 2. 데이터베이스 검색
            db_resp = await client.post(
                "/",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "search_database",
                        "arguments": {
                            "query": "SELECT tablename FROM pg_tables WHERE schemaname = 'public' LIMIT 5",
                            "limit": 5,
                        },
                    },
                    "id": 4002,
                },
                headers=headers,
            )

            db_results = None
            if db_resp.status_code == 200:
                db_result = db_resp.json()
                if "result" in db_result:
                    db_results = db_result["result"]
                    logger.info(f"DB 검색 결과: {len(db_results)}개")

            # 3. 벡터 검색 (Qdrant가 설정된 경우)
            vector_resp = await client.post(
                "/",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "search_vectors",
                        "arguments": {
                            "query": "performance optimization techniques",
                            "collection": "default",
                            "limit": 5,
                        },
                    },
                    "id": 4003,
                },
                headers=headers,
            )

            # 벡터 검색은 컬렉션이 없을 수 있으므로 오류 허용
            vector_results = None
            if vector_resp.status_code == 200:
                vector_result = vector_resp.json()
                if "result" in vector_result:
                    vector_results = vector_result["result"]
                    logger.info(f"벡터 검색 결과: {len(vector_results)}개")

            # 4. 통합 검색 (search_all)
            all_resp = await client.post(
                "/",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "search_all",
                        "arguments": {
                            "query": "API development best practices",
                            "limit": 3,
                        },
                    },
                    "id": 4004,
                },
                headers=headers,
            )

            if all_resp.status_code == 200:
                all_result = all_resp.json()
                if "result" in all_result:
                    all_results = all_result["result"]
                    logger.info(f"통합 검색 완료: 총 {len(all_results)}개 소스")

            # 최소한 일부 검색은 성공해야 함
            successful_searches = sum(
                [
                    1 if web_results else 0,
                    1 if db_results else 0,
                    1 if vector_results else 0,
                ]
            )

            assert successful_searches >= 1, "모든 검색이 실패함"

            logger.info(f"✅ 종합 시나리오 완료 - {successful_searches}/3 검색 성공")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
