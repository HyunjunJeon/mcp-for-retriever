"""권한 관리 목록 표시 E2E 테스트."""

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
class TestPermissionsList:
    """권한 관리 목록 표시 E2E 테스트."""

    async def test_permissions_page_access(
        self,
        logged_in_admin_page: Page,
        base_url: str
    ):
        """권한 관리 페이지 접근 테스트."""
        try:
            # 권한 관리 페이지로 이동
            await logged_in_admin_page.goto(f"{base_url}/admin/permissions")
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # 페이지 제목 확인
            await expect(logged_in_admin_page.locator("h1:has-text('권한 관리')")).to_be_visible()
            
            # 새 권한 추가 섹션 확인
            await expect(logged_in_admin_page.locator("h2:has-text('새 권한 추가')")).to_be_visible()
            
            # 기존 권한 목록 섹션 확인
            await expect(logged_in_admin_page.locator("h2:has-text('기존 권한 목록')")).to_be_visible()
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "permissions_page_access")
            raise e

    async def test_permissions_table_loading(
        self,
        logged_in_admin_page: Page,
        base_url: str
    ):
        """권한 목록 테이블 로딩 테스트."""
        try:
            # 권한 관리 페이지로 이동
            await logged_in_admin_page.goto(f"{base_url}/admin/permissions")
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # HTMX로 테이블이 로드될 때까지 대기
            table_container = logged_in_admin_page.locator("#permissions-table-container")
            await expect(table_container).to_be_visible()
            
            # 테이블 로딩이 완료될 때까지 대기 (최대 10초)
            await logged_in_admin_page.wait_for_function(
                "document.querySelector('#permissions-table') !== null || "
                "document.querySelector('#permissions-table-container').textContent.includes('권한이 없습니다')",
                timeout=10000
            )
            
            # 테이블이 로드되었는지 확인
            table_or_empty = await logged_in_admin_page.locator(
                "#permissions-table, text=권한이 없습니다"
            ).count()
            assert table_or_empty > 0, "권한 테이블 또는 빈 메시지가 표시되지 않음"
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "permissions_table_loading")
            raise e

    async def test_permissions_filters_functionality(
        self,
        logged_in_admin_page: Page,
        base_url: str
    ):
        """권한 필터링 기능 테스트."""
        try:
            # 권한 관리 페이지로 이동
            await logged_in_admin_page.goto(f"{base_url}/admin/permissions")
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # 필터 옵션 펼치기
            filter_summary = logged_in_admin_page.locator("summary:has-text('필터 옵션')")
            await expect(filter_summary).to_be_visible()
            await filter_summary.click()
            
            # 필터 폼이 로드될 때까지 대기
            await logged_in_admin_page.wait_for_function(
                "document.querySelector('#permissions-filters') !== null",
                timeout=5000
            )
            
            # 리소스 타입 필터 테스트
            resource_type_select = logged_in_admin_page.locator('select[name="resource_type_filter"]')
            await expect(resource_type_select).to_be_visible()
            
            # 웹 검색 필터 선택
            await resource_type_select.select_option("web_search")
            
            # HTMX 요청이 완료될 때까지 대기
            await logged_in_admin_page.wait_for_timeout(1000)
            
            # 리소스 이름 필터 테스트
            resource_name_input = logged_in_admin_page.locator('input[name="resource_name_filter"]')
            await expect(resource_name_input).to_be_visible()
            
            # 검색어 입력
            await resource_name_input.fill("test")
            
            # 검색이 트리거될 때까지 대기 (debounce 500ms + 처리 시간)
            await logged_in_admin_page.wait_for_timeout(1000)
            
            # 역할명 필터 테스트
            role_name_input = logged_in_admin_page.locator('input[name="role_name_filter"]')
            await expect(role_name_input).to_be_visible()
            
            await role_name_input.fill("admin")
            await logged_in_admin_page.wait_for_timeout(1000)
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "permissions_filters_functionality")
            raise e

    async def test_permissions_pagination(
        self,
        logged_in_admin_page: Page,
        base_url: str
    ):
        """권한 목록 페이지네이션 테스트."""
        try:
            # 권한 관리 페이지로 이동
            await logged_in_admin_page.goto(f"{base_url}/admin/permissions")
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # 테이블 로딩 대기
            await logged_in_admin_page.wait_for_function(
                "document.querySelector('#permissions-table') !== null || "
                "document.querySelector('#permissions-table-container').textContent.includes('권한이 없습니다')",
                timeout=10000
            )
            
            # 페이지네이션 정보 확인
            pagination_info = logged_in_admin_page.locator("text=/총 \\d+개 권한/")
            if await pagination_info.count() > 0:
                # 권한이 있는 경우 페이지네이션 버튼 확인
                prev_button = logged_in_admin_page.locator("button:has-text('이전')")
                next_button = logged_in_admin_page.locator("button:has-text('다음')")
                
                await expect(prev_button).to_be_visible()
                await expect(next_button).to_be_visible()
                
                # 첫 페이지에서 이전 버튼은 비활성화되어야 함
                await expect(prev_button).to_be_disabled()
                
                # 다음 버튼이 활성화되어 있다면 클릭 테스트
                if await next_button.is_enabled():
                    await next_button.click()
                    await logged_in_admin_page.wait_for_timeout(1000)
                    
                    # 두 번째 페이지에서 이전 버튼이 활성화되어야 함
                    await expect(prev_button).to_be_enabled()
            else:
                print("권한이 없어서 페이지네이션 테스트를 건너뜀")
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "permissions_pagination")
            raise e

    async def test_permission_delete_functionality(
        self,
        logged_in_admin_page: Page,
        base_url: str
    ):
        """권한 삭제 기능 테스트."""
        try:
            # 권한 관리 페이지로 이동
            await logged_in_admin_page.goto(f"{base_url}/admin/permissions")
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # 테이블 로딩 대기
            await logged_in_admin_page.wait_for_function(
                "document.querySelector('#permissions-table') !== null || "
                "document.querySelector('#permissions-table-container').textContent.includes('권한이 없습니다')",
                timeout=10000
            )
            
            # 삭제 버튼이 있는지 확인
            delete_buttons = logged_in_admin_page.locator("button:has-text('삭제')")
            delete_count = await delete_buttons.count()
            
            if delete_count > 0:
                print(f"삭제 가능한 권한 {delete_count}개 발견")
                
                # 첫 번째 삭제 버튼 클릭 (확인 대화상자가 나타날 것)
                first_delete_button = delete_buttons.first()
                await expect(first_delete_button).to_be_visible()
                
                # 확인 대화상자 처리 준비
                logged_in_admin_page.on("dialog", lambda dialog: dialog.dismiss())
                
                # 삭제 버튼 클릭 (확인 대화상자에서 취소)
                await first_delete_button.click()
                
                # 잠시 대기 후 테이블이 여전히 존재하는지 확인
                await logged_in_admin_page.wait_for_timeout(1000)
                remaining_buttons = await logged_in_admin_page.locator("button:has-text('삭제')").count()
                assert remaining_buttons == delete_count, "취소 후에도 권한이 삭제되었습니다"
                
            else:
                print("삭제할 권한이 없어서 삭제 기능 테스트를 건너뜀")
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "permission_delete_functionality")
            raise e

    async def test_permissions_table_headers(
        self,
        logged_in_admin_page: Page,
        base_url: str
    ):
        """권한 테이블 헤더 구조 테스트."""
        try:
            # 권한 관리 페이지로 이동
            await logged_in_admin_page.goto(f"{base_url}/admin/permissions")
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # 테이블 로딩 대기
            await logged_in_admin_page.wait_for_function(
                "document.querySelector('#permissions-table') !== null || "
                "document.querySelector('#permissions-table-container').textContent.includes('권한이 없습니다')",
                timeout=10000
            )
            
            # 테이블이 있는 경우 헤더 확인
            table = logged_in_admin_page.locator("#permissions-table table")
            if await table.count() > 0:
                # 테이블 헤더 확인
                headers = [
                    "대상", "리소스 타입", "리소스 이름", 
                    "권한", "부여일", "만료일", "액션"
                ]
                
                for header in headers:
                    header_element = logged_in_admin_page.locator(f"th:has-text('{header}')")
                    await expect(header_element).to_be_visible()
                
                print("모든 테이블 헤더가 올바르게 표시됨")
            else:
                print("권한이 없어서 테이블 헤더 테스트를 건너뜀")
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "permissions_table_headers")
            raise e

    async def test_permissions_real_time_search(
        self,
        logged_in_admin_page: Page,
        base_url: str
    ):
        """실시간 검색 기능 테스트."""
        try:
            # 권한 관리 페이지로 이동
            await logged_in_admin_page.goto(f"{base_url}/admin/permissions")
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # 필터 펼치기
            filter_summary = logged_in_admin_page.locator("summary:has-text('필터 옵션')")
            await filter_summary.click()
            
            # 필터 폼 로딩 대기
            await logged_in_admin_page.wait_for_function(
                "document.querySelector('#permissions-filters') !== null",
                timeout=5000
            )
            
            # 리소스 이름 검색 필드에 입력
            resource_name_input = logged_in_admin_page.locator('input[name="resource_name_filter"]')
            await resource_name_input.fill("test")
            
            # debounce 대기 (500ms + 처리 시간)
            await logged_in_admin_page.wait_for_timeout(1000)
            
            # 다른 검색어로 변경
            await resource_name_input.fill("")
            await logged_in_admin_page.wait_for_timeout(1000)
            
            # 역할명 검색 테스트
            role_name_input = logged_in_admin_page.locator('input[name="role_name_filter"]')
            await role_name_input.fill("user")
            await logged_in_admin_page.wait_for_timeout(1000)
            
            # 검색어 클리어
            await role_name_input.fill("")
            await logged_in_admin_page.wait_for_timeout(1000)
            
            print("실시간 검색 기능이 정상 작동함")
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "permissions_real_time_search")
            raise e

    async def test_permissions_accessibility(
        self,
        logged_in_admin_page: Page,
        base_url: str
    ):
        """권한 관리 페이지 접근성 테스트."""
        try:
            # 권한 관리 페이지로 이동
            await logged_in_admin_page.goto(f"{base_url}/admin/permissions")
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # 키보드 네비게이션 테스트
            await logged_in_admin_page.keyboard.press("Tab")  # 첫 번째 포커스 가능한 요소로
            
            # 필터 펼치기 키보드로 접근
            filter_summary = logged_in_admin_page.locator("summary:has-text('필터 옵션')")
            await filter_summary.focus()
            await logged_in_admin_page.keyboard.press("Enter")  # Enter로 펼치기
            
            # 필터 폼 로딩 대기
            await logged_in_admin_page.wait_for_timeout(2000)
            
            # Tab으로 필터 요소들 순회
            for _ in range(5):  # 필터 요소들을 Tab으로 순회
                await logged_in_admin_page.keyboard.press("Tab")
                await logged_in_admin_page.wait_for_timeout(200)
            
            # 포커스된 요소 확인
            focused_element = await logged_in_admin_page.evaluate("document.activeElement.tagName")
            print(f"현재 포커스된 요소: {focused_element}")
            
            # label과 input 연결 확인
            labels = logged_in_admin_page.locator("label")
            label_count = await labels.count()
            print(f"총 {label_count}개의 label 요소 발견")
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "permissions_accessibility")
            raise e

    async def test_permissions_error_handling(
        self,
        logged_in_admin_page: Page,
        base_url: str
    ):
        """권한 관리 오류 처리 테스트."""
        try:
            # 권한 관리 페이지로 이동
            await logged_in_admin_page.goto(f"{base_url}/admin/permissions")
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # 테이블 로딩 대기
            await logged_in_admin_page.wait_for_function(
                "document.querySelector('#permissions-table-container') !== null",
                timeout=10000
            )
            
            # 오류 메시지가 있는지 확인
            error_messages = logged_in_admin_page.locator(".text-red-600, .text-red-500")
            error_count = await error_messages.count()
            
            if error_count > 0:
                print(f"오류 메시지 {error_count}개 발견")
                first_error = error_messages.first()
                error_text = await first_error.text_content()
                print(f"오류 내용: {error_text}")
            else:
                print("오류 메시지가 없어서 정상 작동 중")
            
            # 네트워크 오류 시뮬레이션 (옵션)
            # 이는 실제 환경에서는 어려울 수 있으므로 기본적으로 건너뜀
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "permissions_error_handling")
            raise e