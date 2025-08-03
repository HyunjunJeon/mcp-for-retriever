"""관리자 인증 E2E 테스트."""

import pytest
from playwright.async_api import Page, expect
from .helpers import (
    login_as_admin, 
    wait_for_admin_page, 
    assert_admin_access,
    check_error_state,
    take_screenshot_on_failure
)


@pytest.mark.e2e
@pytest.mark.admin_ui
class TestAdminAuth:
    """관리자 인증 관련 E2E 테스트."""

    async def test_admin_login_success(
        self, 
        admin_page: Page, 
        admin_credentials: dict, 
        base_url: str
    ):
        """관리자 로그인 성공 테스트."""
        try:
            # 로그인 페이지로 이동
            await admin_page.goto(f"{base_url}/auth/login-page")
            await admin_page.wait_for_load_state("networkidle")
            
            # 로그인 페이지 로딩 확인
            await expect(admin_page).to_have_title("MCP 로그인")
            
            # 로그인 폼 존재 확인
            await expect(admin_page.locator('input[name="email"]')).to_be_visible()
            await expect(admin_page.locator('input[name="password"]')).to_be_visible()
            await expect(admin_page.locator('button[type="submit"]')).to_be_visible()
            
            # 관리자 계정으로 로그인
            await login_as_admin(
                admin_page, 
                admin_credentials["email"], 
                admin_credentials["password"]
            )
            
            # 관리자 대시보드로 리다이렉트 확인
            await expect(admin_page).to_have_url(f"{base_url}/admin")
            
            # 관리자 권한 확인
            await assert_admin_access(admin_page)
            
            # 에러 상태 확인
            assert not await check_error_state(admin_page), "로그인 후 에러 상태 감지"
            
        except Exception as e:
            await take_screenshot_on_failure(admin_page, "admin_login_success")
            raise e

    async def test_admin_login_invalid_credentials(
        self, 
        admin_page: Page, 
        base_url: str
    ):
        """잘못된 계정 정보로 로그인 실패 테스트."""
        try:
            # 로그인 페이지로 이동
            await admin_page.goto(f"{base_url}/auth/login-page")
            await admin_page.wait_for_load_state("networkidle")
            
            # 잘못된 계정 정보 입력
            await admin_page.fill('input[name="email"]', "wrong@example.com")
            await admin_page.fill('input[name="password"]', "wrongpassword")
            
            # 로그인 시도
            await admin_page.click('button[type="submit"]')
            
            # 에러 메시지 확인 (페이지에 머물러야 함)
            await admin_page.wait_for_load_state("networkidle")
            
            # 로그인 실패 시 로그인 페이지에 머물러야 함
            current_url = admin_page.url
            assert "/auth/login" in current_url, f"로그인 실패 후 잘못된 URL: {current_url}"
            
            # 에러 메시지 또는 알림 확인
            error_indicators = [
                "text=Invalid credentials",
                "text=로그인 실패", 
                "text=잘못된",
                ".error",
                ".alert-error"
            ]
            
            error_found = False
            for indicator in error_indicators:
                try:
                    error_element = admin_page.locator(indicator)
                    if await error_element.is_visible():
                        error_found = True
                        break
                except:
                    continue
            
            assert error_found, "로그인 실패 에러 메시지를 찾을 수 없습니다"
            
        except Exception as e:
            await take_screenshot_on_failure(admin_page, "admin_login_invalid_credentials")
            raise e

    async def test_admin_logout(
        self, 
        logged_in_admin_page: Page, 
        base_url: str
    ):
        """관리자 로그아웃 테스트."""
        try:
            # 이미 로그인된 상태에서 시작
            await expect(logged_in_admin_page).to_have_url(f"{base_url}/admin")
            
            # 로그아웃 버튼 찾기 및 클릭
            logout_selectors = [
                "text=로그아웃",
                "text=Logout", 
                "[data-testid='logout']",
                "button:has-text('로그아웃')",
                "a:has-text('로그아웃')"
            ]
            
            logout_clicked = False
            for selector in logout_selectors:
                try:
                    logout_element = logged_in_admin_page.locator(selector)
                    if await logout_element.is_visible():
                        await logout_element.click()
                        logout_clicked = True
                        break
                except:
                    continue
            
            assert logout_clicked, "로그아웃 버튼을 찾을 수 없습니다"
            
            # 로그아웃 후 로그인 페이지로 리다이렉트 확인
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # 로그인 페이지 또는 홈페이지로 리다이렉트되어야 함
            current_url = logged_in_admin_page.url
            assert ("/auth/login" in current_url or current_url == base_url), \
                f"로그아웃 후 잘못된 URL: {current_url}"
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "admin_logout")
            raise e

    async def test_admin_access_protection(
        self, 
        admin_page: Page, 
        base_url: str
    ):
        """관리자 페이지 접근 보호 테스트 (미인증 상태)."""
        try:
            # 로그인하지 않은 상태에서 관리자 페이지 접근 시도
            protected_pages = [
                "/admin",
                "/admin/users", 
                "/admin/sessions",
                "/admin/permissions",
                "/admin/roles"
            ]
            
            for page_path in protected_pages:
                await admin_page.goto(f"{base_url}{page_path}")
                await admin_page.wait_for_load_state("networkidle")
                
                current_url = admin_page.url
                
                # 로그인 페이지로 리다이렉트되어야 함
                assert "/auth/login" in current_url, \
                    f"보호된 페이지 {page_path}에 미인증 접근이 허용됨: {current_url}"
            
        except Exception as e:
            await take_screenshot_on_failure(admin_page, "admin_access_protection")
            raise e

    async def test_admin_session_persistence(
        self, 
        admin_page: Page, 
        admin_credentials: dict, 
        base_url: str
    ):
        """관리자 세션 지속성 테스트."""
        try:
            # 관리자 로그인
            await login_as_admin(
                admin_page, 
                admin_credentials["email"], 
                admin_credentials["password"]
            )
            
            # 다른 관리자 페이지로 이동
            await admin_page.goto(f"{base_url}/admin/users")
            await admin_page.wait_for_load_state("networkidle")
            
            # 여전히 인증된 상태인지 확인
            await assert_admin_access(admin_page)
            
            # 페이지 새로고침 후에도 세션 유지 확인
            await admin_page.reload()
            await admin_page.wait_for_load_state("networkidle")
            
            # 여전히 로그인 상태인지 확인 (로그인 페이지로 리다이렉트되지 않아야 함)
            current_url = admin_page.url
            assert "/auth/login" not in current_url, "페이지 새로고침 후 세션이 유지되지 않음"
            
        except Exception as e:
            await take_screenshot_on_failure(admin_page, "admin_session_persistence")
            raise e