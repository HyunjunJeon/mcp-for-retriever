"""Docker 환경에서의 통합 테스트"""

import asyncio
import os
import time
import pytest
import httpx

# 환경 변수에서 서비스 URL 가져오기 (Docker 환경용)
AUTH_URL = os.getenv("AUTH_URL", "http://localhost:8000")
MCP_URL = os.getenv("MCP_URL", "http://localhost:8001")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")


class TestDockerIntegration:
    """Docker 환경에서 실행되는 통합 테스트"""

    @pytest.fixture
    async def auth_client(self):
        """Auth Gateway 클라이언트"""
        async with httpx.AsyncClient(base_url=AUTH_URL) as client:
            yield client

    @pytest.fixture
    async def mcp_client(self):
        """MCP Server 클라이언트"""
        async with httpx.AsyncClient(base_url=MCP_URL) as client:
            yield client

    async def wait_for_service(self, url: str, timeout: int = 30) -> bool:
        """서비스가 준비될 때까지 대기"""
        start_time = time.time()

        async with httpx.AsyncClient() as client:
            while time.time() - start_time < timeout:
                try:
                    response = await client.get(url)
                    if response.status_code in [200, 404]:  # 서비스가 응답하면 OK
                        return True
                except httpx.RequestError:
                    pass

                await asyncio.sleep(1)

        return False

    @pytest.mark.asyncio
    async def test_services_health(self):
        """모든 서비스의 헬스체크"""
        # Auth Gateway 헬스체크
        assert await self.wait_for_service(f"{AUTH_URL}/health"), (
            "Auth Gateway가 시작되지 않았습니다"
        )

        # MCP Server 체크 (FastMCP는 루트에서 404 반환)
        assert await self.wait_for_service(MCP_URL), "MCP Server가 시작되지 않았습니다"

        # 실제 헬스체크 수행
        async with httpx.AsyncClient() as client:
            # Auth Gateway
            response = await client.get(f"{AUTH_URL}/health")
            assert response.status_code == 200
            assert response.json()["status"] == "healthy"

            print("✅ 모든 서비스가 정상적으로 실행 중입니다")

    @pytest.mark.asyncio
    async def test_auth_flow(self, auth_client):
        """인증 플로우 테스트"""
        # 1. 새 사용자 등록
        register_response = await auth_client.post(
            "/auth/register",
            json={"email": "docker.test@example.com", "password": "DockerTest123!"},
        )
        assert register_response.status_code == 200
        user_data = register_response.json()
        assert user_data["email"] == "docker.test@example.com"
        print("✅ 사용자 등록 성공")

        # 2. 로그인
        login_response = await auth_client.post(
            "/auth/login",
            json={"email": "docker.test@example.com", "password": "DockerTest123!"},
        )
        assert login_response.status_code == 200
        token_data = login_response.json()
        assert "access_token" in token_data
        print("✅ 로그인 성공")

        # 3. 토큰으로 사용자 정보 조회
        headers = {"Authorization": f"Bearer {token_data['access_token']}"}
        me_response = await auth_client.get("/auth/me", headers=headers)
        assert me_response.status_code == 200
        assert me_response.json()["email"] == "docker.test@example.com"
        print("✅ 토큰 검증 성공")

        return token_data["access_token"]

    @pytest.mark.asyncio
    async def test_mcp_tools_discovery(self, mcp_client):
        """MCP 도구 검색 테스트"""
        # MCP 프로토콜로 도구 목록 조회
        response = await mcp_client.post(
            "/", json={"jsonrpc": "2.0", "method": "tools/list", "id": 1}
        )

        assert response.status_code == 200
        result = response.json()

        # 응답 검증
        assert "result" in result
        tools = result["result"]["tools"]

        # 모든 도구가 있는지 확인
        tool_names = [tool["name"] for tool in tools]
        expected_tools = [
            "search_web",
            "search_vectors",
            "search_database",
            "search_all",
            "health_check",
        ]

        for expected in expected_tools:
            assert expected in tool_names, f"도구 '{expected}'가 없습니다"

        print(f"✅ MCP 도구 {len(tools)}개 발견: {', '.join(tool_names)}")

    @pytest.mark.asyncio
    async def test_mcp_health_check(self, mcp_client):
        """MCP 헬스체크 도구 실행"""
        response = await mcp_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "health_check", "arguments": {}},
                "id": 2,
            },
        )

        assert response.status_code == 200
        result = response.json()

        # 응답 검증
        assert "result" in result
        health_data = result["result"]["content"][0]

        # 헬스 상태 확인
        assert health_data["type"] == "text"
        health_status = eval(health_data["text"])  # JSON 문자열을 파싱

        assert health_status["service"] == "mcp-retriever"
        assert "retrievers" in health_status

        print(f"✅ MCP 헬스체크 성공: {health_status['status']}")
        print(f"   활성 retrievers: {list(health_status['retrievers'].keys())}")

    @pytest.mark.asyncio
    async def test_user_search_api(self, auth_client):
        """사용자 검색 API 테스트"""
        # 기본 사용자로 로그인
        login_response = await auth_client.post(
            "/auth/login", json={"email": "admin@example.com", "password": "Admin123!"}
        )
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 사용자 검색
        search_response = await auth_client.get(
            "/api/v1/users/search?q=admin", headers=headers
        )
        assert search_response.status_code == 200
        users = search_response.json()
        assert len(users) > 0
        assert any(user["email"] == "admin@example.com" for user in users)
        print("✅ 사용자 검색 API 테스트 성공")

        # 최근 사용자 조회
        recent_response = await auth_client.get(
            "/api/v1/users/search?limit=5", headers=headers
        )
        assert recent_response.status_code == 200
        recent_users = recent_response.json()
        assert len(recent_users) <= 5
        print("✅ 최근 사용자 조회 성공")

    @pytest.mark.asyncio
    async def test_admin_endpoints(self, auth_client):
        """관리자 엔드포인트 테스트"""
        # 관리자로 로그인
        login_response = await auth_client.post(
            "/auth/login", json={"email": "admin@example.com", "password": "Admin123!"}
        )
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 사용자 목록 조회
        users_response = await auth_client.get(
            "/api/v1/admin/users?limit=10", headers=headers
        )
        assert users_response.status_code == 200
        users = users_response.json()
        assert isinstance(users, list)
        print(f"✅ 관리자 사용자 목록 조회 성공: {len(users)}명")

        # 사용자 통계 조회
        stats_response = await auth_client.get(
            "/api/v1/admin/users/stats", headers=headers
        )
        assert stats_response.status_code == 200
        stats = stats_response.json()
        assert "total_users" in stats
        assert "active_users" in stats
        assert "roles" in stats
        print(f"✅ 사용자 통계 조회 성공: 총 {stats['total_users']}명")

    @pytest.mark.asyncio
    async def test_mcp_web_search_mock(self, mcp_client):
        """MCP 웹 검색 도구 테스트 (Mock 데이터)"""
        response = await mcp_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "search_web",
                    "arguments": {"query": "Docker integration test"},
                },
                "id": 3,
            },
        )

        # Tavily API 키가 없으면 실패할 수 있음
        if response.status_code == 200:
            result = response.json()
            if "error" not in result:
                print("✅ MCP 웹 검색 도구 실행 성공")
            else:
                print(f"⚠️  MCP 웹 검색 실패 (예상됨): {result['error']['message']}")
        else:
            print(f"⚠️  MCP 웹 검색 실패: HTTP {response.status_code}")

    @pytest.mark.asyncio
    async def test_end_to_end_flow(self, auth_client, mcp_client):
        """전체 통합 플로우 테스트"""
        print("\n🔄 전체 통합 플로우 테스트 시작...")

        # 1. 사용자 등록 및 로그인
        token = await self.test_auth_flow(auth_client)

        # 2. MCP 도구 검색
        await self.test_mcp_tools_discovery(mcp_client)

        # 3. 헬스체크
        await self.test_mcp_health_check(mcp_client)

        # 4. 사용자 검색
        headers = {"Authorization": f"Bearer {token}"}
        search_response = await auth_client.get(
            "/api/v1/users/search?q=docker", headers=headers
        )
        assert search_response.status_code == 200

        print("✅ 전체 통합 플로우 테스트 완료!")


if __name__ == "__main__":
    # 직접 실행 시
    async def main():
        test = TestDockerIntegration()

        print("🐳 Docker 통합 테스트 시작...\n")

        # 서비스 헬스체크
        await test.test_services_health()

        # Auth 클라이언트 생성
        async with httpx.AsyncClient(base_url=AUTH_URL) as auth_client:
            test.auth_client = auth_client

            # MCP 클라이언트 생성
            async with httpx.AsyncClient(base_url=MCP_URL) as mcp_client:
                test.mcp_client = mcp_client

                # 테스트 실행
                await test.test_auth_flow(auth_client)
                await test.test_mcp_tools_discovery(mcp_client)
                await test.test_mcp_health_check(mcp_client)
                await test.test_user_search_api(auth_client)
                await test.test_admin_endpoints(auth_client)
                await test.test_mcp_web_search_mock(mcp_client)
                await test.test_end_to_end_flow(auth_client, mcp_client)

        print("\n✅ 모든 Docker 통합 테스트 완료!")

    asyncio.run(main())
