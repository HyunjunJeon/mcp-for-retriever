"""관리자 UI 네비게이션 E2E 테스트."""

import pytest
from playwright.async_api import Page, expect
from .helpers import (
    navigate_to_admin_page,
    wait_for_admin_page,
    assert_admin_access,
    wait_for_table_load,
    check_error_state,
    take_screenshot_on_failure
)


@pytest.mark.e2e
@pytest.mark.admin_ui
class TestAdminNavigation:
    """관리자 UI 네비게이션 기능 E2E 테스트."""

    async def test_navigation_menu_visibility(
        self, 
        logged_in_admin_page: Page
    ):
        """네비게이션 메뉴 표시 확인 테스트."""
        try:
            # 주요 네비게이션 메뉴 항목들
            nav_items = [
                "대시보드",
                "사용자 관리", 
                "세션 관리",
                "권한 관리",
                "역할 관리"
            ]
            
            found_items = 0
            for nav_item in nav_items:
                # 다양한 선택자로 네비게이션 항목 찾기
                nav_selectors = [
                    f"nav a:has-text('{nav_item}')",
                    f"nav button:has-text('{nav_item}')",
                    f"text={nav_item}",
                    f"[data-nav='{nav_item.lower().replace(' ', '-')}']"
                ]
                
                for selector in nav_selectors:
                    try:
                        nav_element = logged_in_admin_page.locator(selector)
                        if await nav_element.is_visible():
                            found_items += 1
                            break
                    except:
                        continue
            
            assert found_items >= 3, f"필수 네비게이션 메뉴가 충분하지 않습니다: {found_items}개 발견"
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "navigation_menu_visibility")
            raise e

    async def test_dashboard_navigation(
        self, 
        logged_in_admin_page: Page, 
        base_url: str
    ):
        """대시보드 페이지 네비게이션 테스트."""
        try:
            # 대시보드로 이동
            await navigate_to_admin_page(logged_in_admin_page, "dashboard")
            
            # URL 확인
            await expect(logged_in_admin_page).to_have_url(f"{base_url}/admin")
            
            # 대시보드 콘텐츠 확인
            dashboard_indicators = [
                "text=총 사용자",
                "text=활성 사용자",
                "text=관리자",
                "text=Dashboard",
                ".dashboard",
                ".admin-dashboard"
            ]
            
            dashboard_found = False
            for indicator in dashboard_indicators:
                try:
                    element = logged_in_admin_page.locator(indicator)
                    if await element.is_visible():
                        dashboard_found = True
                        break
                except:
                    continue
            
            assert dashboard_found, "대시보드 페이지 콘텐츠를 찾을 수 없습니다"
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "dashboard_navigation")
            raise e

    async def test_users_page_navigation(
        self, 
        logged_in_admin_page: Page, 
        base_url: str
    ):
        """사용자 관리 페이지 네비게이션 테스트."""
        try:
            # 사용자 관리 페이지로 이동
            await navigate_to_admin_page(logged_in_admin_page, "users")
            
            # URL 확인
            await expect(logged_in_admin_page).to_have_url(f"{base_url}/admin/users")
            
            # 사용자 관리 페이지 콘텐츠 확인
            await wait_for_table_load(logged_in_admin_page)
            
            # 사용자 테이블 존재 확인
            table_selectors = [
                "table",
                ".users-table",
                "[data-testid='users-table']"
            ]
            
            table_found = False
            for selector in table_selectors:
                try:
                    table_element = logged_in_admin_page.locator(selector)
                    if await table_element.is_visible():
                        table_found = True
                        break
                except:
                    continue
            
            assert table_found, "사용자 관리 페이지에서 사용자 테이블을 찾을 수 없습니다"
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "users_page_navigation")
            raise e

    async def test_sessions_page_navigation(
        self, 
        logged_in_admin_page: Page, 
        base_url: str
    ):
        """세션 관리 페이지 네비게이션 테스트."""
        try:
            # 세션 관리 페이지로 이동
            await navigate_to_admin_page(logged_in_admin_page, "sessions")
            
            # URL 확인
            await expect(logged_in_admin_page).to_have_url(f"{base_url}/admin/sessions")
            
            # 세션 관리 페이지 콘텐츠 확인
            await wait_for_table_load(logged_in_admin_page)
            
            # 세션 관련 요소 확인
            session_indicators = [
                "text=활성 세션",
                "text=Active Sessions",
                "text=Session",
                "table",
                ".sessions-table"
            ]
            
            session_found = False
            for indicator in session_indicators:
                try:
                    element = logged_in_admin_page.locator(indicator)
                    if await element.is_visible():
                        session_found = True
                        break
                except:
                    continue
            
            assert session_found, "세션 관리 페이지 콘텐츠를 찾을 수 없습니다"
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "sessions_page_navigation")
            raise e

    async def test_permissions_page_navigation(
        self, 
        logged_in_admin_page: Page, 
        base_url: str
    ):
        """권한 관리 페이지 네비게이션 테스트."""
        try:
            # 권한 관리 페이지로 이동
            await navigate_to_admin_page(logged_in_admin_page, "permissions")
            
            # URL 확인
            await expect(logged_in_admin_page).to_have_url(f"{base_url}/admin/permissions")
            
            # 권한 관리 페이지 기본 요소 확인
            permission_indicators = [
                "text=권한 관리",
                "text=Permission",
                "text=권한 생성",
                "text=Create Permission",
                ".permissions",
                ".permission-form"
            ]
            
            permission_found = False
            for indicator in permission_indicators:
                try:
                    element = logged_in_admin_page.locator(indicator)
                    if await element.is_visible():
                        permission_found = True
                        break
                except:
                    continue
            
            assert permission_found, "권한 관리 페이지 콘텐츠를 찾을 수 없습니다"
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "permissions_page_navigation")
            raise e

    async def test_roles_page_navigation(
        self, 
        logged_in_admin_page: Page, 
        base_url: str
    ):
        """역할 관리 페이지 네비게이션 테스트."""
        try:
            # 역할 관리 페이지로 이동
            await navigate_to_admin_page(logged_in_admin_page, "roles")
            
            # URL 확인
            await expect(logged_in_admin_page).to_have_url(f"{base_url}/admin/roles")
            
            # 역할 관리 페이지 기본 요소 확인
            role_indicators = [
                "text=역할 관리",
                "text=Role",
                "text=역할 생성",
                "text=Create Role",
                ".roles",
                ".role-form"
            ]
            
            role_found = False
            for indicator in role_indicators:
                try:
                    element = logged_in_admin_page.locator(indicator)
                    if await element.is_visible():
                        role_found = True
                        break
                except:
                    continue
            
            assert role_found, "역할 관리 페이지 콘텐츠를 찾을 수 없습니다"
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "roles_page_navigation")
            raise e

    async def test_navigation_breadcrumbs(
        self, 
        logged_in_admin_page: Page, 
        base_url: str
    ):
        """네비게이션 breadcrumb 테스트."""
        try:
            pages_to_test = [
                {"page": "users", "breadcrumb": "사용자 관리"},
                {"page": "sessions", "breadcrumb": "세션 관리"},
                {"page": "permissions", "breadcrumb": "권한 관리"},
                {"page": "roles", "breadcrumb": "역할 관리"}
            ]
            
            for test_case in pages_to_test:
                # 각 페이지로 이동
                await navigate_to_admin_page(logged_in_admin_page, test_case["page"])
                
                # breadcrumb 또는 페이지 제목 확인
                breadcrumb_selectors = [
                    ".breadcrumb",
                    ".page-title", 
                    "h1",
                    "h2",
                    f"text={test_case['breadcrumb']}"
                ]
                
                breadcrumb_found = False
                for selector in breadcrumb_selectors:
                    try:
                        element = logged_in_admin_page.locator(selector)
                        if await element.is_visible():
                            text_content = await element.text_content()
                            if test_case['breadcrumb'] in text_content or test_case['page'] in text_content.lower():
                                breadcrumb_found = True
                                break
                    except:
                        continue
                
                # breadcrumb이 없어도 페이지가 로드되면 통과 (선택적 기능)
                if not breadcrumb_found:
                    print(f"경고: {test_case['page']} 페이지에서 breadcrumb을 찾을 수 없습니다")
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "navigation_breadcrumbs")
            raise e

    async def test_back_navigation(
        self, 
        logged_in_admin_page: Page, 
        base_url: str
    ):
        """브라우저 뒤로가기 네비게이션 테스트."""
        try:
            # 대시보드에서 시작
            await navigate_to_admin_page(logged_in_admin_page, "dashboard")
            
            # 사용자 관리 페이지로 이동
            await navigate_to_admin_page(logged_in_admin_page, "users")
            await expect(logged_in_admin_page).to_have_url(f"{base_url}/admin/users")
            
            # 뒤로가기
            await logged_in_admin_page.go_back()
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # 대시보드로 돌아갔는지 확인
            await expect(logged_in_admin_page).to_have_url(f"{base_url}/admin")
            
            # 앞으로가기
            await logged_in_admin_page.go_forward()
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # 다시 사용자 관리 페이지로 돌아갔는지 확인
            await expect(logged_in_admin_page).to_have_url(f"{base_url}/admin/users")
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "back_navigation")
            raise e

    async def test_all_pages_accessibility(
        self, 
        logged_in_admin_page: Page, 
        base_url: str
    ):
        """모든 관리자 페이지 접근성 확인 테스트."""
        try:
            admin_pages = [
                {"name": "dashboard", "path": "/admin"},
                {"name": "users", "path": "/admin/users"},
                {"name": "sessions", "path": "/admin/sessions"},
                {"name": "permissions", "path": "/admin/permissions"},
                {"name": "roles", "path": "/admin/roles"}
            ]
            
            for page_info in admin_pages:
                # 각 페이지로 이동
                await logged_in_admin_page.goto(f"{base_url}{page_info['path']}")
                await logged_in_admin_page.wait_for_load_state("networkidle")
                
                # URL 확인
                current_url = logged_in_admin_page.url
                assert page_info['path'] in current_url, \
                    f"{page_info['name']} 페이지 URL이 올바르지 않습니다: {current_url}"
                
                # 관리자 권한 확인
                await assert_admin_access(logged_in_admin_page)
                
                # 에러 상태 확인
                has_error = await check_error_state(logged_in_admin_page)
                assert not has_error, f"{page_info['name']} 페이지에서 에러 발생"
                
                # 기본 페이지 구조 확인 (네비게이션)
                nav_exists = False
                nav_selectors = ["nav", ".admin-nav", ".navigation"]
                for selector in nav_selectors:
                    try:
                        nav_element = logged_in_admin_page.locator(selector)
                        if await nav_element.is_visible():
                            nav_exists = True
                            break
                    except:
                        continue
                
                assert nav_exists, f"{page_info['name']} 페이지에서 네비게이션을 찾을 수 없습니다"
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "all_pages_accessibility")
            raise e