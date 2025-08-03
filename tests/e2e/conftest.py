"""E2E 테스트 전용 설정 및 fixtures."""

import pytest
import os
import asyncio
from typing import AsyncGenerator
from playwright.async_api import Page, Browser, BrowserContext


# E2E 테스트는 기본 conftest.py의 event_loop를 사용


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """E2E 테스트용 브라우저 컨텍스트 설정."""
    return {
        **browser_context_args,
        "viewport": {"width": 1920, "height": 1080},
        "ignore_https_errors": True,
        # E2E 테스트에서는 더 긴 타임아웃 설정
        "extra_http_headers": {"User-Agent": "E2E-Test-Agent"},
    }


@pytest.fixture(scope="session")
def base_url():
    """Auth Gateway 기본 URL."""
    return os.getenv("AUTH_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def mcp_url():
    """MCP Server 기본 URL."""
    return os.getenv("MCP_URL", "http://localhost:8001")


@pytest.fixture
def admin_credentials():
    """기본 관리자 계정 정보."""
    return {
        "email": os.getenv("ADMIN_EMAIL", "admin@example.com"),
        "password": os.getenv("ADMIN_PASSWORD", "Admin123!"),
    }


@pytest.fixture
def admin_page(page: Page, base_url: str) -> Page:
    """관리자 권한으로 로그인된 페이지."""
    # 기본 URL 설정
    page.base_url = base_url
    
    # 타임아웃 설정 (Docker 환경 고려)
    page.set_default_timeout(30000)  # 30초
    
    return page


@pytest.fixture
async def logged_in_admin_page(
    admin_page: Page, 
    admin_credentials: dict, 
    base_url: str
) -> Page:
    """관리자로 로그인된 상태의 페이지."""
    # 기본 로그인 수행 (helpers 없이)
    await admin_page.goto(f"{base_url}/auth/login-page")
    await admin_page.wait_for_load_state("networkidle")
    await admin_page.fill('input[name="email"]', admin_credentials["email"])
    await admin_page.fill('input[name="password"]', admin_credentials["password"])
    await admin_page.click('button[type="submit"]')
    await admin_page.wait_for_url(f"{base_url}/admin", timeout=30000)
    
    return admin_page


@pytest.fixture(autouse=True)
def setup_e2e_environment():
    """E2E 테스트 환경 설정."""
    test_env = {
        "ENVIRONMENT": "test",
        "LOG_LEVEL": "INFO",  # E2E 테스트에서는 INFO 레벨로 설정
        "PLAYWRIGHT_HEADLESS": os.getenv("PLAYWRIGHT_HEADLESS", "true"),
    }
    
    import unittest.mock
    with unittest.mock.patch.dict(os.environ, test_env):
        yield


# Playwright 마커 설정
def pytest_configure(config):
    """E2E 테스트용 마커 설정."""
    config.addinivalue_line("markers", "e2e: E2E 테스트 마커")
    config.addinivalue_line("markers", "admin_ui: Admin UI E2E 테스트")
    config.addinivalue_line("markers", "docker_required: Docker 환경 필요")


# 테스트 컬렉션 설정
def pytest_collection_modifyitems(config, items):
    """E2E 테스트에 마커 자동 추가."""
    for item in items:
        # E2E 테스트 디렉토리의 모든 테스트에 e2e 마커 추가
        if "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
            item.add_marker(pytest.mark.docker_required)