"""기본 E2E 테스트 - Playwright 동작 확인."""

import pytest
from playwright.async_api import Page, expect


@pytest.mark.e2e
class TestBasic:
    """기본 E2E 테스트."""

    async def test_google_page(self, page: Page):
        """Google 페이지 접근 테스트 (Playwright 동작 확인)."""
        await page.goto("https://www.google.com")
        title = await page.title()
        assert "Google" in title

    async def test_auth_gateway_health(self, page: Page, base_url: str):
        """Auth Gateway 헬스 체크 테스트."""
        await page.goto(f"{base_url}/health")
        # JSON 응답 확인
        content = await page.content()
        assert "healthy" in content or "status" in content

    async def test_mcp_server_health(self, page: Page, mcp_url: str):
        """MCP Server 헬스 체크 테스트."""
        await page.goto(f"{mcp_url}/health")
        # JSON 응답 확인
        content = await page.content()
        assert "healthy" in content or "status" in content

    async def test_login_page_access(self, page: Page, base_url: str):
        """로그인 페이지 접근 테스트."""
        await page.goto(f"{base_url}/auth/login-page")
        await page.wait_for_load_state("networkidle")
        
        # 페이지 제목 확인
        title = await page.title()
        assert "MCP" in title or "로그인" in title
        
        # 폼 요소 존재 확인
        email_input = page.locator('input[name="email"]')
        password_input = page.locator('input[name="password"]')
        submit_button = page.locator('button[type="submit"]')
        
        await expect(email_input).to_be_visible()
        await expect(password_input).to_be_visible()
        await expect(submit_button).to_be_visible()