"""인증 서버 통합 테스트"""

from typing import Any
import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from src.auth.server import app
from src.auth.models import UserCreate, UserLogin


class TestAuthServer:
    """인증 서버 통합 테스트"""
    
    @pytest.fixture
    def client(self) -> TestClient:
        """테스트 클라이언트"""
        return TestClient(app)
    
    @pytest.fixture
    def test_user_data(self) -> dict[str, Any]:
        """테스트 사용자 데이터"""
        return {
            "email": "test@example.com",
            "password": r"TestPassword123!",
            "roles": ["user"],
        }
    
    def test_health_check(self, client: TestClient) -> None:
        """헬스체크 테스트"""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "auth-gateway"
    
    def test_register_user(self, client: TestClient, test_user_data: dict) -> None:
        """사용자 등록 테스트"""
        response = client.post("/auth/register", json=test_user_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_user_data["email"]
        assert data["roles"] == test_user_data["roles"]
        assert data["is_active"] is True
        assert "id" in data
        assert "created_at" in data
    
    def test_register_duplicate_email(self, client: TestClient) -> None:
        """중복 이메일 등록 테스트"""
        # admin@example.com은 기본으로 등록되어 있음
        user_data = {
            "email": "admin@example.com",
            "password": r"NewPassword123!",
            "roles": ["user"],
        }
        
        response = client.post("/auth/register", json=user_data)
        
        assert response.status_code == 400
        assert "이미 등록된 이메일" in response.json()["detail"]
    
    def test_login_success(self, client: TestClient) -> None:
        """로그인 성공 테스트"""
        # 기본 사용자로 로그인
        login_data = {
            "email": "admin@example.com",
            "password": r"Admin123!",  # raw string to avoid escape sequences
        }
        
        response = client.post("/auth/login", json=login_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "Bearer"
    
    def test_login_wrong_password(self, client: TestClient) -> None:
        """잘못된 비밀번호 로그인 테스트"""
        login_data = {
            "email": "admin@example.com",
            "password": r"WrongPassword123!",
        }
        
        response = client.post("/auth/login", json=login_data)
        
        assert response.status_code == 401
        assert "이메일 또는 비밀번호가 올바르지 않습니다" in response.json()["detail"]
    
    def test_get_current_user(self, client: TestClient) -> None:
        """현재 사용자 조회 테스트"""
        # 먼저 로그인
        login_response = client.post("/auth/login", json={
            "email": "admin@example.com",
            "password": r"Admin123!",
        })
        token = login_response.json()["access_token"]
        
        # 토큰으로 현재 사용자 조회
        response = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "admin@example.com"
        assert data["roles"] == ["admin"]
        assert data["is_active"] is True
    
    def test_get_current_user_invalid_token(self, client: TestClient) -> None:
        """잘못된 토큰으로 사용자 조회 테스트"""
        response = client.get(
            "/auth/me",
            headers={"Authorization": "Bearer invalid_token"},
        )
        
        assert response.status_code == 401
    
    def test_refresh_tokens(self, client: TestClient) -> None:
        """토큰 갱신 테스트"""
        # 고유한 이메일로 새 사용자 등록
        unique_email = f"refresh_test_{uuid.uuid4().hex[:8]}@example.com"
        user_data = {
            "email": unique_email,
            "password": r"TestPassword123!",
            "roles": ["user"],
        }
        
        register_response = client.post("/auth/register", json=user_data)
        assert register_response.status_code == 200
        
        # 로그인
        login_response = client.post("/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"],
        })
        refresh_token = login_response.json()["refresh_token"]
        
        # 토큰 갱신
        response = client.post(
            "/auth/refresh",
            params={"refresh_token": refresh_token},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["refresh_token"] == refresh_token  # 리프레시 토큰은 재사용
    
    def test_mcp_proxy_with_permission(self, client: TestClient) -> None:
        """권한이 있는 MCP 프록시 요청 테스트"""
        # admin으로 로그인
        login_response = client.post("/auth/login", json={
            "email": "admin@example.com",
            "password": r"Admin123!",
        })
        token = login_response.json()["access_token"]
        
        # MCP 요청 (실제 MCP 서버가 없으므로 연결 오류 예상)
        mcp_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "search_web",
                "arguments": {"query": "test"},
            },
        }
        
        response = client.post(
            "/mcp/proxy",
            json=mcp_request,
            headers={"Authorization": f"Bearer {token}"},
        )
        
        assert response.status_code == 200
        data = response.json()
        # MCP 서버가 없으므로 연결 오류 응답 예상
        assert data["error"] is not None
        assert "MCP 서버에 연결할 수 없습니다" in data["error"]["message"]
    
    def test_mcp_proxy_without_permission(self, client: TestClient) -> None:
        """권한이 없는 MCP 프록시 요청 테스트"""
        # 고유한 이메일로 새 사용자 등록 (user 역할만 가짐)
        unique_email = f"permission_test_{uuid.uuid4().hex[:8]}@example.com"
        user_data = {
            "email": unique_email,
            "password": r"TestPassword123!",
            "roles": ["user"],
        }
        
        register_response = client.post("/auth/register", json=user_data)
        assert register_response.status_code == 200
        
        # 로그인
        login_response = client.post("/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"],
        })
        token = login_response.json()["access_token"]
        
        # 권한이 없는 도구 호출
        mcp_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "search_vectors",  # WRITE 권한 필요
                "arguments": {"query": "test"},
            },
        }
        
        response = client.post(
            "/mcp/proxy",
            json=mcp_request,
            headers={"Authorization": f"Bearer {token}"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["error"] is not None
        assert "도구 사용 권한이 없습니다" in data["error"]["message"]
    
    def test_batch_mcp_proxy(self, client: TestClient) -> None:
        """배치 MCP 프록시 요청 테스트"""
        # admin으로 로그인
        login_response = client.post("/auth/login", json={
            "email": "admin@example.com",
            "password": r"Admin123!",
        })
        token = login_response.json()["access_token"]
        
        # 배치 요청
        mcp_requests = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "search_web", "arguments": {"query": "test1"}},
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "search_database", "arguments": {"query": "test2"}},
            },
        ]
        
        response = client.post(
            "/mcp/batch",
            json=mcp_requests,
            headers={"Authorization": f"Bearer {token}"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        # 모두 연결 오류 응답 예상
        for resp in data:
            assert resp["error"] is not None
    
    def test_admin_endpoint_with_admin_role(self, client: TestClient) -> None:
        """관리자 엔드포인트 접근 테스트 (관리자)"""
        # admin으로 로그인
        login_response = client.post("/auth/login", json={
            "email": "admin@example.com",
            "password": r"Admin123!",
        })
        token = login_response.json()["access_token"]
        
        response = client.get(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_admin_endpoint_with_user_role(self, client: TestClient) -> None:
        """관리자 엔드포인트 접근 테스트 (일반 사용자)"""
        # 고유한 이메일로 새 사용자 등록
        unique_email = f"admin_test_{uuid.uuid4().hex[:8]}@example.com"
        user_data = {
            "email": unique_email,
            "password": r"TestPassword123!",
            "roles": ["user"],
        }
        
        register_response = client.post("/auth/register", json=user_data)
        assert register_response.status_code == 200
        
        # 로그인
        login_response = client.post("/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"],
        })
        token = login_response.json()["access_token"]
        
        response = client.get(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        
        assert response.status_code == 403
        assert "권한이 없습니다" in response.json()["detail"]