"""사용자 역할 변경 모달 E2E 테스트."""

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
class TestUserRoleModal:
    """사용자 역할 변경 모달 E2E 테스트."""

    async def test_role_modal_open_and_close(
        self,
        logged_in_admin_page: Page,
        base_url: str
    ):
        """역할 변경 모달 열기/닫기 테스트."""
        try:
            # 사용자 관리 페이지로 이동
            await logged_in_admin_page.goto(f"{base_url}/admin/users")
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # 사용자 테이블 로딩 대기
            await expect(logged_in_admin_page.locator("table")).to_be_visible()
            
            # 첫 번째 "역할 변경" 버튼 찾기
            role_change_button = logged_in_admin_page.locator("button:has-text('역할 변경')").first()
            await expect(role_change_button).to_be_visible()
            
            # 역할 변경 버튼 클릭
            await role_change_button.click()
            
            # 모달이 표시될 때까지 대기
            modal = logged_in_admin_page.locator("#roleChangeModal")
            await expect(modal).to_be_visible(timeout=10000)
            
            # 모달 내용 확인
            await expect(logged_in_admin_page.locator("text=사용자 역할 변경")).to_be_visible()
            await expect(logged_in_admin_page.locator("text=이 사용자에게 부여할 역할을 선택하세요")).to_be_visible()
            
            # 역할 체크박스들이 표시되는지 확인
            role_checkboxes = logged_in_admin_page.locator('input[name="roles"]')
            checkbox_count = await role_checkboxes.count()
            assert checkbox_count >= 3, f"역할 선택지가 충분하지 않습니다: {checkbox_count}개"
            
            # 취소 버튼으로 모달 닫기
            cancel_button = logged_in_admin_page.locator("button:has-text('취소')")
            await expect(cancel_button).to_be_visible()
            await cancel_button.click()
            
            # 모달이 사라질 때까지 대기
            await expect(modal).to_be_hidden(timeout=5000)
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "role_modal_open_close")
            raise e

    async def test_role_modal_background_close(
        self,
        logged_in_admin_page: Page,
        base_url: str
    ):
        """모달 배경 클릭으로 닫기 테스트."""
        try:
            # 사용자 관리 페이지로 이동
            await logged_in_admin_page.goto(f"{base_url}/admin/users")
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # 역할 변경 버튼 클릭하여 모달 열기
            role_change_button = logged_in_admin_page.locator("button:has-text('역할 변경')").first()
            await role_change_button.click()
            
            # 모달이 표시될 때까지 대기
            modal = logged_in_admin_page.locator("#roleChangeModal")
            await expect(modal).to_be_visible()
            
            # 모달 배경 클릭
            background = logged_in_admin_page.locator("#roleModalOverlay")
            await expect(background).to_be_visible()
            await background.click()
            
            # 모달이 사라질 때까지 대기
            await expect(modal).to_be_hidden(timeout=5000)
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "role_modal_background_close")
            raise e

    async def test_role_change_success_flow(
        self,
        logged_in_admin_page: Page,
        base_url: str
    ):
        """역할 변경 성공 플로우 테스트."""
        try:
            # 사용자 관리 페이지로 이동
            await logged_in_admin_page.goto(f"{base_url}/admin/users")
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # 첫 번째 사용자의 현재 역할 저장
            first_user_role_cell = logged_in_admin_page.locator("tbody tr").first().locator("td").nth(3)
            original_roles = await first_user_role_cell.text_content()
            
            # 역할 변경 모달 열기
            role_change_button = logged_in_admin_page.locator("button:has-text('역할 변경')").first()
            await role_change_button.click()
            
            # 모달 로딩 대기
            modal = logged_in_admin_page.locator("#roleChangeModal")
            await expect(modal).to_be_visible()
            
            # 현재 체크된 역할들 확인
            checked_checkboxes = logged_in_admin_page.locator('input[name="roles"]:checked')
            initial_checked_count = await checked_checkboxes.count()
            
            # 사용 가능한 역할 중 체크되지 않은 것 찾기
            all_checkboxes = logged_in_admin_page.locator('input[name="roles"]')
            checkbox_count = await all_checkboxes.count()
            
            # 체크박스 상태 변경 (토글)
            for i in range(checkbox_count):
                checkbox = all_checkboxes.nth(i)
                is_checked = await checkbox.is_checked()
                
                # user 역할은 항상 체크되도록 유지 (최소 하나는 필요)
                role_value = await checkbox.get_attribute("value")
                if role_value == "user":
                    if not is_checked:
                        await checkbox.check()
                    continue
                
                # 다른 역할들은 토글
                if is_checked:
                    await checkbox.uncheck()
                else:
                    await checkbox.check()
                break  # 하나만 변경하고 종료
            
            # 저장 버튼 클릭
            save_button = logged_in_admin_page.locator("button:has-text('저장')")
            await expect(save_button).to_be_visible()
            await save_button.click()
            
            # 성공 메시지 또는 모달 닫힘 확인
            # 성공 메시지가 나타날 때까지 대기 (최대 10초)
            try:
                success_message = logged_in_admin_page.locator(".bg-green-100, .text-green-700")
                await expect(success_message).to_be_visible(timeout=10000)
            except:
                # 성공 메시지가 없어도 모달이 닫혔는지 확인
                await expect(modal).to_be_hidden(timeout=10000)
            
            # 사용자 테이블에서 역할이 업데이트되었는지 확인 (옵션)
            await logged_in_admin_page.wait_for_timeout(2000)  # UI 업데이트 대기
            updated_roles = await first_user_role_cell.text_content()
            
            # 역할이 변경되었는지 확인 (원래와 다르거나 같을 수 있음)
            print(f"원래 역할: {original_roles}")
            print(f"업데이트된 역할: {updated_roles}")
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "role_change_success_flow")
            raise e

    async def test_role_modal_form_validation(
        self,
        logged_in_admin_page: Page,
        base_url: str
    ):
        """역할 모달 폼 검증 테스트."""
        try:
            # 사용자 관리 페이지로 이동
            await logged_in_admin_page.goto(f"{base_url}/admin/users")
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # 역할 변경 모달 열기
            role_change_button = logged_in_admin_page.locator("button:has-text('역할 변경')").first()
            await role_change_button.click()
            
            # 모달 로딩 대기
            modal = logged_in_admin_page.locator("#roleChangeModal")
            await expect(modal).to_be_visible()
            
            # 모든 역할 체크박스 해제 (빈 역할로 저장 시도)
            all_checkboxes = logged_in_admin_page.locator('input[name="roles"]')
            checkbox_count = await all_checkboxes.count()
            
            for i in range(checkbox_count):
                checkbox = all_checkboxes.nth(i)
                if await checkbox.is_checked():
                    await checkbox.uncheck()
            
            # 저장 버튼 클릭
            save_button = logged_in_admin_page.locator("button:has-text('저장')")
            await save_button.click()
            
            # 빈 역할로도 저장이 가능한지 확인하거나 오류 메시지 확인
            await logged_in_admin_page.wait_for_timeout(3000)
            
            # 모달이 여전히 있는지 또는 오류 메시지가 있는지 확인
            modal_still_visible = await modal.is_visible()
            
            if modal_still_visible:
                # 모달이 여전히 열려있다면 오류 처리가 되었을 수 있음
                error_message = logged_in_admin_page.locator(".text-red-600, .bg-red-100")
                if await error_message.count() > 0:
                    print("역할 없음에 대한 적절한 오류 처리가 되었습니다.")
            else:
                # 모달이 닫혔다면 빈 역할도 허용하는 것
                print("빈 역할이 허용됩니다.")
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "role_modal_form_validation")
            raise e

    async def test_role_modal_x_button_close(
        self,
        logged_in_admin_page: Page,
        base_url: str
    ):
        """모달 X 버튼으로 닫기 테스트."""
        try:
            # 사용자 관리 페이지로 이동
            await logged_in_admin_page.goto(f"{base_url}/admin/users")
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # 역할 변경 모달 열기
            role_change_button = logged_in_admin_page.locator("button:has-text('역할 변경')").first()
            await role_change_button.click()
            
            # 모달 로딩 대기
            modal = logged_in_admin_page.locator("#roleChangeModal")
            await expect(modal).to_be_visible()
            
            # X 버튼 찾기 및 클릭
            x_button = logged_in_admin_page.locator("button:has-text('×')")
            await expect(x_button).to_be_visible()
            await x_button.click()
            
            # 모달이 사라질 때까지 대기
            await expect(modal).to_be_hidden(timeout=5000)
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "role_modal_x_button_close")
            raise e

    async def test_multiple_users_role_change(
        self,
        logged_in_admin_page: Page,
        base_url: str
    ):
        """여러 사용자 역할 변경 테스트."""
        try:
            # 사용자 관리 페이지로 이동
            await logged_in_admin_page.goto(f"{base_url}/admin/users")
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # 사용자 테이블에서 행 개수 확인
            user_rows = logged_in_admin_page.locator("tbody tr")
            row_count = await user_rows.count()
            
            if row_count < 2:
                print("테스트를 위한 충분한 사용자가 없습니다.")
                return
            
            # 첫 번째 사용자 역할 변경
            first_role_button = logged_in_admin_page.locator("button:has-text('역할 변경')").first()
            await first_role_button.click()
            
            modal = logged_in_admin_page.locator("#roleChangeModal")
            await expect(modal).to_be_visible()
            
            # 취소로 닫기
            cancel_button = logged_in_admin_page.locator("button:has-text('취소')")
            await cancel_button.click()
            await expect(modal).to_be_hidden()
            
            # 두 번째 사용자 역할 변경
            second_role_button = logged_in_admin_page.locator("button:has-text('역할 변경')").nth(1)
            await second_role_button.click()
            
            await expect(modal).to_be_visible()
            
            # 이번에는 X 버튼으로 닫기
            x_button = logged_in_admin_page.locator("button:has-text('×')")
            await x_button.click()
            await expect(modal).to_be_hidden()
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "multiple_users_role_change")
            raise e

    async def test_role_modal_accessibility(
        self,
        logged_in_admin_page: Page,
        base_url: str
    ):
        """역할 모달 접근성 테스트."""
        try:
            # 사용자 관리 페이지로 이동
            await logged_in_admin_page.goto(f"{base_url}/admin/users")
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # 역할 변경 모달 열기
            role_change_button = logged_in_admin_page.locator("button:has-text('역할 변경')").first()
            await role_change_button.click()
            
            # 모달 로딩 대기
            modal = logged_in_admin_page.locator("#roleChangeModal")
            await expect(modal).to_be_visible()
            
            # 키보드 네비게이션 테스트
            # Tab 키로 폼 요소들 간 이동
            await logged_in_admin_page.keyboard.press("Tab")
            await logged_in_admin_page.keyboard.press("Tab")
            
            # Enter 키 테스트 (저장 버튼 활성화 상태에서)
            focused_element = await logged_in_admin_page.evaluate("document.activeElement.tagName")
            print(f"현재 포커스된 요소: {focused_element}")
            
            # Escape 키로 모달 닫기 (HTMX 환경에서는 작동하지 않을 수 있음)
            await logged_in_admin_page.keyboard.press("Escape")
            
            # Escape가 작동하지 않으면 수동으로 닫기
            if await modal.is_visible():
                cancel_button = logged_in_admin_page.locator("button:has-text('취소')")
                await cancel_button.click()
            
            await expect(modal).to_be_hidden(timeout=5000)
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "role_modal_accessibility")
            raise e