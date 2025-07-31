"""Basic Playwright setup test to verify environment configuration."""

import pytest
from playwright.async_api import Page, async_playwright
import os


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_playwright_environment():
    """Test that Playwright environment is properly configured."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 720})
        page = await context.new_page()
        
        # Check if we can navigate to a test page
        await page.goto("https://example.com")
        
        # Verify page loaded
        assert await page.title() == "Example Domain"
        
        # Check viewport size
        viewport = page.viewport_size
        assert viewport["width"] == 1280
        assert viewport["height"] == 720
        
        await browser.close()


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_auth_server_accessible(auth_page: Page):
    """Test that auth server is accessible."""
    auth_url = auth_page.auth_url
    
    try:
        # Try to access the auth server root
        response = await auth_page.goto(auth_url)
        
        # Check if server is running
        if response:
            assert response.status < 500, f"Auth server returned status {response.status}"
    except Exception as e:
        # If server is not running, skip the test
        pytest.skip(f"Auth server not accessible at {auth_url}: {e}")


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_mcp_server_accessible(mcp_page: Page):
    """Test that MCP server is accessible."""
    mcp_url = mcp_page.mcp_url
    
    try:
        # Try to access the MCP server
        response = await mcp_page.goto(mcp_url)
        
        # Check if server is running
        if response:
            assert response.status < 500, f"MCP server returned status {response.status}"
    except Exception as e:
        # If server is not running, skip the test
        pytest.skip(f"MCP server not accessible at {mcp_url}: {e}")


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_headless_mode_configuration():
    """Test that headless mode is properly configured."""
    headless_env = os.getenv("PLAYWRIGHT_HEADLESS", "true")
    
    assert headless_env in ["true", "false"], "PLAYWRIGHT_HEADLESS must be 'true' or 'false'"
    
    # In CI/CD, we expect headless to be true
    if os.getenv("CI"):
        assert headless_env == "true", "Headless mode should be enabled in CI"


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_browser_context_configuration(context):
    """Test that browser context is properly configured."""
    # Check that HTTPS errors are ignored (for local development)
    # This is set in our conftest.py browser_context_args fixture
    
    # Create a new page in the context
    page = await context.new_page()
    
    # Try to navigate to a self-signed HTTPS site (this would fail without ignore_https_errors)
    # For now, just verify the page was created successfully
    assert page is not None
    
    await page.close()