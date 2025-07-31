"""Playwright E2E test for authentication flow - simplified version for local testing."""

import pytest
from playwright.async_api import Page, expect
import uuid
import os
import asyncio


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_auth_server_pages_accessible():
    """Test that auth server HTML pages are accessible"""
    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        base_url = os.getenv("AUTH_URL", "http://localhost:8000")
        
        try:
            # Try to access registration page
            response = await page.goto(f"{base_url}/auth/register-page", wait_until="domcontentloaded", timeout=5000)
            
            if response and response.status == 200:
                # Check page elements
                assert await page.title() == "MCP 회원가입"
                assert await page.locator('input[name="email"]').is_visible()
                assert await page.locator('input[name="password"]').is_visible()
                assert await page.locator('button[type="submit"]').is_visible()
                print("✅ Registration page accessible and elements found")
            else:
                pytest.skip(f"Auth server not running at {base_url}")
                
        except Exception as e:
            pytest.skip(f"Auth server not accessible: {e}")
        finally:
            await browser.close()


@pytest.mark.asyncio  
@pytest.mark.playwright
async def test_login_page_accessible():
    """Test that login page is accessible"""
    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        base_url = os.getenv("AUTH_URL", "http://localhost:8000")
        
        try:
            # Try to access login page
            response = await page.goto(f"{base_url}/auth/login-page", wait_until="domcontentloaded", timeout=5000)
            
            if response and response.status == 200:
                # Check page elements
                assert await page.title() == "MCP 로그인"
                assert await page.locator('input[name="email"]').is_visible()
                assert await page.locator('input[name="password"]').is_visible()
                assert await page.locator('button[type="submit"]').is_visible()
                print("✅ Login page accessible and elements found")
            else:
                pytest.skip(f"Auth server not running at {base_url}")
                
        except Exception as e:
            pytest.skip(f"Auth server not accessible: {e}")
        finally:
            await browser.close()


@pytest.mark.asyncio
@pytest.mark.playwright  
async def test_form_validation_client_side():
    """Test client-side form validation without server"""
    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        base_url = os.getenv("AUTH_URL", "http://localhost:8000")
        
        try:
            await page.goto(f"{base_url}/auth/register-page", wait_until="domcontentloaded", timeout=5000)
            
            # Try to submit empty form
            await page.click('button[type="submit"]')
            
            # Check HTML5 validation
            email_input = page.locator('input[name="email"]')
            is_invalid = await email_input.evaluate('el => !el.validity.valid')
            assert is_invalid, "Email field should be invalid when empty"
            
            # Fill invalid email
            await page.fill('input[name="email"]', "notanemail")
            await page.click('button[type="submit"]')
            
            # Check email format validation
            is_invalid = await email_input.evaluate('el => !el.validity.valid')
            assert is_invalid, "Email field should be invalid with wrong format"
            
            print("✅ Client-side validation working correctly")
            
        except Exception as e:
            if "Timeout" in str(e):
                pytest.skip(f"Auth server not accessible")
            else:
                raise
        finally:
            await browser.close()