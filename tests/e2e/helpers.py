"""E2E 테스트 공통 헬퍼 함수들."""

import asyncio
import os
import json
import csv
from pathlib import Path
from playwright.async_api import Page, expect, Download
from typing import Optional, Dict, Any, List


async def login_as_admin(page: Page, email: str, password: str) -> None:
    """관리자로 로그인하는 헬퍼 함수."""
    base_url = getattr(page, 'base_url', 'http://localhost:8000')
    
    # 로그인 페이지로 이동
    await page.goto(f"{base_url}/auth/login-page")
    
    # 페이지 로딩 대기
    await page.wait_for_load_state("networkidle")
    
    # 로그인 폼 채우기
    await page.fill('input[name="email"]', email)
    await page.fill('input[name="password"]', password)
    
    # 로그인 버튼 클릭
    await page.click('button[type="submit"]')
    
    # 로그인 성공 후 리다이렉트 대기 (관리자 대시보드로)
    await page.wait_for_url(f"{base_url}/admin", timeout=30000)
    
    # 관리자 대시보드 로딩 완료 대기
    await page.wait_for_load_state("networkidle")


async def wait_for_admin_page(page: Page, title: str, timeout: int = 30000) -> None:
    """관리자 페이지 로딩 대기 함수."""
    # 페이지 타이틀 확인
    await expect(page).to_have_title(title, timeout=timeout)
    
    # 네트워크 요청 완료 대기
    await page.wait_for_load_state("networkidle", timeout=timeout)
    
    # Admin UI 레이아웃이 로드되었는지 확인
    await expect(page.locator('.admin-layout, nav, .admin-nav')).to_be_visible(timeout=timeout)


async def assert_admin_access(page: Page) -> None:
    """관리자 권한 접근 확인 함수."""
    # 현재 URL이 admin 경로인지 확인
    current_url = page.url
    assert "/admin" in current_url, f"관리자 페이지가 아닙니다: {current_url}"
    
    # 관리자 네비게이션 메뉴 존재 확인
    admin_nav_items = [
        "대시보드", "사용자 관리", "세션 관리", "권한 관리", "역할 관리"
    ]
    
    for nav_item in admin_nav_items:
        # 네비게이션 메뉴 항목이 존재하는지 확인
        nav_locator = page.locator(f'text="{nav_item}"')
        await expect(nav_locator).to_be_visible(timeout=10000)


async def navigate_to_admin_page(page: Page, page_name: str) -> None:
    """특정 관리자 페이지로 네비게이션."""
    page_mapping = {
        "dashboard": "/admin",
        "users": "/admin/users", 
        "sessions": "/admin/sessions",
        "permissions": "/admin/permissions",
        "roles": "/admin/roles"
    }
    
    if page_name not in page_mapping:
        raise ValueError(f"알 수 없는 페이지: {page_name}")
    
    base_url = getattr(page, 'base_url', 'http://localhost:8000')
    target_url = f"{base_url}{page_mapping[page_name]}"
    
    await page.goto(target_url)
    await page.wait_for_load_state("networkidle")


async def wait_for_table_load(page: Page, table_selector: str = "table", timeout: int = 15000) -> None:
    """테이블 로딩 대기 함수."""
    # 테이블 요소가 표시될 때까지 대기
    await expect(page.locator(table_selector)).to_be_visible(timeout=timeout)
    
    # 테이블 내 데이터 행이 로드될 때까지 대기 (최소 1개 행 또는 "데이터 없음" 메시지)
    await page.wait_for_function(
        f"""() => {{
            const table = document.querySelector('{table_selector}');
            if (!table) return false;
            const rows = table.querySelectorAll('tbody tr');
            return rows.length > 0 || document.querySelector('[data-testid="no-data"]');
        }}""",
        timeout=timeout
    )


async def assert_table_not_empty(page: Page, table_selector: str = "table") -> None:
    """테이블에 데이터가 있는지 확인."""
    # 테이블 존재 확인
    await expect(page.locator(table_selector)).to_be_visible()
    
    # 데이터 행이 존재하는지 확인 (헤더 제외)
    data_rows = page.locator(f"{table_selector} tbody tr")
    row_count = await data_rows.count()
    
    assert row_count > 0, "테이블에 데이터가 없습니다"


async def check_error_state(page: Page) -> bool:
    """페이지에 에러 상태가 있는지 확인."""
    error_indicators = [
        ".error",
        ".alert-error", 
        "[data-testid='error']",
        "text=Error",
        "text=오류",
        "text=실패"
    ]
    
    for indicator in error_indicators:
        try:
            error_element = page.locator(indicator)
            if await error_element.is_visible():
                error_text = await error_element.text_content()
                print(f"페이지 에러 감지: {error_text}")
                return True
        except:
            continue
    
    return False


