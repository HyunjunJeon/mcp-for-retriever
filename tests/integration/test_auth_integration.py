"""Integration tests for authentication gateway with MCP server."""

import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from src.auth.server import app
from src.auth.models import User, Role, Permission
from src.auth.services.jwt_service import JWTService


class TestAuthIntegration:
    """Test authentication integration with MCP server."""
    
    @pytest.fixture
    def app(self):
        """Get test app."""
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)
    
    @pytest.fixture
    def jwt_service(self):
        """Create JWT service."""
        return JWTService(secret_key="test-secret-key")
    
    @pytest.fixture
    def test_user(self):
        """Create test user."""
        return User(
            id="user-123",
            email="user@example.com",
            name="Test User",
            password_hash="hashed",
            roles=["user"],
            is_active=True,
            created_at=datetime.utcnow()
        )
    
    @pytest.fixture
    def admin_user(self):
        """Create admin user."""
        return User(
            id="admin-123",
            email="admin@example.com",
            name="Admin User",
            password_hash="hashed",
            roles=["admin"],
            is_active=True,
            created_at=datetime.utcnow()
        )
    
    async def test_user_registration_flow(self, client):
        """Test complete user registration flow."""
        # 1. Register new user
        registration_data = {
            "email": "newuser@example.com",
            "password": "SecurePass123!",
            "name": "New User"
        }
        
        response = client.post("/api/v1/auth/register", json=registration_data)
        assert response.status_code == 201
        
        user_data = response.json()
        assert user_data["email"] == "newuser@example.com"
        assert user_data["name"] == "New User"
        assert user_data["role"] == "user"
        assert "id" in user_data
        assert "password" not in user_data
        assert "password_hash" not in user_data
        
        # 2. Try to register with same email (should fail)
        response = client.post("/api/v1/auth/register", json=registration_data)
        assert response.status_code == 400
        assert "already registered" in response.json()["detail"]
        
        # 3. Login with registered credentials
        login_response = client.post(
            "/api/v1/auth/token",
            data={
                "username": "newuser@example.com",
                "password": "SecurePass123!"
            }
        )
        assert login_response.status_code == 200
        
        token_data = login_response.json()
        assert "access_token" in token_data
        assert "refresh_token" in token_data
        assert token_data["token_type"] == "bearer"
        
        # 4. Access protected endpoint
        me_response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token_data['access_token']}"}
        )
        assert me_response.status_code == 200
        
        me_data = me_response.json()
        assert me_data["email"] == "newuser@example.com"
    
    async def test_token_refresh_flow(self, client, jwt_service, test_user):
        """Test token refresh flow."""
        # Create tokens
        access_token = jwt_service.create_access_token(test_user)
        refresh_token = jwt_service.create_refresh_token(test_user)
        
        # Mock auth service to return user
        with patch('src.auth.server.auth_service.get_user_by_id') as mock_get_user:
            mock_get_user.return_value = test_user
            
            # Refresh token
            refresh_response = client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": refresh_token}
            )
            assert refresh_response.status_code == 200
            
            new_tokens = refresh_response.json()
            assert "access_token" in new_tokens
            assert "refresh_token" in new_tokens
            
            # New access token should work
            me_response = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {new_tokens['access_token']}"}
            )
            assert me_response.status_code == 200
    
    async def test_mcp_proxy_authentication(self, client, jwt_service, test_user):
        """Test MCP proxy with authentication."""
        access_token = jwt_service.create_access_token(test_user)
        
        # Mock MCP proxy service
        with patch('src.auth.server.mcp_proxy') as mock_proxy:
            mock_result = {
                "jsonrpc": "2.0",
                "result": {"status": "success", "data": "test"},
                "id": 1
            }
            mock_proxy.execute_request.return_value = mock_result
            
            # Valid MCP request
            mcp_request = {
                "jsonrpc": "2.0",
                "method": "search_web",
                "params": {"query": "test"},
                "id": 1
            }
            
            response = client.post(
                "/api/v1/mcp/execute",
                json=mcp_request,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            assert response.status_code == 200
            assert response.json() == mock_result
            
            # Verify proxy was called with correct parameters
            mock_proxy.execute_request.assert_called_once()
            call_args = mock_proxy.execute_request.call_args
            assert call_args[0][0] == mcp_request
            assert call_args[0][1] == test_user
    
    async def test_mcp_proxy_batch_requests(self, client, jwt_service, test_user):
        """Test MCP proxy with batch requests."""
        access_token = jwt_service.create_access_token(test_user)
        
        with patch('src.auth.server.mcp_proxy') as mock_proxy:
            # Mock responses for batch
            mock_results = [
                {"jsonrpc": "2.0", "result": {"data": "result1"}, "id": 1},
                {"jsonrpc": "2.0", "result": {"data": "result2"}, "id": 2}
            ]
            mock_proxy.execute_batch_request.return_value = mock_results
            
            # Batch request
            batch_request = [
                {
                    "jsonrpc": "2.0",
                    "method": "search_web",
                    "params": {"query": "test1"},
                    "id": 1
                },
                {
                    "jsonrpc": "2.0",
                    "method": "search_database", 
                    "params": {"query": "SELECT * FROM test"},
                    "id": 2
                }
            ]
            
            response = client.post(
                "/api/v1/mcp/execute",
                json=batch_request,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            assert response.status_code == 200
            assert response.json() == mock_results
    
    async def test_mcp_proxy_permission_check(self, client, jwt_service, test_user):
        """Test MCP proxy checks tool permissions."""
        access_token = jwt_service.create_access_token(test_user)
        
        # Mock RBAC service to deny permission
        with patch('src.auth.server.rbac_service.check_tool_permission') as mock_check:
            mock_check.return_value = False
            
            mcp_request = {
                "jsonrpc": "2.0",
                "method": "admin_tool",
                "params": {},
                "id": 1
            }
            
            response = client.post(
                "/api/v1/mcp/execute",
                json=mcp_request,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            assert response.status_code == 200  # JSON-RPC always returns 200
            result = response.json()
            assert "error" in result
            assert "permission" in result["error"]["message"].lower()
    
    async def test_admin_endpoints(self, client, jwt_service, admin_user):
        """Test admin-only endpoints."""
        admin_token = jwt_service.create_access_token(admin_user)
        
        # 1. List users
        with patch('src.auth.server.auth_service.list_users') as mock_list:
            mock_list.return_value = [admin_user]
            
            response = client.get(
                "/api/v1/admin/users",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            assert response.status_code == 200
            users = response.json()
            assert len(users) == 1
            assert users[0]["email"] == "admin@example.com"
        
        # 2. Update user role
        with patch('src.auth.server.auth_service.update_user_role') as mock_update:
            mock_update.return_value = True
            
            response = client.put(
                "/api/v1/admin/users/user-123/role",
                json={"role": "admin"},
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            assert response.status_code == 200
        
        # 3. Grant tool permission
        with patch('src.auth.server.rbac_service.grant_permission') as mock_grant:
            response = client.post(
                "/api/v1/admin/permissions/grant",
                json={
                    "user_id": "user-123",
                    "tool_name": "search_vectors",
                    "granted_by": admin_user.id
                },
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            assert response.status_code == 200
    
    async def test_non_admin_cannot_access_admin_endpoints(self, client, jwt_service, test_user):
        """Test that regular users cannot access admin endpoints."""
        user_token = jwt_service.create_access_token(test_user)
        
        # Try to list users
        response = client.get(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403
        
        # Try to update role
        response = client.put(
            "/api/v1/admin/users/user-123/role",
            json={"role": "admin"},
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403
    
    async def test_logout_flow(self, client, jwt_service, test_user):
        """Test logout flow."""
        access_token = jwt_service.create_access_token(test_user)
        
        with patch('src.auth.server.auth_service.logout') as mock_logout:
            mock_logout.return_value = True
            
            # Logout
            response = client.post(
                "/api/v1/auth/logout",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            assert response.status_code == 200
            
            # Verify token was passed to logout
            mock_logout.assert_called_once_with(access_token)
    
    async def test_invalid_token_handling(self, client):
        """Test handling of invalid tokens."""
        # 1. No token
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401
        
        # 2. Invalid format
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "InvalidFormat"}
        )
        assert response.status_code == 401
        
        # 3. Invalid token
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"}
        )
        assert response.status_code == 401
    
    async def test_rate_limiting(self, client):
        """Test rate limiting on auth endpoints."""
        # Note: Actual rate limiting implementation would be needed
        # This is a placeholder test
        
        # Try multiple login attempts
        for i in range(10):
            response = client.post(
                "/api/v1/auth/token",
                data={
                    "username": "test@example.com",
                    "password": "wrong_password"
                }
            )
            # After certain attempts, should get rate limited
            if i > 5:
                # Would expect 429 Too Many Requests
                pass