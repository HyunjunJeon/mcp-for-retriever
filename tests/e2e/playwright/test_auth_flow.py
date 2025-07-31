"""Playwright E2E test for authentication flow."""

import pytest
from playwright.async_api import Page, expect
import uuid
import os


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_register_and_login_flow(page: Page):
    """Test complete authentication flow: register → login → token verification"""
    
    # Generate unique email for this test
    test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    test_password = "TestPass123"  # Must include uppercase, lowercase, and numbers
    
    base_url = os.getenv("AUTH_URL", "http://localhost:8000")
    
    # Navigate to registration page
    await page.goto(f"{base_url}/auth/register-page")
    
    # Check page title
    await expect(page).to_have_title("MCP 회원가입")
    
    # Fill registration form
    await page.fill('input[name="email"]', test_email)
    await page.fill('input[name="password"]', test_password)
    
    # Submit registration form
    await page.click('button[type="submit"]')
    
    # Wait for success message
    await expect(page.locator('.success')).to_contain_text('회원가입 성공!')
    
    # Click login link
    await page.click('a[href="/auth/login-page"]')
    
    # Check we're on login page
    await expect(page).to_have_title("MCP 로그인")
    
    # Fill login form
    await page.fill('input[name="email"]', test_email)
    await page.fill('input[name="password"]', test_password)
    
    # Submit login form
    await page.click('button[type="submit"]')
    
    # Wait for success message
    await expect(page.locator('.success')).to_contain_text('로그인 성공!')
    
    # Check that token info is displayed
    await expect(page.locator('#tokenInfo')).to_be_visible()
    
    # Get tokens from page
    access_token_element = page.locator('#accessToken')
    refresh_token_element = page.locator('#refreshToken')
    
    await expect(access_token_element).not_to_be_empty()
    await expect(refresh_token_element).not_to_be_empty()
    
    # Check localStorage has tokens
    access_token_storage = await page.evaluate('() => localStorage.getItem("access_token")')
    refresh_token_storage = await page.evaluate('() => localStorage.getItem("refresh_token")')
    
    assert access_token_storage is not None
    assert refresh_token_storage is not None
    
    # Test /auth/me endpoint
    await page.click('button:has-text("현재 사용자 정보 조회")')
    
    # Wait for user info to be displayed
    await expect(page.locator('.success')).to_contain_text('사용자 정보:')
    await expect(page.locator('.success')).to_contain_text(test_email)


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_login_with_invalid_credentials(page: Page):
    """Test login with invalid credentials"""
    
    base_url = os.getenv("AUTH_URL", "http://localhost:8000")
    
    # Navigate to login page
    await page.goto(f"{base_url}/auth/login-page")
    
    # Fill login form with invalid credentials
    await page.fill('input[name="email"]', "nonexistent@example.com")
    await page.fill('input[name="password"]', "wrongpassword")
    
    # Submit login form
    await page.click('button[type="submit"]')
    
    # Wait for error message
    await expect(page.locator('.error')).to_be_visible()
    await expect(page.locator('.error')).to_contain_text('오류:')
    
    # Token info should not be visible
    await expect(page.locator('#tokenInfo')).not_to_be_visible()


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_register_with_existing_email(page: Page):
    """Test registration with already existing email"""
    
    # First, create a user
    test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    test_password = "TestPass123"
    
    base_url = os.getenv("AUTH_URL", "http://localhost:8000")
    
    # Navigate to registration page
    await page.goto(f"{base_url}/auth/register-page")
    
    # Register first time
    await page.fill('input[name="email"]', test_email)
    await page.fill('input[name="password"]', test_password)
    await page.click('button[type="submit"]')
    
    # Wait for success
    await expect(page.locator('.success')).to_contain_text('회원가입 성공!')
    
    # Try to register again with same email
    await page.reload()
    await page.fill('input[name="email"]', test_email)
    await page.fill('input[name="password"]', test_password)
    await page.click('button[type="submit"]')
    
    # Should show error
    await expect(page.locator('.error')).to_be_visible()
    await expect(page.locator('.error')).to_contain_text('오류:')


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_form_validation(page: Page):
    """Test client-side form validation"""
    
    base_url = os.getenv("AUTH_URL", "http://localhost:8000")
    
    # Navigate to registration page
    await page.goto(f"{base_url}/auth/register-page")
    
    # Try to submit empty form
    await page.click('button[type="submit"]')
    
    # Check HTML5 validation (email should be required)
    email_input = page.locator('input[name="email"]')
    is_invalid = await email_input.evaluate('el => !el.validity.valid')
    assert is_invalid
    
    # Fill email but leave password empty
    await page.fill('input[name="email"]', "test@example.com")
    await page.click('button[type="submit"]')
    
    # Check password validation
    password_input = page.locator('input[name="password"]')
    is_invalid = await password_input.evaluate('el => !el.validity.valid')
    assert is_invalid
    
    # Test password minimum length
    await page.fill('input[name="password"]', "123")  # Too short
    await page.click('button[type="submit"]')
    
    # Check password length validation
    is_invalid = await password_input.evaluate('el => !el.validity.valid')
    assert is_invalid


@pytest.mark.asyncio
@pytest.mark.playwright  
async def test_navigation_between_pages(page: Page):
    """Test navigation between register and login pages"""
    
    base_url = os.getenv("AUTH_URL", "http://localhost:8000")
    
    # Start at registration page
    await page.goto(f"{base_url}/auth/register-page")
    await expect(page).to_have_title("MCP 회원가입")
    
    # Navigate to login page
    await page.click('a:has-text("로그인")')
    await expect(page).to_have_title("MCP 로그인")
    await expect(page).to_have_url(f"{base_url}/auth/login-page")
    
    # Navigate back to registration page
    await page.click('a:has-text("회원가입")')
    await expect(page).to_have_title("MCP 회원가입")
    await expect(page).to_have_url(f"{base_url}/auth/register-page")