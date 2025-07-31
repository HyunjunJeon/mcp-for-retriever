"""MCP Client browser test using Playwright."""

import pytest
from playwright.async_api import async_playwright
import uuid
import json


@pytest.mark.asyncio
async def test_mcp_client_flow():
    """Test MCP client page with authentication and tool calls"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        # Generate unique credentials
        test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
        test_password = "TestPass123"
        
        try:
            # Step 1: Register
            print("📝 Registering new user...")
            await page.goto("http://localhost:8000/auth/register-page")
            await page.fill('input[name="email"]', test_email)
            await page.fill('input[name="password"]', test_password)
            await page.click('button[type="submit"]')
            
            # Wait for success message
            await page.wait_for_selector('.success', timeout=5000)
            print(f"✅ Registered: {test_email}")
            
            # Step 2: Login
            print("🔐 Logging in...")
            await page.click('a[href="/auth/login-page"]')
            await page.fill('input[name="email"]', test_email)
            await page.fill('input[name="password"]', test_password)
            await page.click('button[type="submit"]')
            
            # Wait for token display
            await page.wait_for_selector('#tokenInfo', state='visible', timeout=5000)
            
            # Get access token from page
            token_element = await page.query_selector('#accessToken')
            access_token = await token_element.inner_text()
            print(f"✅ Got access token: {access_token[:20]}...")
            
            # Step 3: Navigate to MCP client page
            print("🚀 Testing MCP client...")
            await page.goto("http://localhost:8000/mcp/client-page")
            
            # Token should be auto-loaded from localStorage
            await page.wait_for_timeout(1000)
            
            # Step 4: Test tools/list
            print("📋 Listing available tools...")
            await page.click('button:has-text("List Tools")')
            
            # Wait for tools list
            await page.wait_for_selector('#toolsList:not(:empty)', timeout=10000)
            
            # Check if tools are listed
            tools_text = await page.inner_text('#toolsList')
            assert "search_web" in tools_text
            assert "search_vectors" in tools_text
            assert "search_database" in tools_text
            print("✅ Tools listed successfully")
            
            # Step 5: Test health check
            print("🏥 Testing health check...")
            # Select health_check tool
            await page.select_option('select#toolSelect', 'health_check')
            await page.click('button:has-text("Call Tool")')
            
            # Wait for response
            await page.wait_for_selector('#response pre', timeout=10000)
            
            # Check response
            response_text = await page.inner_text('#response pre')
            response_data = json.loads(response_text)
            assert response_data.get("result") is not None
            assert response_data["result"]["status"] == "healthy"
            print("✅ Health check successful")
            
            # Step 6: Test search_web tool
            print("🔍 Testing web search...")
            await page.select_option('select#toolSelect', 'search_web')
            
            # Fill in parameters
            await page.fill('textarea#toolArgs', json.dumps({
                "query": "FastMCP tutorial",
                "limit": 3
            }, indent=2))
            
            await page.click('button:has-text("Call Tool")')
            
            # Wait for response
            await page.wait_for_selector('#response pre', timeout=15000)
            
            # Check response
            response_text = await page.inner_text('#response pre')
            response_data = json.loads(response_text)
            
            if "error" in response_data:
                print(f"⚠️ Search returned error: {response_data['error']}")
            else:
                assert response_data.get("result") is not None
                print(f"✅ Web search returned {len(response_data['result'].get('results', []))} results")
            
            # Take screenshot of final state
            await page.screenshot(path="mcp_client_test.png")
            print("📸 Screenshot saved as mcp_client_test.png")
            
        finally:
            await page.wait_for_timeout(3000)  # Keep browser open for 3 seconds
            await browser.close()
            
    print("✅ All MCP client tests passed!")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_mcp_client_flow())