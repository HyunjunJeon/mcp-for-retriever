"""Direct MCP server test using FastMCP client."""

import asyncio
from fastmcp import Client
from pprint import pprint


async def test_direct_mcp():
    """Test MCP server directly using FastMCP client"""
    # Create client
    client = Client(
        base_url="http://localhost:8001",
        headers={"Authorization": "Bearer test-internal-key"}
    )
    
    async with client:
        print("📋 Listing tools...")
        tools = await client.list_tools()
        print(f"Found {len(tools.tools)} tools:")
        for tool in tools.tools:
            print(f"  - {tool.name}: {tool.description}")
        
        print("\n🏥 Testing health check...")
        result = await client.call_tool("health_check", {})
        print("Health check result:")
        pprint(result.content)
        
        print("\n✅ Direct MCP test successful!")


if __name__ == "__main__":
    asyncio.run(test_direct_mcp())