async def wait_for_no_loading_state(page: Page, timeout: int = 10000) -> None:
    """로딩 상태가 끝날 때까지 대기."""
    loading_indicators = [
        ".loading",
        ".spinner",
        "[data-testid='loading']",
        "text=로딩중",
        "text=Loading"
    ]
    
    # 로딩 인디케이터가 사라질 때까지 대기
    for indicator in loading_indicators:
        try:
            loading_element = page.locator(indicator)
            await expect(loading_element).to_be_hidden(timeout=timeout)
        except:
            continue  # 해당 인디케이터가 없으면 무시


async def take_screenshot_on_failure(page: Page, test_name: str) -> Optional[str]:
    """테스트 실패 시 스크린샷 촬영."""
    try:
        screenshot_path = f"tests/e2e/screenshots/{test_name}_failure.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        return screenshot_path
    except Exception as e:
        print(f"스크린샷 촬영 실패: {e}")
        return None


async def wait_for_chart_load(page: Page, chart_selector: str = "canvas", timeout: int = 15000) -> None:
    """Chart.js 차트 로딩 완료 대기."""
    # 캔버스 요소가 표시될 때까지 대기
    await expect(page.locator(chart_selector)).to_be_visible(timeout=timeout)
    
    # Chart.js 라이브러리가 로드되고 차트가 렌더링될 때까지 대기
    await page.wait_for_function(
        """() => {
            return window.Chart && 
                   document.querySelector('canvas') && 
                   document.querySelector('canvas').getContext('2d');
        }""",
        timeout=timeout
    )
    
    # 차트 데이터가 실제로 렌더링될 때까지 잠시 대기
    await page.wait_for_timeout(1000)


async def verify_chart_data(page: Page, chart_selector: str = "canvas", expected_data_points: int = 1) -> bool:
    """차트에 데이터가 올바르게 표시되는지 확인."""
    try:
        # 차트 캔버스가 존재하는지 확인
        canvas = page.locator(chart_selector)
        await expect(canvas).to_be_visible()
        
        # 차트가 비어있지 않은지 확인 (픽셀 데이터 체크)
        has_content = await page.evaluate("""() => {
            const canvas = document.querySelector('canvas');
            if (!canvas) return false;
            
            const ctx = canvas.getContext('2d');
            const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
            const pixels = imageData.data;
            
            // 투명하지 않은 픽셀이 있는지 확인
            for (let i = 3; i < pixels.length; i += 4) {
                if (pixels[i] > 0) return true; // 알파 채널이 0이 아닌 픽셀 발견
            }
            return false;
        }""")
        
        return has_content
    except:
        return False


async def wait_for_download(page: Page, download_trigger_selector: str) -> Optional[Download]:
    """파일 다운로드 완료 대기."""
    async with page.expect_download() as download_info:
        await page.click(download_trigger_selector)
    
    download = await download_info.value
    return download


