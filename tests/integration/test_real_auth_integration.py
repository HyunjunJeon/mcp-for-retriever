"""실제 인증 서버와 데이터베이스를 사용한 통합 테스트"""

import asyncio
import os
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.auth.server import app
from src.auth.database import Base, get_db
from src.auth.models import UserCreate
from src.auth.services import AuthService, JWTService, RBACService


class TestRealAuthIntegration:
    """실제 서버 컴포넌트를 사용한 통합 테스트"""
    
    @pytest.fixture
    async def test_db(self):
        """테스트용 인메모리 SQLite 데이터베이스"""
        # 인메모리 SQLite 사용
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            echo=False
        )
        
        # 테이블 생성
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        # 세션 팩토리
        async_session = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        
        # 의존성 오버라이드
        async def override_get_db():
            async with async_session() as session:
                yield session
        
        app.dependency_overrides[get_db] = override_get_db
        
        yield engine
        
        # 정리
        await engine.dispose()
        app.dependency_overrides.clear()
    
    @pytest.fixture
    async def client(self, test_db):
        """비동기 HTTP 클라이언트"""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac
    
    async def test_full_authentication_flow(self, client):
        """전체 인증 플로우 테스트"""
        # 1. 헬스 체크
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        
        # 2. 사용자 등록
        user_data = {
            "email": "test@example.com",
            "password": "SecurePassword123!",
            "name": "Test User"
        }
        
        response = await client.post("/auth/register", json=user_data)
        assert response.status_code == 201
        
        user_response = response.json()
        assert user_response["email"] == user_data["email"]
        assert user_response["name"] == user_data["name"]
        assert "id" in user_response
        assert "password" not in user_response
        
        # 3. 로그인
        login_data = {
            "username": user_data["email"],
            "password": user_data["password"]
        }
        
        response = await client.post("/auth/token", data=login_data)
        assert response.status_code == 200
        
        token_response = response.json()
        assert "access_token" in token_response
        assert "refresh_token" in token_response
        assert token_response["token_type"] == "bearer"
        
        access_token = token_response["access_token"]
        
        # 4. 인증된 요청
        headers = {"Authorization": f"Bearer {access_token}"}
        response = await client.get("/auth/me", headers=headers)
        assert response.status_code == 200
        
        me_response = response.json()
        assert me_response["email"] == user_data["email"]
        assert me_response["name"] == user_data["name"]
        
        # 5. 토큰 갱신
        refresh_data = {
            "refresh_token": token_response["refresh_token"]
        }
        
        response = await client.post("/auth/refresh", json=refresh_data)
        assert response.status_code == 200
        
        new_tokens = response.json()
        assert "access_token" in new_tokens
        assert "refresh_token" in new_tokens
        
        # 6. 새 토큰으로 요청
        new_headers = {"Authorization": f"Bearer {new_tokens['access_token']}"}
        response = await client.get("/auth/me", headers=new_headers)
        assert response.status_code == 200
        
        # 7. 로그아웃
        response = await client.post("/auth/logout", headers=headers)
        assert response.status_code == 200
    
    async def test_duplicate_registration(self, client):
        """중복 등록 방지 테스트"""
        user_data = {
            "email": "duplicate@example.com",
            "password": "Password123!",
            "name": "Duplicate User"
        }
        
        # 첫 번째 등록 - 성공
        response = await client.post("/auth/register", json=user_data)
        assert response.status_code == 201
        
        # 두 번째 등록 - 실패
        response = await client.post("/auth/register", json=user_data)
        assert response.status_code == 400
        assert "already registered" in response.json()["detail"]
    
    async def test_invalid_credentials(self, client):
        """잘못된 인증 정보 테스트"""
        # 등록
        user_data = {
            "email": "invalid@example.com",
            "password": "CorrectPassword123!",
            "name": "Invalid Test"
        }
        
        response = await client.post("/auth/register", json=user_data)
        assert response.status_code == 201
        
        # 잘못된 비밀번호로 로그인
        login_data = {
            "username": user_data["email"],
            "password": "WrongPassword123!"
        }
        
        response = await client.post("/auth/token", data=login_data)
        assert response.status_code == 401
        assert "Invalid" in response.json()["detail"]
    
    async def test_token_expiration(self, client):
        """토큰 만료 테스트"""
        # JWT 서비스를 짧은 만료 시간으로 설정
        os.environ["JWT_ACCESS_TOKEN_EXPIRE_MINUTES"] = "0.01"  # 0.6초
        
        # 사용자 등록 및 로그인
        user_data = {
            "email": "expiry@example.com",
            "password": "Password123!",
            "name": "Expiry Test"
        }
        
        await client.post("/auth/register", json=user_data)
        
        login_response = await client.post("/auth/token", data={
            "username": user_data["email"],
            "password": user_data["password"]
        })
        
        access_token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # 즉시 요청 - 성공
        response = await client.get("/auth/me", headers=headers)
        assert response.status_code == 200
        
        # 1초 대기 후 요청 - 실패
        await asyncio.sleep(1)
        response = await client.get("/auth/me", headers=headers)
        assert response.status_code == 401
        
        # 환경 변수 원복
        os.environ.pop("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", None)
    
    async def test_mcp_proxy_integration(self, client):
        """MCP 프록시 통합 테스트"""
        # 사용자 등록 및 로그인
        user_data = {
            "email": "mcp@example.com",
            "password": "MCPPassword123!",
            "name": "MCP User"
        }
        
        await client.post("/auth/register", json=user_data)
        
        login_response = await client.post("/auth/token", data={
            "username": user_data["email"],
            "password": user_data["password"]
        })
        
        access_token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # MCP 요청 (실제 MCP 서버가 없으므로 404 예상)
        mcp_request = {
            "jsonrpc": "2.0",
            "method": "test_method",
            "params": {},
            "id": 1
        }
        
        response = await client.post("/mcp/execute", json=mcp_request, headers=headers)
        # 실제 MCP 서버가 없으므로 프록시 오류 발생
        assert response.status_code in [502, 503]  # Bad Gateway or Service Unavailable
    
    async def test_concurrent_registrations(self, client):
        """동시 등록 처리 테스트"""
        # 10명의 사용자를 동시에 등록
        async def register_user(index: int):
            user_data = {
                "email": f"concurrent{index}@example.com",
                "password": "Password123!",
                "name": f"Concurrent User {index}"
            }
            response = await client.post("/auth/register", json=user_data)
            return response.status_code == 201
        
        # 동시 실행
        tasks = [register_user(i) for i in range(10)]
        results = await asyncio.gather(*tasks)
        
        # 모든 등록이 성공해야 함
        assert all(results)
    
    async def test_password_validation(self, client):
        """비밀번호 검증 테스트"""
        test_cases = [
            ("short", False),  # 너무 짧음
            ("nouppercase123!", False),  # 대문자 없음
            ("NOLOWERCASE123!", False),  # 소문자 없음
            ("NoNumbers!", False),  # 숫자 없음
            ("NoSpecial123", False),  # 특수문자 없음
            ("ValidPass123!", True),  # 유효함
        ]
        
        for i, (password, should_succeed) in enumerate(test_cases):
            user_data = {
                "email": f"pwtest{i}@example.com",
                "password": password,
                "name": f"Password Test {i}"
            }
            
            response = await client.post("/auth/register", json=user_data)
            
            if should_succeed:
                assert response.status_code == 201
            else:
                assert response.status_code == 422  # Validation error