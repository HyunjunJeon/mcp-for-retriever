"""Simple authentication test to verify the flow works."""

import pytest
from playwright.async_api import async_playwright
import uuid


@pytest.mark.asyncio
async def test_simple_auth_flow():
    """Simple test for registration and login"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        # Generate unique credentials
        test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
        test_password = "TestPass123"
        
        try:
            # Test registration
            await page.goto("http://localhost:8000/auth/register-page")
            await page.fill('input[name="email"]', test_email)
            await page.fill('input[name="password"]', test_password)
            await page.click('button[type="submit"]')
            
            # Wait for success message
            success_msg = await page.wait_for_selector('.success', timeout=5000)
            assert success_msg is not None
            print(f"✅ Registration successful for {test_email}")
            
            # Navigate to login
            await page.click('a[href="/auth/login-page"]')
            
            # Test login
            await page.fill('input[name="email"]', test_email)
            await page.fill('input[name="password"]', test_password)
            await page.click('button[type="submit"]')
            
            # Wait for token display
            token_info = await page.wait_for_selector('#tokenInfo', state='visible', timeout=5000)
            assert token_info is not None
            print("✅ Login successful, tokens displayed")
            
            # Test /auth/me
            await page.click('button:has-text("현재 사용자 정보 조회")')
            await page.wait_for_selector('text=사용자 정보:', timeout=5000)
            print("✅ User info retrieved successfully")
            
        finally:
            await browser.close()
            
    print("✅ All tests passed!")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_simple_auth_flow())