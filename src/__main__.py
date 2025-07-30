"""Main entry point for running the MCP server."""

import os

# Always use the auth-enabled server
from src.server_auth import mcp

# Run the server
if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    port = int(os.getenv("MCP_SERVER_PORT", "8001"))
    
    print(f"Starting MCP server with authentication (transport: {transport})...")
    
    if transport == "http":
        print(f"HTTP server listening on port {port}...")
        mcp.run(transport="http", port=port)
    else:
        print("STDIO server started...")
        mcp.run()