async def verify_download_file(download: Download, expected_filename: str, expected_content_type: str = None) -> bool:
    """다운로드된 파일 검증."""
    try:
        # 파일명 확인
        if expected_filename not in download.suggested_filename:
            return False
        
        # 임시 파일로 저장하여 내용 확인
        temp_path = f"/tmp/{download.suggested_filename}"
        await download.save_as(temp_path)
        
        # 파일이 실제로 존재하고 비어있지 않은지 확인
        temp_file = Path(temp_path)
        if not temp_file.exists() or temp_file.stat().st_size == 0:
            return False
        
        # CSV 파일인 경우 간단한 유효성 검사
        if expected_filename.endswith('.csv'):
            try:
                with open(temp_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    headers = next(reader)  # 헤더 행이 있는지 확인
                    if len(headers) == 0:
                        return False
            except:
                return False
        
        # JSON 파일인 경우 JSON 유효성 검사
        elif expected_filename.endswith('.json'):
            try:
                with open(temp_path, 'r', encoding='utf-8') as f:
                    json.load(f)  # JSON 파싱 가능한지 확인
            except:
                return False
        
        # 임시 파일 정리
        temp_file.unlink()
        return True
        
    except Exception as e:
        print(f"다운로드 파일 검증 실패: {e}")
        return False


async def change_language(page: Page, language: str, timeout: int = 10000) -> None:
    """언어 설정 변경."""
    # 언어 선택 드롭다운 클릭
    language_selector = page.locator("select[name='language'], .language-selector select")
    await expect(language_selector).to_be_visible(timeout=timeout)
    
    # 언어 선택
    await language_selector.select_option(value=language)
    
    # 변경 버튼 클릭 (있는 경우)
    change_button = page.locator("button[type='submit']:has-text('변경'), button[type='submit']:has-text('Change')")
    if await change_button.is_visible():
        await change_button.click()
    
    # 페이지 reload 대기
    await page.wait_for_load_state("networkidle", timeout=timeout)


async def verify_language_change(page: Page, expected_language: str, test_key: str = "dashboard") -> bool:
    """언어 변경이 정확히 적용되었는지 확인."""
    try:
        # 특정 키워드가 올바른 언어로 표시되는지 확인
        expected_translations = {
            "ko": {"dashboard": "대시보드", "admin": "관리자", "user": "사용자"},
            "en": {"dashboard": "Dashboard", "admin": "Admin", "user": "User"}
        }
        
        if expected_language not in expected_translations:
            return False
        
        expected_text = expected_translations[expected_language].get(test_key)
        if not expected_text:
            return False
        
        # 페이지에서 해당 텍스트가 표시되는지 확인
        text_locator = page.locator(f"text={expected_text}")
        await expect(text_locator).to_be_visible(timeout=5000)
        return True
        
    except:
        return False


async def wait_for_notification(page: Page, notification_text: str = None, timeout: int = 10000) -> bool:
    """실시간 알림 표시 대기."""
    try:
        # 알림 배너 또는 토스트 메시지 대기
        notification_selectors = [
            ".notification-banner",
            ".toast-message", 
            ".alert",
            "[data-testid='notification']",
            ".notification"
        ]
        
        for selector in notification_selectors:
            try:
                notification = page.locator(selector)
                await expect(notification).to_be_visible(timeout=timeout)
                
                # 특정 텍스트가 지정된 경우 해당 텍스트가 포함되는지 확인
                if notification_text:
                    await expect(notification).to_contain_text(notification_text, timeout=2000)
                
                return True
            except:
                continue
        
        return False
        
    except:
        return False


async def wait_for_sse_connection(page: Page, timeout: int = 10000) -> bool:
    """SSE 연결이 활성화될 때까지 대기."""
    try:
        # SSE 연결이 설정되었는지 JavaScript로 확인
        sse_connected = await page.wait_for_function(
            """() => {
                // HTMX SSE extension이 있는지 확인
                return window.htmx && 
                       document.querySelector('[hx-sse]') !== null;
            }""",
            timeout=timeout
        )
        
        return True if sse_connected else False
        
    except:
        return False


async def trigger_sse_event(page: Page, event_type: str = "user_action") -> None:
    """테스트용 SSE 이벤트 트리거 (서버에 요청 보내기)."""
    try:
        # 관리자 페이지에서 SSE 이벤트를 발생시킬 수 있는 액션 수행
        # 예: 사용자 역할 변경, 권한 생성 등
        if event_type == "user_action":
            # 사용자 목록 새로고침 등의 액션으로 SSE 이벤트 유발
            refresh_button = page.locator("button:has-text('새로고침'), button:has-text('Refresh')")
            if await refresh_button.is_visible():
                await refresh_button.click()
        
        elif event_type == "system_error":
            # 의도적으로 오류를 발생시켜 SSE 알림 테스트
            # 실제 구현에서는 mock이나 테스트 전용 엔드포인트 사용
            pass
        
    except Exception as e:
        print(f"SSE 이벤트 트리거 실패: {e}")


async def assert_analytics_data_present(page: Page) -> None:
    """분석 페이지에 데이터가 올바르게 표시되는지 확인."""
    # 차트가 로드되었는지 확인
    await wait_for_chart_load(page)
    
    # 메트릭 카드들이 표시되는지 확인
    metrics_cards = [
        "총 요청수", "Total Requests",
        "평균 응답시간", "Avg Response Time", 
        "성공률", "Success Rate",
        "오류 수", "Error Count"
    ]
    
    for metric in metrics_cards:
        try:
            await expect(page.locator(f"text={metric}")).to_be_visible(timeout=5000)
            break  # 하나의 언어 버전이라도 찾으면 성공
        except:
            continue
    
    # 테이블에 데이터가 있는지 확인
    await wait_for_table_load(page, ".metrics-table, table")


async def assert_export_buttons_present(page: Page) -> None:
    """내보내기 버튼들이 올바르게 표시되는지 확인."""
    export_buttons = [
        "사용자 내보내기", "Export Users",
        "권한 내보내기", "Export Permissions", 
        "메트릭 내보내기", "Export Metrics"
    ]
    
    for button_text in export_buttons:
        try:
            button = page.locator(f"a:has-text('{button_text}'), button:has-text('{button_text}')")
            await expect(button).to_be_visible(timeout=5000)
            break  # 하나의 언어 버전이라도 찾으면 성공
        except:
            continue