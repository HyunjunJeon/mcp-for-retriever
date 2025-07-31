"""
E2E 테스트를 위한 공통 fixture 모음
"""

import asyncio
import os
from typing import AsyncGenerator

import httpx
import pytest
from playwright.async_api import Page, Browser


@pytest.fixture
async def auth_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Auth Gateway용 HTTP 클라이언트"""
    auth_url = os.getenv("AUTH_GATEWAY_URL", "http://localhost:8000")
    
    async with httpx.AsyncClient(
        base_url=auth_url,
        timeout=httpx.Timeout(30.0),
    ) as client:
        # Health check
        try:
            resp = await client.get("/health")
            resp.raise_for_status()
        except Exception as e:
            pytest.skip(f"Auth Gateway not available: {e}")
        
        yield client


@pytest.fixture
async def mcp_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """MCP Server용 HTTP 클라이언트"""
    mcp_url = os.getenv("MCP_SERVER_URL", "http://localhost:8001")
    
    async with httpx.AsyncClient(
        base_url=mcp_url,
        timeout=httpx.Timeout(30.0),
    ) as client:
        # Health check - MCP 서버는 다른 방식으로 체크
        # MCP 서버는 /health가 아닌 다른 엔드포인트를 사용할 수 있음
        yield client


@pytest.fixture
async def test_user(auth_client: httpx.AsyncClient) -> dict[str, str]:
    """테스트용 사용자 생성 및 로그인"""
    import uuid
    
    # 유니크한 이메일 생성
    email = f"test-{uuid.uuid4().hex[:8]}@example.com"
    password = "TestPass123!"
    
    # 사용자 등록
    register_resp = await auth_client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "username": "test_user"
        }
    )
    assert register_resp.status_code == 200
    
    # 로그인
    login_resp = await auth_client.post(
        "/auth/login",
        json={"email": email, "password": password}
    )
    assert login_resp.status_code == 200
    
    tokens = login_resp.json()
    return {
        "email": email,
        "password": password,
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"]
    }


@pytest.fixture
async def admin_user(auth_client: httpx.AsyncClient) -> dict[str, str]:
    """테스트용 관리자 생성 및 로그인"""
    # TODO: 실제 환경에서는 관리자 권한 설정 API 필요
    import uuid
    
    email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    password = "AdminPass123!"
    
    # 관리자 등록 (실제로는 별도 프로세스 필요)
    register_resp = await auth_client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "username": "admin_user",
            "roles": ["admin"]  # 실제로는 별도 API로 설정
        }
    )
    
    # 로그인
    login_resp = await auth_client.post(
        "/auth/login",
        json={"email": email, "password": password}
    )
    
    tokens = login_resp.json()
    return {
        "email": email,
        "password": password,
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"]
    }


@pytest.fixture
async def playwright_auth_page(
    page: Page,
    auth_client: httpx.AsyncClient
) -> Page:
    """Auth Gateway 로그인 페이지로 이동한 Playwright Page"""
    auth_url = str(auth_client.base_url)
    await page.goto(f"{auth_url}/auth/login-page")
    return page


@pytest.fixture
async def playwright_mcp_page(
    page: Page,
    auth_client: httpx.AsyncClient,
    test_user: dict[str, str]
) -> Page:
    """인증된 상태로 MCP 클라이언트 페이지로 이동한 Page"""
    auth_url = str(auth_client.base_url)
    
    # 로컬 스토리지에 토큰 설정
    await page.goto(auth_url)
    await page.evaluate(f"""
        localStorage.setItem('access_token', '{test_user["access_token"]}');
        localStorage.setItem('refresh_token', '{test_user["refresh_token"]}');
    """)
    
    # MCP 클라이언트 페이지로 이동
    await page.goto(f"{auth_url}/mcp/client-page")
    return page