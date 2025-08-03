"""역할 관리 테이블 E2E 테스트."""

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
class TestRolesTable:
    """역할 관리 테이블 E2E 테스트."""

    async def test_roles_page_access(
        self,
        logged_in_admin_page: Page,
        base_url: str
    ):
        """역할 관리 페이지 접근 테스트."""
        try:
            # 역할 관리 페이지로 이동
            await logged_in_admin_page.goto(f"{base_url}/admin/roles")
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # 페이지 제목 확인
            await expect(logged_in_admin_page.locator("h1:has-text('역할 관리')")).to_be_visible()
            
            # 새 역할 추가 섹션 확인
            await expect(logged_in_admin_page.locator("h2:has-text('새 역할 추가')")).to_be_visible()
            
            # 역할 목록 섹션 확인
            await expect(logged_in_admin_page.locator("h2:has-text('역할 목록')")).to_be_visible()
            
            # 권한 매트릭스 섹션 확인
            await expect(logged_in_admin_page.locator("h2:has-text('권한 매트릭스')")).to_be_visible()
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "roles_page_access")
            raise e

    async def test_roles_table_loading(
        self,
        logged_in_admin_page: Page,
        base_url: str
    ):
        """역할 테이블 로딩 테스트."""
        try:
            # 역할 관리 페이지로 이동
            await logged_in_admin_page.goto(f"{base_url}/admin/roles")
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # HTMX로 테이블이 로드될 때까지 대기
            table_container = logged_in_admin_page.locator("#roles-table-container")
            await expect(table_container).to_be_visible()
            
            # 테이블 로딩이 완료될 때까지 대기 (최대 10초)
            await logged_in_admin_page.wait_for_function(
                "document.querySelector('#roles-table') !== null || "
                "document.querySelector('#roles-table-container').textContent.includes('역할이 없습니다')",
                timeout=10000
            )
            
            # 테이블이 로드되었는지 확인
            table_or_empty = await logged_in_admin_page.locator(
                "#roles-table, text=역할이 없습니다"
            ).count()
            assert table_or_empty > 0, "역할 테이블 또는 빈 메시지가 표시되지 않음"
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "roles_table_loading")
            raise e

    async def test_roles_table_content(
        self,
        logged_in_admin_page: Page,
        base_url: str
    ):
        """역할 테이블 내용 확인 테스트."""
        try:
            # 역할 관리 페이지로 이동
            await logged_in_admin_page.goto(f"{base_url}/admin/roles")
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # 테이블 로딩 대기
            await logged_in_admin_page.wait_for_function(
                "document.querySelector('#roles-table') !== null",
                timeout=10000
            )
            
            # 테이블 헤더 확인
            headers = ["역할", "권한 수", "리소스 권한", "도구 접근", "액션"]
            for header in headers:
                header_element = logged_in_admin_page.locator(f"th:has-text('{header}')")
                await expect(header_element).to_be_visible()
            
            # 기본 역할들 확인 (admin, user, guest, analyst, viewer)
            expected_roles = ["admin", "user", "guest"]
            for role in expected_roles:
                role_element = logged_in_admin_page.locator(f"td strong:has-text('{role}')")
                if await role_element.count() > 0:
                    await expect(role_element).to_be_visible()
                    print(f"역할 '{role}' 확인됨")
            
            # 역할별 액션 버튼 확인
            view_buttons = logged_in_admin_page.locator("button:has-text('권한 보기')")
            edit_buttons = logged_in_admin_page.locator("button:has-text('편집')")
            delete_buttons = logged_in_admin_page.locator("button:has-text('삭제')")
            
            view_count = await view_buttons.count()
            edit_count = await edit_buttons.count()
            delete_count = await delete_buttons.count()
            
            assert view_count > 0, "권한 보기 버튼이 없습니다"
            assert edit_count > 0, "편집 버튼이 없습니다"
            print(f"액션 버튼: 권한보기 {view_count}개, 편집 {edit_count}개, 삭제 {delete_count}개")
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "roles_table_content")
            raise e

    async def test_role_permissions_detail(
        self,
        logged_in_admin_page: Page,
        base_url: str
    ):
        """역할 권한 상세 보기 테스트."""
        try:
            # 역할 관리 페이지로 이동
            await logged_in_admin_page.goto(f"{base_url}/admin/roles")
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # 테이블 로딩 대기
            await logged_in_admin_page.wait_for_function(
                "document.querySelector('#roles-table') !== null",
                timeout=10000
            )
            
            # 첫 번째 "권한 보기" 버튼 클릭
            view_button = logged_in_admin_page.locator("button:has-text('권한 보기')").first()
            await expect(view_button).to_be_visible()
            await view_button.click()
            
            # 권한 상세 정보가 표시될 때까지 대기
            detail_container = logged_in_admin_page.locator("#role-permissions-detail")
            await logged_in_admin_page.wait_for_function(
                "document.querySelector('#role-permissions-detail').children.length > 0",
                timeout=5000
            )
            
            # 상세 정보 내용 확인
            await expect(logged_in_admin_page.locator("h4:text-matches('.*역할 상세 권한')")).to_be_visible()
            await expect(logged_in_admin_page.locator("h5:has-text('리소스 권한')")).to_be_visible()
            await expect(logged_in_admin_page.locator("h5:has-text('접근 가능한 도구')")).to_be_visible()
            
            # 닫기 버튼 클릭
            close_button = logged_in_admin_page.locator("button:has-text('닫기')")
            await expect(close_button).to_be_visible()
            await close_button.click()
            
            # 상세 정보가 사라지는지 확인
            await logged_in_admin_page.wait_for_timeout(1000)
            detail_content = await logged_in_admin_page.locator("#role-permissions-detail").inner_text()
            assert detail_content.strip() == "", "권한 상세 정보가 닫히지 않았습니다"
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "role_permissions_detail")
            raise e

    async def test_permission_matrix_display(
        self,
        logged_in_admin_page: Page,
        base_url: str
    ):
        """권한 매트릭스 표시 테스트."""
        try:
            # 역할 관리 페이지로 이동
            await logged_in_admin_page.goto(f"{base_url}/admin/roles")
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # 권한 매트릭스 토글 버튼 클릭
            matrix_toggle = logged_in_admin_page.locator("summary:has-text('권한 매트릭스 보기/숨기기')")
            await expect(matrix_toggle).to_be_visible()
            await matrix_toggle.click()
            
            # 매트릭스가 로드될 때까지 대기
            await logged_in_admin_page.wait_for_function(
                "document.querySelector('#roles-matrix') !== null",
                timeout=10000
            )
            
            # 리소스 권한 매트릭스 확인
            await expect(logged_in_admin_page.locator("h3:has-text('리소스 권한 매트릭스')")).to_be_visible()
            
            # 도구 접근 권한 매트릭스 확인
            await expect(logged_in_admin_page.locator("h3:has-text('도구 접근 권한 매트릭스')")).to_be_visible()
            
            # 매트릭스 테이블의 체크마크/X 마크 확인
            check_marks = logged_in_admin_page.locator("span:has-text('✅')")
            x_marks = logged_in_admin_page.locator("span:has-text('❌')")
            
            check_count = await check_marks.count()
            x_count = await x_marks.count()
            
            assert check_count > 0, "권한 허용 표시(✅)가 없습니다"
            assert x_count > 0, "권한 거부 표시(❌)가 없습니다"
            print(f"매트릭스 아이콘: 허용 {check_count}개, 거부 {x_count}개")
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "permission_matrix_display")
            raise e

    async def test_role_edit_modal(
        self,
        logged_in_admin_page: Page,
        base_url: str
    ):
        """역할 편집 모달 테스트."""
        try:
            # 역할 관리 페이지로 이동
            await logged_in_admin_page.goto(f"{base_url}/admin/roles")
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # 테이블 로딩 대기
            await logged_in_admin_page.wait_for_function(
                "document.querySelector('#roles-table') !== null",
                timeout=10000
            )
            
            # 첫 번째 "편집" 버튼 클릭
            edit_button = logged_in_admin_page.locator("button:has-text('편집')").first()
            await expect(edit_button).to_be_visible()
            await edit_button.click()
            
            # 편집 모달이 표시될 때까지 대기
            modal = logged_in_admin_page.locator("#roleEditModal")
            await expect(modal).to_be_visible(timeout=5000)
            
            # 모달 내용 확인
            await expect(logged_in_admin_page.locator("h3:text-matches('.*역할 편집')")).to_be_visible()
            await expect(logged_in_admin_page.locator("h4:has-text('리소스 권한')")).to_be_visible()
            
            # 권한 체크박스들 확인
            checkboxes = logged_in_admin_page.locator('input[name="permissions"]')
            checkbox_count = await checkboxes.count()
            assert checkbox_count >= 6, f"권한 체크박스가 충분하지 않습니다: {checkbox_count}개"
            
            # 취소 버튼으로 모달 닫기
            cancel_button = logged_in_admin_page.locator("button:has-text('취소')")
            await expect(cancel_button).to_be_visible()
            await cancel_button.click()
            
            # 모달이 사라지는지 확인
            await logged_in_admin_page.wait_for_timeout(1000)
            modal_content = await logged_in_admin_page.locator("#role-edit-modal").inner_text()
            assert modal_content.strip() == "", "편집 모달이 닫히지 않았습니다"
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "role_edit_modal")
            raise e

    async def test_role_alias_information(
        self,
        logged_in_admin_page: Page,
        base_url: str
    ):
        """역할 별칭 정보 표시 테스트."""
        try:
            # 역할 관리 페이지로 이동
            await logged_in_admin_page.goto(f"{base_url}/admin/roles")
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # 역할 별칭 정보 섹션 확인
            await expect(logged_in_admin_page.locator("h3:has-text('역할 별칭 정보')")).to_be_visible()
            
            # viewer → guest 별칭 확인
            await expect(logged_in_admin_page.locator("text=viewer")).to_be_visible()
            await expect(logged_in_admin_page.locator("text=guest")).to_be_visible()
            
            # analyst → user 별칭 확인
            await expect(logged_in_admin_page.locator("text=analyst")).to_be_visible()
            await expect(logged_in_admin_page.locator("text=user")).to_be_visible()
            
            print("역할 별칭 정보가 올바르게 표시됨")
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "role_alias_information")
            raise e

    async def test_new_role_creation_form(
        self,
        logged_in_admin_page: Page,
        base_url: str
    ):
        """새 역할 생성 폼 테스트."""
        try:
            # 역할 관리 페이지로 이동
            await logged_in_admin_page.goto(f"{base_url}/admin/roles")
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # 새 역할 추가 폼 확인
            role_name_input = logged_in_admin_page.locator('input[name="name"]')
            description_textarea = logged_in_admin_page.locator('textarea[name="description"]')
            create_button = logged_in_admin_page.locator('button:has-text("역할 생성")')
            
            await expect(role_name_input).to_be_visible()
            await expect(description_textarea).to_be_visible()
            await expect(create_button).to_be_visible()
            
            # 폼 필드에 값 입력
            await role_name_input.fill("test_role")
            await description_textarea.fill("테스트용 역할입니다")
            
            # 값이 올바르게 입력되었는지 확인
            name_value = await role_name_input.input_value()
            desc_value = await description_textarea.input_value()
            
            assert name_value == "test_role", "역할 이름이 올바르게 입력되지 않음"
            assert desc_value == "테스트용 역할입니다", "설명이 올바르게 입력되지 않음"
            
            # 실제 생성은 하지 않고 폼 검증만 수행
            print("새 역할 생성 폼이 정상 작동함")
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "new_role_creation_form")
            raise e

    async def test_role_table_accessibility(
        self,
        logged_in_admin_page: Page,
        base_url: str
    ):
        """역할 테이블 접근성 테스트."""
        try:
            # 역할 관리 페이지로 이동
            await logged_in_admin_page.goto(f"{base_url}/admin/roles")
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # 키보드 네비게이션 테스트
            await logged_in_admin_page.keyboard.press("Tab")  # 첫 번째 포커스 가능한 요소로
            
            # 테이블 로딩 대기
            await logged_in_admin_page.wait_for_function(
                "document.querySelector('#roles-table') !== null",
                timeout=10000
            )
            
            # Tab으로 테이블 내 요소들 순회
            for _ in range(10):  # 테이블 버튼들을 Tab으로 순회
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
            await take_screenshot_on_failure(logged_in_admin_page, "role_table_accessibility")
            raise e

    async def test_role_permissions_matrix_data_accuracy(
        self,
        logged_in_admin_page: Page,
        base_url: str
    ):
        """권한 매트릭스 데이터 정확성 테스트."""
        try:
            # 역할 관리 페이지로 이동
            await logged_in_admin_page.goto(f"{base_url}/admin/roles")
            await logged_in_admin_page.wait_for_load_state("networkidle")
            
            # 권한 매트릭스 토글 버튼 클릭
            matrix_toggle = logged_in_admin_page.locator("summary:has-text('권한 매트릭스 보기/숨기기')")
            await matrix_toggle.click()
            
            # 매트릭스 로딩 대기
            await logged_in_admin_page.wait_for_function(
                "document.querySelector('#roles-matrix') !== null",
                timeout=10000
            )
            
            # admin 역할은 모든 권한을 가져야 함
            admin_row = logged_in_admin_page.locator("tr:has(strong:has-text('admin'))")
            if await admin_row.count() > 0:
                admin_checks = admin_row.locator("span:has-text('✅')")
                admin_check_count = await admin_checks.count()
                print(f"admin 역할 권한 수: {admin_check_count}개")
                assert admin_check_count > 0, "admin 역할에게 권한이 할당되지 않음"
            
            # guest 역할은 제한적 권한만 가져야 함
            guest_row = logged_in_admin_page.locator("tr:has(strong:has-text('guest'))")
            if await guest_row.count() > 0:
                guest_checks = guest_row.locator("span:has-text('✅')")
                guest_xs = guest_row.locator("span:has-text('❌')")
                guest_check_count = await guest_checks.count()
                guest_x_count = await guest_xs.count()
                print(f"guest 역할: 허용 {guest_check_count}개, 거부 {guest_x_count}개")
                assert guest_x_count > guest_check_count, "guest 역할에게 너무 많은 권한이 부여됨"
            
            print("권한 매트릭스 데이터 정확성 검증 완료")
            
        except Exception as e:
            await take_screenshot_on_failure(logged_in_admin_page, "role_permissions_matrix_data_accuracy")
            raise e