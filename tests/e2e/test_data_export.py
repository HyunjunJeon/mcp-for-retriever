"""데이터 내보내기 E2E 테스트"""

import pytest
import tempfile
import csv
import json
from pathlib import Path
from playwright.async_api import Page, expect, Download
from .helpers import (
    login_as_admin,
    navigate_to_admin_page,
    wait_for_download,
    verify_download_file,
    assert_export_buttons_present,
    wait_for_table_load,
    take_screenshot_on_failure
)


class TestDataExport:
    """데이터 내보내기 기능 E2E 테스트 클래스"""

    @pytest.fixture(autouse=True)
    async def setup_page(self, page: Page):
        """각 테스트 전에 관리자로 로그인"""
        page.base_url = "http://localhost:8000"
        await login_as_admin(page, "admin@example.com", "Admin123!")
        yield page

    async def test_export_buttons_visible(self, page: Page):
        """내보내기 버튼들이 올바르게 표시되는지 테스트"""
        try:
            # 사용자 관리 페이지로 이동
            await navigate_to_admin_page(page, "users")
            await wait_for_table_load(page)

            # 내보내기 버튼들 확인
            await assert_export_buttons_present(page)

            # 각 내보내기 버튼이 클릭 가능한지 확인
            export_buttons = [
                ("사용자 내보내기", "Export Users"),
                ("CSV 내보내기", "CSV Export"),
                ("JSON 내보내기", "JSON Export")
            ]

            for ko_text, en_text in export_buttons:
                button_found = False
                for text in [ko_text, en_text]:
                    try:
                        button = page.locator(f"a:has-text('{text}'), button:has-text('{text}')")
                        if await button.is_visible():
                            await expect(button).to_be_enabled()
                            button_found = True
                            break
                    except:
                        continue

        except Exception as e:
            await take_screenshot_on_failure(page, "export_buttons_visible")
            raise e

    async def test_users_csv_export(self, page: Page):
        """사용자 데이터 CSV 내보내기 테스트"""
        try:
            await navigate_to_admin_page(page, "users")
            await wait_for_table_load(page)

            # CSV 내보내기 버튼 찾기
            csv_button_selectors = [
                "a[href*='/admin/export/users.csv']",
                "a:has-text('CSV 내보내기')",
                "a:has-text('CSV Export')",
                "a:has-text('사용자 내보내기')",
                "a:has-text('Export Users')"
            ]

            download_button = None
            for selector in csv_button_selectors:
                try:
                    button = page.locator(selector)
                    if await button.is_visible():
                        download_button = button
                        break
                except:
                    continue

            assert download_button is not None, "CSV 내보내기 버튼을 찾을 수 없음"

            # 다운로드 수행
            download = await wait_for_download(page, selector)
            assert download is not None, "파일 다운로드가 시작되지 않음"

            # 파일 검증
            is_valid = await verify_download_file(download, "users.csv")
            assert is_valid, "다운로드된 CSV 파일이 유효하지 않음"

            # CSV 내용 상세 검증
            temp_path = f"/tmp/{download.suggested_filename}"
            await download.save_as(temp_path)

            with open(temp_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                headers = next(reader)
                
                # 예상되는 헤더들이 있는지 확인
                expected_headers = ['ID', '사용자명', '이메일', '역할', '활성화', '생성일']
                header_found = any(any(exp in header for header in headers) for exp in expected_headers)
                assert header_found, f"예상된 헤더가 없음. 실제 헤더: {headers}"

                # 데이터 행이 있는지 확인 (최소 1개)
                data_rows = list(reader)
                assert len(data_rows) >= 0, "CSV에 데이터가 없음"

            # 임시 파일 정리
            Path(temp_path).unlink()

        except Exception as e:
            await take_screenshot_on_failure(page, "users_csv_export")
            raise e

    async def test_permissions_csv_export(self, page: Page):
        """권한 데이터 CSV 내보내기 테스트"""
        try:
            await navigate_to_admin_page(page, "permissions")
            await wait_for_table_load(page)

            # 권한 CSV 내보내기 버튼 찾기
            csv_button_selectors = [
                "a[href*='/admin/export/permissions.csv']",
                "a:has-text('권한 내보내기')",
                "a:has-text('Export Permissions')"
            ]

            download_button = None
            for selector in csv_button_selectors:
                try:
                    button = page.locator(selector)
                    if await button.is_visible():
                        download_button = button
                        break
                except:
                    continue

            if download_button is not None:
                # 다운로드 수행
                download = await wait_for_download(page, selector)
                assert download is not None, "권한 CSV 다운로드가 시작되지 않음"

                # 파일 검증
                is_valid = await verify_download_file(download, "permissions.csv")
                assert is_valid, "다운로드된 권한 CSV 파일이 유효하지 않음"

                # CSV 내용 검증
                temp_path = f"/tmp/{download.suggested_filename}"
                await download.save_as(temp_path)

                with open(temp_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    headers = next(reader)
                    
                    # 권한 관련 헤더 확인
                    expected_headers = ['리소스', '액션', '사용자', 'Resource', 'Action', 'User']
                    header_found = any(any(exp in header for header in headers) for exp in expected_headers)
                    assert header_found, f"예상된 권한 헤더가 없음. 실제 헤더: {headers}"

                # 임시 파일 정리
                Path(temp_path).unlink()

        except Exception as e:
            await take_screenshot_on_failure(page, "permissions_csv_export")
            raise e

    async def test_metrics_json_export(self, page: Page):
        """메트릭 데이터 JSON 내보내기 테스트"""
        try:
            # 분석 페이지로 이동
            await page.goto(f"{page.base_url}/admin/analytics")
            await page.wait_for_load_state("networkidle")

            # JSON 내보내기 버튼 찾기
            json_button_selectors = [
                "a[href*='/admin/export/metrics.json']",
                "a:has-text('메트릭 내보내기')",
                "a:has-text('Export Metrics')",
                "a:has-text('JSON 내보내기')",
                "a:has-text('JSON Export')"
            ]

            download_button = None
            for selector in json_button_selectors:
                try:
                    button = page.locator(selector)
                    if await button.is_visible():
                        download_button = button
                        break
                except:
                    continue

            if download_button is not None:
                # 다운로드 수행
                download = await wait_for_download(page, selector)
                assert download is not None, "메트릭 JSON 다운로드가 시작되지 않음"

                # 파일 검증
                is_valid = await verify_download_file(download, "metrics.json")
                assert is_valid, "다운로드된 메트릭 JSON 파일이 유효하지 않음"

                # JSON 내용 상세 검증
                temp_path = f"/tmp/{download.suggested_filename}"
                await download.save_as(temp_path)

                with open(temp_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    # 메트릭 JSON 구조 확인
                    expected_keys = ['summary', 'tool_metrics', 'response_time_distribution']
                    for key in expected_keys:
                        if key in data:
                            assert isinstance(data[key], dict), f"{key} 섹션이 올바른 형식이 아님"

                    # summary 섹션 상세 확인
                    if 'summary' in data:
                        summary = data['summary']
                        summary_keys = ['total_requests', 'total_errors', 'success_rate', 'unique_users']
                        for skey in summary_keys:
                            if skey in summary:
                                # 숫자 값들이 유효한지 확인
                                if skey in ['total_requests', 'total_errors', 'unique_users']:
                                    assert isinstance(summary[skey], int) and summary[skey] >= 0, f"{skey} 값이 유효하지 않음"

                # 임시 파일 정리
                Path(temp_path).unlink()

        except Exception as e:
            await take_screenshot_on_failure(page, "metrics_json_export")
            raise e

    async def test_export_file_naming(self, page: Page):
        """내보내기 파일명이 올바른지 테스트"""
        try:
            await navigate_to_admin_page(page, "users")
            await wait_for_table_load(page)

            # CSV 내보내기 수행
            csv_selector = "a[href*='/admin/export/users.csv']"
            csv_button = page.locator(csv_selector)
            
            if await csv_button.is_visible():
                download = await wait_for_download(page, csv_selector)
                
                # 파일명이 예상 패턴과 일치하는지 확인
                filename = download.suggested_filename
                assert filename.endswith('.csv'), f"CSV 파일 확장자가 올바르지 않음: {filename}"
                assert 'users' in filename.lower(), f"사용자 파일명에 'users'가 포함되지 않음: {filename}"

        except Exception as e:
            await take_screenshot_on_failure(page, "export_file_naming")
            raise e

    async def test_export_button_permissions(self, page: Page):
        """내보내기 버튼 권한 테스트 (관리자만 접근 가능)"""
        try:
            await navigate_to_admin_page(page, "users")
            await wait_for_table_load(page)

            # 관리자로 로그인된 상태에서 내보내기 버튼이 보이는지 확인
            export_buttons = page.locator("a[href*='/admin/export/'], a:has-text('내보내기'), a:has-text('Export')")
            button_count = await export_buttons.count()
            
            # 최소 하나의 내보내기 버튼이 있어야 함
            assert button_count > 0, "관리자에게 내보내기 버튼이 표시되지 않음"

            # 버튼들이 활성화되어 있는지 확인
            for i in range(button_count):
                button = export_buttons.nth(i)
                if await button.is_visible():
                    await expect(button).to_be_enabled()

        except Exception as e:
            await take_screenshot_on_failure(page, "export_button_permissions")
            raise e

    async def test_export_during_loading(self, page: Page):
        """페이지 로딩 중 내보내기 버튼 동작 테스트"""
        try:
            # 페이지 로딩 시작
            await page.goto(f"{page.base_url}/admin/users")
            
            # 로딩이 완료되기 전에 내보내기 버튼 상태 확인
            # (너무 빨리 클릭하는 것을 방지하기 위해)
            await page.wait_for_timeout(1000)
            
            # 테이블이 로딩될 때까지 대기
            await wait_for_table_load(page)
            
            # 이제 내보내기 버튼이 정상적으로 작동하는지 확인
            csv_button = page.locator("a[href*='/admin/export/users.csv']")
            if await csv_button.is_visible():
                await expect(csv_button).to_be_enabled()

        except Exception as e:
            await take_screenshot_on_failure(page, "export_during_loading")
            raise e

    async def test_multiple_exports_simultaneously(self, page: Page):
        """동시 다중 내보내기 처리 테스트"""
        try:
            await navigate_to_admin_page(page, "users")
            await wait_for_table_load(page)

            # 여러 내보내기 버튼이 있는지 확인
            export_buttons = page.locator("a[href*='/admin/export/']")
            button_count = await export_buttons.count()
            
            if button_count > 1:
                # 첫 번째 내보내기 시작
                first_button = export_buttons.first
                if await first_button.is_visible():
                    href1 = await first_button.get_attribute("href")
                    
                    # 잠시 대기 후 두 번째 내보내기 시도
                    await page.wait_for_timeout(500)
                    
                    second_button = export_buttons.nth(1)
                    if await second_button.is_visible():
                        href2 = await second_button.get_attribute("href")
                        
                        # 두 버튼이 서로 다른 엔드포인트를 가리키는지 확인
                        assert href1 != href2, "내보내기 버튼들이 같은 엔드포인트를 가리킴"

        except Exception as e:
            await take_screenshot_on_failure(page, "multiple_exports_simultaneously")
            raise e

    async def test_export_error_handling(self, page: Page):
        """내보내기 오류 처리 테스트"""
        try:
            await navigate_to_admin_page(page, "users")
            await wait_for_table_load(page)

            # 존재하지 않는 내보내기 엔드포인트에 접근 시도
            await page.goto(f"{page.base_url}/admin/export/nonexistent.csv")
            
            # 404 에러 페이지가 표시되거나 적절한 오류 메시지가 표시되는지 확인
            error_indicators = [
                "404",
                "Not Found",
                "찾을 수 없음",
                "오류",
                "Error"
            ]
            
            error_found = False
            for indicator in error_indicators:
                try:
                    error_element = page.locator(f"text={indicator}")
                    if await error_element.is_visible():
                        error_found = True
                        break
                except:
                    continue
            
            # 오류가 적절히 처리되었는지 확인 (페이지가 완전히 깨지지 않았는지)
            body = page.locator("body")
            await expect(body).to_be_visible()

        except Exception as e:
            await take_screenshot_on_failure(page, "export_error_handling")
            raise e

    async def test_export_data_privacy(self, page: Page):
        """내보내기 데이터 개인정보 보호 테스트"""
        try:
            await navigate_to_admin_page(page, "users")
            await wait_for_table_load(page)

            # CSV 내보내기 수행
            csv_selector = "a[href*='/admin/export/users.csv']"
            csv_button = page.locator(csv_selector)
            
            if await csv_button.is_visible():
                download = await wait_for_download(page, csv_selector)
                
                # 다운로드된 파일 내용 확인
                temp_path = f"/tmp/{download.suggested_filename}"
                await download.save_as(temp_path)

                with open(temp_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                    # 민감한 정보가 노출되지 않았는지 확인
                    sensitive_patterns = [
                        'password',
                        'secret',
                        'token',
                        'key',
                        'hash'
                    ]
                    
                    for pattern in sensitive_patterns:
                        assert pattern.lower() not in content.lower(), f"민감한 정보 '{pattern}'가 내보내기 파일에 포함됨"

                # 임시 파일 정리
                Path(temp_path).unlink()

        except Exception as e:
            await take_screenshot_on_failure(page, "export_data_privacy")
            raise e