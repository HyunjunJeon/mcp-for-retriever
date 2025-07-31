import httpx
import json

# MCP 서버에 직접 tools/list 요청
request = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list",
    "params": {}
}

headers = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
    "Authorization": "Bearer test-internal-key"
}

response = httpx.post(
    "http://localhost:8001/mcp/",
    json=request,
    headers=headers
)

print(f"Status: {response.status_code}")
print(f"Headers: {dict(response.headers)}")
print(f"Response: {response.text}")

# SSE 형식으로 파싱
if "text/event-stream" in response.headers.get("content-type", ""):
    for line in response.text.strip().split('\n'):
        if line.startswith('data: '):
            data = json.loads(line[6:])
            if "result" in data and "tools" in data["result"]:
                tools = data["result"]["tools"]
                print(f"\nTotal tools: {len(tools)}")
                for tool in tools:
                    print(f"  - {tool['name']}")
