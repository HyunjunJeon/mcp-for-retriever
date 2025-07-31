import httpx
import json

# 1. Initialize session
init_request = {
    "jsonrpc": "2.0",
    "id": 0,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {
            "name": "mcp",
            "version": "0.1.0"
        }
    }
}

headers = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
    "Authorization": "Bearer test-internal-key"
}

# Initialize session
print("Initializing session...")
response = httpx.post(
    "http://localhost:8001/mcp/",
    json=init_request,
    headers=headers
)

session_id = response.headers.get("mcp-session-id")
print(f"Session ID: {session_id}")

# 2. Request tools list with session
tools_request = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list",
    "params": {}
}

headers["mcp-session-id"] = session_id

print("\nRequesting tools list...")
response = httpx.post(
    "http://localhost:8001/mcp/",
    json=tools_request,
    headers=headers
)

print(f"Status: {response.status_code}")
print(f"Response: {response.text[:200]}...")

# Parse SSE response
if "text/event-stream" in response.headers.get("content-type", ""):
    for line in response.text.strip().split('\n'):
        if line.startswith('data: '):
            try:
                data = json.loads(line[6:])
                if "result" in data and "tools" in data["result"]:
                    tools = data["result"]["tools"]
                    print(f"\nTotal tools from MCP server: {len(tools)}")
                    for tool in tools:
                        print(f"  - {tool['name']}")
            except json.JSONDecodeError:
                pass
