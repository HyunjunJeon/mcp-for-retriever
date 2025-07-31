"""
Fine-grained permission E2E tests

세밀한 리소스 권한 시스템을 테스트합니다.
Collection/Table 레벨의 접근 제어를 검증합니다.
"""

import json
import pytest
from playwright.async_api import Page, expect
import httpx
from typing import Any, Optional

from src.auth.models import ResourceType, ActionType

# E2E fixture 임포트
from .fixtures import auth_client, mcp_client


@pytest.mark.asyncio
class TestFineGrainedPermissions:
    """세밀한 권한 시스템 E2E 테스트"""
    
    async def setup_test_users(self, auth_client: httpx.AsyncClient) -> dict[str, dict[str, Any]]:
        """테스트용 사용자 생성 및 로그인"""
        import uuid
        users = {}
        unique_id = uuid.uuid4().hex[:8]
        
        # 1. 기본 user (public 스키마 읽기, users collection 읽기)
        basic_email = f"basic-{unique_id}@example.com"
        user_resp = await auth_client.post(
            "/auth/register",
            json={
                "email": basic_email,
                "password": "Basic123!",
                "username": "basic_user"
            }
        )
        if user_resp.status_code != 200:
            print(f"Registration failed: {user_resp.status_code}")
            print(f"Response: {user_resp.text}")
        assert user_resp.status_code == 200
        
        login_resp = await auth_client.post(
            "/auth/login",
            json={"email": basic_email, "password": "Basic123!"}
        )
        users["basic"] = login_resp.json()
        
        # 2. Power user (모든 collection 읽기, analytics 스키마 읽기/쓰기)
        power_email = f"power-{unique_id}@example.com"
        power_resp = await auth_client.post(
            "/auth/register",
            json={
                "email": power_email,
                "password": "Power123!",
                "username": "power_user"
                # roles는 등록 후 별도로 설정해야 함
            }
        )
        assert power_resp.status_code == 200
        
        login_resp = await auth_client.post(
            "/auth/login",
            json={"email": power_email, "password": "Power123!"}
        )
        users["power"] = login_resp.json()
        
        # 3. Admin user (모든 권한)
        admin_email = f"admin-{unique_id}@example.com"
        admin_resp = await auth_client.post(
            "/auth/register",
            json={
                "email": admin_email,
                "password": "Admin123!",
                "username": "admin_user"
                # roles는 등록 후 별도로 설정해야 함
            }
        )
        assert admin_resp.status_code == 200
        
        login_resp = await auth_client.post(
            "/auth/login",
            json={"email": admin_email, "password": "Admin123!"}
        )
        users["admin"] = login_resp.json()
        
        return users
    
    async def test_vector_db_collection_permissions(
        self,
        auth_client: httpx.AsyncClient,
        mcp_client: httpx.AsyncClient
    ):
        """Vector DB collection 레벨 권한 테스트"""
        users = await self.setup_test_users(auth_client)
        
        # 1. Basic user: users.* collection만 접근 가능
        headers = {"Authorization": f"Bearer {users['basic']['access_token']}"}
        
        # users.documents collection 검색 - 성공해야 함
        search_resp = await auth_client.post(
            "/mcp/proxy",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "search_vectors",
                    "arguments": {
                        "query": "test query",
                        "collection": "users.documents",
                        "limit": 5
                    }
                }
            },
            headers=headers
        )
        result = search_resp.json()
        assert "error" not in result, f"users.documents 접근 실패: {result}"
        
        # admin.secrets collection 검색 - 실패해야 함
        search_resp = await auth_client.post(
            "/mcp/proxy",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "search_vectors",
                    "arguments": {
                        "query": "test query",
                        "collection": "admin.secrets",
                        "limit": 5
                    }
                }
            },
            headers=headers
        )
        result = search_resp.json()
        assert "error" in result
        assert "admin.secrets에 대한 접근 권한이 없습니다" in result["error"]["message"]
        
        # 2. Power user: 모든 collection 읽기 가능
        headers = {"Authorization": f"Bearer {users['power']['access_token']}"}
        
        # 모든 collection 접근 테스트
        for collection in ["users.documents", "admin.secrets", "analytics.metrics"]:
            search_resp = await auth_client.post(
                "/mcp/proxy",
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "search_vectors",
                        "arguments": {
                            "query": "test query",
                            "collection": collection,
                            "limit": 5
                        }
                    }
                },
                headers=headers
            )
            result = search_resp.json()
            assert "error" not in result, f"{collection} 접근 실패: {result}"
    
    async def test_database_table_permissions(
        self,
        auth_client: httpx.AsyncClient,
        mcp_client: httpx.AsyncClient
    ):
        """Database table 레벨 권한 테스트"""
        users = await self.setup_test_users(auth_client)
        
        # 1. Basic user: public.* 테이블만 읽기 가능
        headers = {"Authorization": f"Bearer {users['basic']['access_token']}"}
        
        # public.users 테이블 조회 - 성공해야 함
        query_resp = await auth_client.post(
            "/mcp/proxy",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "search_database",
                    "arguments": {
                        "query": "SELECT * FROM public.users LIMIT 5"
                    }
                }
            },
            headers=headers
        )
        result = query_resp.json()
        assert "error" not in result, f"public.users 조회 실패: {result}"
        
        # analytics.metrics 테이블 조회 - 실패해야 함
        query_resp = await auth_client.post(
            "/mcp/proxy",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "search_database",
                    "arguments": {
                        "query": "SELECT * FROM analytics.metrics LIMIT 5"
                    }
                }
            },
            headers=headers
        )
        result = query_resp.json()
        assert "error" in result
        assert "analytics.metrics에 대한 접근 권한이 없습니다" in result["error"]["message"]
        
        # 2. Power user: analytics.* 스키마 읽기/쓰기 가능
        headers = {"Authorization": f"Bearer {users['power']['access_token']}"}
        
        # analytics.metrics 테이블 조회 - 성공해야 함
        query_resp = await auth_client.post(
            "/mcp/proxy",
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "search_database",
                    "arguments": {
                        "query": "SELECT * FROM analytics.metrics LIMIT 5"
                    }
                }
            },
            headers=headers
        )
        result = query_resp.json()
        assert "error" not in result, f"analytics.metrics 조회 실패: {result}"
    
    async def test_wildcard_pattern_matching(
        self,
        auth_client: httpx.AsyncClient,
        mcp_client: httpx.AsyncClient
    ):
        """와일드카드 패턴 매칭 테스트"""
        users = await self.setup_test_users(auth_client)
        
        # Basic user: users.* 패턴으로 모든 users 시작 collection 접근 가능
        headers = {"Authorization": f"Bearer {users['basic']['access_token']}"}
        
        # 다양한 users.* 패턴 테스트
        test_collections = [
            ("users.documents", True),      # 매칭됨
            ("users.profiles", True),       # 매칭됨
            ("users.settings.v2", True),    # 매칭됨
            ("user.data", False),           # 매칭 안됨 (users가 아님)
            ("admin.users", False),         # 매칭 안됨 (users로 시작 안함)
        ]
        
        for collection, should_succeed in test_collections:
            search_resp = await auth_client.post(
                "/mcp/proxy",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "search_vectors",
                        "arguments": {
                            "query": "test",
                            "collection": collection,
                            "limit": 1
                        }
                    }
                },
                headers=headers
            )
            result = search_resp.json()
            
            if should_succeed:
                assert "error" not in result, f"{collection} 접근 실패: {result}"
            else:
                assert "error" in result, f"{collection} 접근이 성공했지만 실패해야 함"
                assert "접근 권한이 없습니다" in result["error"]["message"]
    
    async def test_permission_inheritance(
        self,
        auth_client: httpx.AsyncClient,
        mcp_client: httpx.AsyncClient
    ):
        """권한 상속 및 우선순위 테스트"""
        users = await self.setup_test_users(auth_client)
        
        # Admin은 명시적 권한 없이도 모든 리소스 접근 가능
        headers = {"Authorization": f"Bearer {users['admin']['access_token']}"}
        
        # 임의의 collection/table 접근 테스트
        random_resources = [
            ("search_vectors", {"collection": "random.collection"}),
            ("search_database", {"query": "SELECT * FROM secret.data"}),
            ("search_vectors", {"collection": "super.secret.collection"}),
        ]
        
        for tool_name, args in random_resources:
            resp = await auth_client.post(
                "/mcp/proxy",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": {**args, "limit": 1}
                    }
                },
                headers=headers
            )
            result = resp.json()
            # Admin은 모든 접근 가능 (실제 리소스가 없어도 권한 체크는 통과)
            # 에러가 있다면 권한 문제가 아닌 다른 이유여야 함
            if "error" in result:
                assert "권한이 없습니다" not in result["error"]["message"]
    
    async def test_tool_list_filtering_by_role(
        self,
        auth_client: httpx.AsyncClient,
        mcp_client: httpx.AsyncClient
    ):
        """역할별 도구 목록 필터링 테스트"""
        import uuid
        unique_id = uuid.uuid4().hex[:8]
        
        # 1. Guest user 생성 (health_check만 접근 가능)
        guest_email = f"guest-{unique_id}@example.com"
        guest_resp = await auth_client.post(
            "/auth/register",
            json={
                "email": guest_email,
                "password": "Guest123!",
                "username": "guest_user"
            }
        )
        assert guest_resp.status_code == 200
        
        # Guest로 로그인
        login_resp = await auth_client.post(
            "/auth/login",
            json={"email": guest_email, "password": "Guest123!"}
        )
        guest_token = login_resp.json()["access_token"]
        
        # 2. User 생성 (기본 user 역할)
        user_email = f"user-{unique_id}@example.com"
        user_resp = await auth_client.post(
            "/auth/register",
            json={
                "email": user_email,
                "password": "User123!",
                "username": "normal_user"
            }
        )
        assert user_resp.status_code == 200
        
        login_resp = await auth_client.post(
            "/auth/login",
            json={"email": user_email, "password": "User123!"}
        )
        user_token = login_resp.json()["access_token"]
        
        # 3. Admin user 생성
        admin_email = f"admin-{unique_id}@example.com"
        admin_resp = await auth_client.post(
            "/auth/register",
            json={
                "email": admin_email,
                "password": "Admin123!",
                "username": "admin_user"
            }
        )
        assert admin_resp.status_code == 200
        
        login_resp = await auth_client.post(
            "/auth/login",
            json={"email": admin_email, "password": "Admin123!"}
        )
        admin_token = login_resp.json()["access_token"]
        
        # Guest user: health_check만 표시되어야 함
        headers = {"Authorization": f"Bearer {guest_token}"}
        tools_resp = await auth_client.post(
            "/mcp/proxy",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list"
            },
            headers=headers
        )
        result = tools_resp.json()
        print(f"Guest tools response: {result}")  # 디버깅용
        assert "result" in result, f"Expected 'result' in response but got: {result}"
        tools = result["result"]["tools"]
        tool_names = [tool["name"] for tool in tools]
        
        # Guest는 health_check만 접근 가능
        assert "health_check" in tool_names
        assert "search_web" not in tool_names  # 최소 역할 제한으로 접근 불가
        assert "search_vectors" not in tool_names
        assert "search_database" not in tool_names
        assert "search_all" not in tool_names
        assert len(tools) == 1, f"Guest는 1개 도구만 접근 가능해야 함. 실제: {tool_names}"
        
        # User: health_check, search_web, search_vectors 접근 가능
        headers = {"Authorization": f"Bearer {user_token}"}
        tools_resp = await auth_client.post(
            "/mcp/proxy",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list"
            },
            headers=headers
        )
        result = tools_resp.json()
        tools = result["result"]["tools"]
        tool_names = [tool["name"] for tool in tools]
        
        assert "health_check" in tool_names
        assert "search_web" in tool_names
        assert "search_vectors" in tool_names
        assert "search_database" not in tool_names  # admin만 가능
        assert "search_all" not in tool_names  # admin만 가능
        assert len(tools) == 3, f"User는 3개 도구 접근 가능해야 함. 실제: {tool_names}"
        
        # Admin: 모든 도구 접근 가능
        headers = {"Authorization": f"Bearer {admin_token}"}
        tools_resp = await auth_client.post(
            "/mcp/proxy",
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/list"
            },
            headers=headers
        )
        result = tools_resp.json()
        tools = result["result"]["tools"]
        tool_names = [tool["name"] for tool in tools]
        
        assert "health_check" in tool_names
        assert "search_web" in tool_names
        assert "search_vectors" in tool_names
        assert "search_database" in tool_names
        assert "search_all" in tool_names
        assert len(tools) == 5, f"Admin은 5개 도구 모두 접근 가능해야 함. 실제: {tool_names}"
    
    @pytest.mark.parametrize("query,expected_tables", [
        (
            "SELECT u.*, p.* FROM users u JOIN profiles p ON u.id = p.user_id",
            ["public.users", "public.profiles"]
        ),
        (
            "SELECT * FROM analytics.metrics WHERE date > '2024-01-01'",
            ["analytics.metrics"]
        ),
        (
            "SELECT * FROM \"special.table\" WHERE active = true",
            ["public.special.table"]
        ),
    ])
    async def test_sql_table_extraction(
        self,
        auth_client: httpx.AsyncClient,
        query: str,
        expected_tables: list[str]
    ):
        """SQL 쿼리에서 테이블 추출 로직 테스트"""
        # MCP 프록시의 _extract_tool_resources 메서드 동작 검증
        # 실제로는 단위 테스트로 하는 것이 더 적절하지만, E2E 관점에서 검증
        
        users = await self.setup_test_users(auth_client)
        headers = {"Authorization": f"Bearer {users['basic']['access_token']}"}
        
        # 쿼리 실행 시도
        resp = await auth_client.post(
            "/mcp/proxy",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "search_database",
                    "arguments": {"query": query}
                }
            },
            headers=headers
        )
        
        # Basic user는 public.* 만 접근 가능
        result = resp.json()
        has_non_public = any(not table.startswith("public.") for table in expected_tables)
        
        if has_non_public:
            assert "error" in result
            assert "접근 권한이 없습니다" in result["error"]["message"]
        else:
            # public 스키마만 있는 경우 성공해야 함
            assert "error" not in result or "권한" not in result.get("error", {}).get("message", "")