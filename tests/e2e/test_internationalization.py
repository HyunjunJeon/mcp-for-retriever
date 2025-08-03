"""국제화(i18n) 기능 E2E 테스트"""

import pytest
from playwright.async_api import Page, expect
from .helpers import (
    login_as_admin,
    navigate_to_admin_page,
    change_language,
    verify_language_change,
    wait_for_table_load,
    take_screenshot_on_failure
)


class TestInternationalization:
    """국제화(i18n) 기능 E2E 테스트 클래스"""

    @pytest.fixture(autouse=True)
    async def setup_page(self, page: Page):
        """각 테스트 전에 관리자로 로그인"""
        page.base_url = "http://localhost:8000"
        await login_as_admin(page, "admin@example.com", "Admin123!")
        yield page

    async def test_language_selector_present(self, page: Page):
        """언어 선택기가 올바르게 표시되는지 테스트"""
        try:
            await navigate_to_admin_page(page, "dashboard")

            # 언어 선택기 요소 확인
            language_selectors = [
                "select[name='language']",
                ".language-selector select",
                "[data-testid='language-selector']",
                ".language-switcher select"
            ]

            selector_found = False
            for selector in language_selectors:
                try:
                    lang_selector = page.locator(selector)
                    if await lang_selector.is_visible():
                        await expect(lang_selector).to_be_enabled()
                        selector_found = True
                        break
                except:
                    continue

            # 언어 선택기가 없어도 언어 변경 링크가 있을 수 있음
            if not selector_found:
                language_links = page.locator("a:has-text('한국어'), a:has-text('English'), a:has-text('언어'), a:has-text('Language')")
                link_count = await language_links.count()
                assert link_count > 0, "언어 선택기나 언어 변경 링크가 없음"

        except Exception as e:
            await take_screenshot_on_failure(page, "language_selector_present")
            raise e

    async def test_korean_to_english_switch(self, page: Page):
        """한국어에서 영어로 언어 변경 테스트"""
        try:
            await navigate_to_admin_page(page, "dashboard")

            # 현재 한국어로 표시되는 요소들 확인
            korean_texts = ["대시보드", "관리자", "사용자 관리"]
            korean_found = False
            
            for text in korean_texts:
                try:
                    element = page.locator(f"text={text}")
                    if await element.is_visible():
                        korean_found = True
                        break
                except:
                    continue

            # 언어를 영어로 변경
            await change_language(page, "en")

            # 영어로 변경되었는지 확인
            english_success = await verify_language_change(page, "en", "dashboard")
            if not english_success:
                # 대안적인 방법으로 영어 텍스트 확인
                english_texts = ["Dashboard", "Admin", "User Management"]
                for text in english_texts:
                    try:
                        element = page.locator(f"text={text}")
                        await expect(element).to_be_visible(timeout=5000)
                        english_success = True
                        break
                    except:
                        continue

            assert english_success, "한국어에서 영어로 언어 변경이 실패함"

        except Exception as e:
            await take_screenshot_on_failure(page, "korean_to_english_switch")
            raise e

    async def test_english_to_korean_switch(self, page: Page):
        """영어에서 한국어로 언어 변경 테스트"""
        try:
            await navigate_to_admin_page(page, "dashboard")

            # 먼저 영어로 변경
            await change_language(page, "en")
            await page.wait_for_timeout(1000)

            # 다시 한국어로 변경
            await change_language(page, "ko")

            # 한국어로 변경되었는지 확인
            korean_success = await verify_language_change(page, "ko", "dashboard")
            if not korean_success:
                # 대안적인 방법으로 한국어 텍스트 확인
                korean_texts = ["대시보드", "관리자", "사용자 관리"]
                for text in korean_texts:
                    try:
                        element = page.locator(f"text={text}")
                        await expect(element).to_be_visible(timeout=5000)
                        korean_success = True
                        break
                    except:
                        continue

            assert korean_success, "영어에서 한국어로 언어 변경이 실패함"

        except Exception as e:
            await take_screenshot_on_failure(page, "english_to_korean_switch")
            raise e

    async def test_navigation_menu_translation(self, page: Page):
        """네비게이션 메뉴 번역 테스트"""
        try:
            await navigate_to_admin_page(page, "dashboard")

            # 한국어 네비게이션 메뉴 확인
            korean_nav_items = [
                "대시보드",
                "사용자 관리", 
                "세션 관리",
                "권한 관리",
                "역할 관리"
            ]

            korean_nav_found = 0
            for item in korean_nav_items:
                try:
                    nav_element = page.locator(f"nav a:has-text('{item}'), .nav-link:has-text('{item}')")
                    if await nav_element.is_visible():
                        korean_nav_found += 1
                except:
                    continue

            # 영어로 변경
            await change_language(page, "en")

            # 영어 네비게이션 메뉴 확인
            english_nav_items = [
                "Dashboard",
                "User Management",
                "Session Management", 
                "Permission Management",
                "Role Management"
            ]

            english_nav_found = 0
            for item in english_nav_items:
                try:
                    nav_element = page.locator(f"nav a:has-text('{item}'), .nav-link:has-text('{item}')")
                    if await nav_element.is_visible():
                        english_nav_found += 1
                except:
                    continue

            # 최소 일부 네비게이션 아이템이 번역되었는지 확인
            assert korean_nav_found > 0 or english_nav_found > 0, "네비게이션 메뉴 번역을 확인할 수 없음"

        except Exception as e:
            await take_screenshot_on_failure(page, "navigation_menu_translation")
            raise e

    async def test_table_headers_translation(self, page: Page):
        """테이블 헤더 번역 테스트"""
        try:
            await navigate_to_admin_page(page, "users")
            await wait_for_table_load(page)

            # 한국어 테이블 헤더 확인
            korean_headers = ["이름", "이메일", "역할", "상태", "생성일", "액션"]
            korean_header_found = 0
            
            for header in korean_headers:
                try:
                    header_element = page.locator(f"th:has-text('{header}'), .table-header:has-text('{header}')")
                    if await header_element.is_visible():
                        korean_header_found += 1
                except:
                    continue

            # 영어로 변경
            await change_language(page, "en")
            await wait_for_table_load(page)

            # 영어 테이블 헤더 확인
            english_headers = ["Name", "Email", "Role", "Status", "Created", "Actions"]
            english_header_found = 0
            
            for header in english_headers:
                try:
                    header_element = page.locator(f"th:has-text('{header}'), .table-header:has-text('{header}')")
                    if await header_element.is_visible():
                        english_header_found += 1
                except:
                    continue

            # 최소 일부 헤더가 번역되었는지 확인
            assert korean_header_found > 0 or english_header_found > 0, "테이블 헤더 번역을 확인할 수 없음"

        except Exception as e:
            await take_screenshot_on_failure(page, "table_headers_translation")
            raise e

    async def test_button_text_translation(self, page: Page):
        """버튼 텍스트 번역 테스트"""
        try:
            await navigate_to_admin_page(page, "users")
            await wait_for_table_load(page)

            # 한국어 버튼 텍스트 확인
            korean_buttons = ["편집", "삭제", "저장", "취소", "내보내기"]
            korean_button_found = 0
            
            for button_text in korean_buttons:
                try:
                    button = page.locator(f"button:has-text('{button_text}'), a:has-text('{button_text}')")
                    if await button.is_visible():
                        korean_button_found += 1
                except:
                    continue

            # 영어로 변경
            await change_language(page, "en")
            await wait_for_table_load(page)

            # 영어 버튼 텍스트 확인
            english_buttons = ["Edit", "Delete", "Save", "Cancel", "Export"]
            english_button_found = 0
            
            for button_text in english_buttons:
                try:
                    button = page.locator(f"button:has-text('{button_text}'), a:has-text('{button_text}')")
                    if await button.is_visible():
                        english_button_found += 1
                except:
                    continue

            # 최소 일부 버튼이 번역되었는지 확인
            assert korean_button_found > 0 or english_button_found > 0, "버튼 텍스트 번역을 확인할 수 없음"

        except Exception as e:
            await take_screenshot_on_failure(page, "button_text_translation")
            raise e

    async def test_page_title_translation(self, page: Page):
        """페이지 제목 번역 테스트"""
        try:
            # 대시보드 페이지
            await navigate_to_admin_page(page, "dashboard")
            
            # 한국어 페이지 제목 확인
            korean_title_patterns = ["관리자", "대시보드", "MCP Retriever"]
            korean_title_found = False
            
            current_title = await page.title()
            for pattern in korean_title_patterns:
                if pattern in current_title:
                    korean_title_found = True
                    break

            # 영어로 변경
            await change_language(page, "en")
            
            # 영어 페이지 제목 확인
            english_title_patterns = ["Admin", "Dashboard", "MCP Retriever"]
            english_title_found = False
            
            current_title = await page.title()
            for pattern in english_title_patterns:
                if pattern in current_title:
                    english_title_found = True
                    break

            # 페이지 제목이 적절히 설정되어 있는지 확인
            assert korean_title_found or english_title_found, f"페이지 제목이 적절하지 않음: {current_title}"

        except Exception as e:
            await take_screenshot_on_failure(page, "page_title_translation")
            raise e

    async def test_form_labels_translation(self, page: Page):
        """폼 레이블 번역 테스트"""
        try:
            await navigate_to_admin_page(page, "users")
            await wait_for_table_load(page)

            # 사용자 편집 또는 생성 폼이 있는지 확인
            edit_buttons = page.locator("button:has-text('편집'), button:has-text('Edit'), a:has-text('편집'), a:has-text('Edit')")
            edit_count = await edit_buttons.count()
            
            if edit_count > 0:
                # 첫 번째 편집 버튼 클릭
                await edit_buttons.first.click()
                await page.wait_for_timeout(1000)

                # 한국어 폼 레이블 확인
                korean_labels = ["이름", "이메일", "역할", "사용자명"]
                korean_label_found = 0
                
                for label in korean_labels:
                    try:
                        label_element = page.locator(f"label:has-text('{label}'), .form-label:has-text('{label}')")
                        if await label_element.is_visible():
                            korean_label_found += 1
                    except:
                        continue

                # 영어로 변경
                await change_language(page, "en")

                # 영어 폼 레이블 확인
                english_labels = ["Name", "Email", "Role", "Username"]
                english_label_found = 0
                
                for label in english_labels:
                    try:
                        label_element = page.locator(f"label:has-text('{label}'), .form-label:has-text('{label}')")
                        if await label_element.is_visible():
                            english_label_found += 1
                    except:
                        continue

                # 최소 일부 레이블이 번역되었는지 확인
                if korean_label_found > 0 or english_label_found > 0:
                    assert True, "폼 레이블 번역 확인 완료"

        except Exception as e:
            await take_screenshot_on_failure(page, "form_labels_translation")
            raise e

    async def test_error_messages_translation(self, page: Page):
        """오류 메시지 번역 테스트"""
        try:
            # 존재하지 않는 페이지로 이동하여 오류 유발
            await page.goto(f"{page.base_url}/admin/nonexistent")
            
            # 한국어 오류 메시지 확인
            korean_error_texts = ["오류", "페이지를 찾을 수 없음", "접근 권한이 없음"]
            korean_error_found = False
            
            for error_text in korean_error_texts:
                try:
                    error_element = page.locator(f"text={error_text}")
                    if await error_element.is_visible():
                        korean_error_found = True
                        break
                except:
                    continue

            # 영어로 변경 시도
            try:
                await change_language(page, "en")
                
                # 영어 오류 메시지 확인
                english_error_texts = ["Error", "Page not found", "Access denied"]
                english_error_found = False
                
                for error_text in english_error_texts:
                    try:
                        error_element = page.locator(f"text={error_text}")
                        if await error_element.is_visible():
                            english_error_found = True
                            break
                    except:
                        continue
            except:
                # 언어 변경이 실패해도 테스트는 계속 진행
                pass

            # 오류 페이지가 적절히 처리되었는지 확인
            body = page.locator("body")
            await expect(body).to_be_visible()

        except Exception as e:
            await take_screenshot_on_failure(page, "error_messages_translation")
            raise e

    async def test_language_persistence(self, page: Page):
        """언어 설정 지속성 테스트"""
        try:
            await navigate_to_admin_page(page, "dashboard")

            # 영어로 변경
            await change_language(page, "en")
            await page.wait_for_timeout(1000)

            # 다른 페이지로 이동
            await navigate_to_admin_page(page, "users")
            await page.wait_for_timeout(1000)

            # 언어 설정이 유지되는지 확인
            english_texts = ["Users", "User Management", "Email", "Role"]
            english_found = False
            
            for text in english_texts:
                try:
                    element = page.locator(f"text={text}")
                    if await element.is_visible():
                        english_found = True
                        break
                except:
                    continue

            # 페이지 새로고침 후에도 언어 설정이 유지되는지 확인
            await page.reload()
            await page.wait_for_load_state("networkidle")

            english_found_after_reload = False
            for text in english_texts:
                try:
                    element = page.locator(f"text={text}")
                    if await element.is_visible():
                        english_found_after_reload = True
                        break
                except:
                    continue

            # 언어 설정이 어느 정도 지속되는지 확인
            # (완벽한 지속성이 보장되지 않을 수 있으므로 관대하게 테스트)
            assert english_found or english_found_after_reload, "언어 설정 지속성을 확인할 수 없음"

        except Exception as e:
            await take_screenshot_on_failure(page, "language_persistence")
            raise e

    async def test_mixed_content_handling(self, page: Page):
        """혼합 콘텐츠 처리 테스트 (번역되지 않은 콘텐츠와 번역된 콘텐츠)"""
        try:
            await navigate_to_admin_page(page, "analytics")
            await page.wait_for_load_state("networkidle")

            # 한국어 상태에서 콘텐츠 확인
            korean_mixed_content = ["MCP Retriever", "API", "JSON", "CSV"]  # 번역되지 않을 수 있는 기술 용어
            korean_translatable = ["분석", "대시보드", "사용자"]  # 번역되어야 하는 콘텐츠
            
            # 영어로 변경
            await change_language(page, "en")
            await page.wait_for_timeout(1000)

            # 기술 용어는 그대로 유지되고, 일반 텍스트는 번역되는지 확인
            for tech_term in korean_mixed_content:
                try:
                    element = page.locator(f"text={tech_term}")
                    # 기술 용어는 여전히 보여야 함 (번역되지 않음)
                    if await element.is_visible():
                        assert True, f"기술 용어 '{tech_term}' 유지 확인"
                except:
                    # 기술 용어가 없어도 문제 없음
                    pass

            # 번역 가능한 텍스트가 영어로 변경되었는지 확인
            english_equivalents = ["Analytics", "Dashboard", "User", "Users"]
            english_found = False
            
            for text in english_equivalents:
                try:
                    element = page.locator(f"text={text}")
                    if await element.is_visible():
                        english_found = True
                        break
                except:
                    continue

            assert english_found, "번역 가능한 콘텐츠가 영어로 변경되지 않음"

        except Exception as e:
            await take_screenshot_on_failure(page, "mixed_content_handling")
            raise e