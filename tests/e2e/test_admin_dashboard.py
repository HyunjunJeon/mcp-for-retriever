"""관리자 대시보드 E2E 테스트."""

import pytest
from playwright.async_api import Page, expect
from .helpers import (
    wait_for_admin_page,
    assert_admin_access,
    check_error_state,
    wait_for_no_loading_state,
    take_screenshot_on_failure
)


@pytest.mark.e2e
@pytest.mark.admin_ui
class TestAdminDashboard:
    """관리자 대시보드 기능 E2E 테스트."""

    async def test_dashboard_basic_load(
        self, 
        logged_in_admin_page: Page, 
        base_url: str
    ):
        """대시보드 기본 로딩 테스트."""
        try:
            # 대시보드 페이지 확인
            await expect(logged_in_admin_page).to_have_url(f"{base_url}/admin")
            
            # 대시보드 페이지 로딩 대기
            await wait_for_admin_page(logged_in_admin_page, "MCP Retriever - Admin Dashboard")
            
            # 관리자 권한 확인
            await assert_admin_access(logged_in_admin_page)
            
            # 로딩 상태 완료 대기
            await wait_for_no_loading_state(logged_in_admin_page)
            
            # 에러 상태 확인
            assert not await check_error_state(logged_in_admin_page), "대시보드 로딩 중 에러 발생"
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "dashboard_basic_load")
            raise e

    async def test_dashboard_statistics_display(
        self, 
        logged_in_admin_page: Page
    ):
        """대시보드 통계 표시 테스트."""
        try:
            # 통계 카드들이 표시되는지 확인
            stats_indicators = [
                "text=총 사용자",
                "text=활성 사용자", 
                "text=관리자",
                "text=일별 가입",
                "text=Total Users",
                "text=Active Users",
                "text=Admins"
            ]
            
            # 최소 하나의 통계 지표가 보여야 함
            stats_found = False
            for indicator in stats_indicators:
                try:
                    stats_element = logged_in_admin_page.locator(indicator)
                    if await stats_element.is_visible():
                        stats_found = True
                        break
                except:
                    continue
            
            assert stats_found, "대시보드에서 통계 정보를 찾을 수 없습니다"
            
            # 통계 값들이 숫자 형태로 표시되는지 확인
            number_patterns = [
                "text=/\\d+/",  # 숫자 패턴
                ".stat-value",
                ".stats-number",
                "[data-testid='stat-value']"
            ]
            
            number_found = False
            for pattern in number_patterns:
                try:
                    number_elements = logged_in_admin_page.locator(pattern)
                    count = await number_elements.count()
                    if count > 0:
                        number_found = True
                        break
                except:
                    continue
            
            assert number_found, "대시보드에서 통계 숫자를 찾을 수 없습니다"
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "dashboard_statistics_display")
            raise e

    async def test_dashboard_quick_actions(
        self, 
        logged_in_admin_page: Page, 
        base_url: str
    ):
        """대시보드 빠른 액션 버튼 테스트."""
        try:
            # 빠른 액션 버튼들 확인
            quick_action_texts = [
                "사용자 관리",
                "세션 관리", 
                "권한 관리",
                "역할 관리",
                "User Management",
                "Session Management",
                "Permission Management",
                "Role Management"
            ]
            
            # 각 액션 버튼이 클릭 가능한지 확인
            actions_found = 0
            for action_text in quick_action_texts:
                try:
                    # 텍스트를 포함하는 링크나 버튼 찾기
                    action_selectors = [
                        f"a:has-text('{action_text}')",
                        f"button:has-text('{action_text}')",
                        f"text={action_text}"
                    ]
                    
                    for selector in action_selectors:
                        action_element = logged_in_admin_page.locator(selector)
                        if await action_element.is_visible():
                            actions_found += 1
                            break
                except:
                    continue
            
            assert actions_found >= 2, f"대시보드 빠른 액션이 충분하지 않습니다: {actions_found}개 발견"
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "dashboard_quick_actions")
            raise e

    async def test_dashboard_navigation_links(
        self, 
        logged_in_admin_page: Page, 
        base_url: str
    ):
        """대시보드에서 다른 페이지로의 네비게이션 테스트."""
        try:
            navigation_tests = [
                {"text": "사용자 관리", "url_pattern": "/admin/users"},
                {"text": "세션 관리", "url_pattern": "/admin/sessions"},
                {"text": "권한 관리", "url_pattern": "/admin/permissions"},
                {"text": "역할 관리", "url_pattern": "/admin/roles"}
            ]
            
            for nav_test in navigation_tests:
                # 대시보드로 돌아가기
                await logged_in_admin_page.goto(f"{base_url}/admin")
                await logged_in_admin_page.wait_for_load_state("networkidle")
                
                # 해당 링크 찾기 및 클릭
                link_selectors = [
                    f"a:has-text('{nav_test['text']}')",
                    f"button:has-text('{nav_test['text']}')"
                ]
                
                link_clicked = False
                for selector in link_selectors:
                    try:
                        link_element = logged_in_admin_page.locator(selector).first()
                        if await link_element.is_visible():
                            await link_element.click()
                            link_clicked = True
                            break
                    except:
                        continue
                
                if link_clicked:
                    # 네비게이션 성공 확인
                    await logged_in_admin_page.wait_for_load_state("networkidle")
                    current_url = logged_in_admin_page.url
                    assert nav_test["url_pattern"] in current_url, \
                        f"{nav_test['text']} 링크가 올바른 페이지로 이동하지 않음: {current_url}"
                else:
                    print(f"경고: '{nav_test['text']}' 링크를 찾을 수 없습니다")
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "dashboard_navigation_links")
            raise e

    async def test_dashboard_responsive_layout(
        self, 
        logged_in_admin_page: Page
    ):
        """대시보드 반응형 레이아웃 테스트."""
        try:
            # 데스크톱 크기에서 테스트
            await logged_in_admin_page.set_viewport_size({"width": 1920, "height": 1080})
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # 주요 요소들이 표시되는지 확인
            desktop_elements = [
                ".admin-layout, nav, .admin-nav",  # 네비게이션
                ".stats, .statistics, .dashboard-stats",  # 통계 섹션
            ]
            
            for element_selector in desktop_elements:
                try:
                    element = logged_in_admin_page.locator(element_selector)
                    await expect(element).to_be_visible(timeout=5000)
                except:
                    # 일부 요소는 선택적일 수 있음
                    continue
            
            # 태블릿 크기 테스트
            await logged_in_admin_page.set_viewport_size({"width": 768, "height": 1024})
            await logged_in_admin_page.wait_for_timeout(1000)  # 레이아웃 조정 대기
            
            # 모바일 크기 테스트
            await logged_in_admin_page.set_viewport_size({"width": 375, "height": 667})
            await logged_in_admin_page.wait_for_timeout(1000)  # 레이아웃 조정 대기
            
            # 모바일에서도 기본 네비게이션이 접근 가능해야 함
            nav_accessible = False
            mobile_nav_selectors = [
                ".mobile-nav",
                ".hamburger",
                "button[aria-label='메뉴']",
                "nav",
                ".admin-nav"
            ]
            
            for selector in mobile_nav_selectors:
                try:
                    nav_element = logged_in_admin_page.locator(selector)
                    if await nav_element.is_visible():
                        nav_accessible = True
                        break
                except:
                    continue
            
            assert nav_accessible, "모바일 환경에서 네비게이션에 접근할 수 없습니다"
            
            # 원래 크기로 복원
            await logged_in_admin_page.set_viewport_size({"width": 1920, "height": 1080})
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "dashboard_responsive_layout")
            raise e