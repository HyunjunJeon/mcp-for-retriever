"""직접 MCP 서버에 연결하여 디버깅"""

import httpx
import asyncio
import json


def parse_sse_response(resp):
    """SSE 응답 파싱"""
    response_data = None
    if resp.headers.get("content-type") == "text/event-stream":
        response_text = resp.text
        for line in response_text.split('\n'):
            if line.startswith('data: '):
                json_data = line[6:]  # "data: " 제거
                if json_data.strip():
                    response_data = json.loads(json_data)
                    break
    else:
        response_data = resp.json()
    return response_data


async def test_direct_mcp():
    """MCP 서버에 직접 연결 테스트"""
    
    async with httpx.AsyncClient() as client:
        # 0. 초기화 요청
        resp = await client.post(
            "http://localhost:8001/mcp/",
            json={
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {
                    "protocolVersion": "1.0.0",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "test",
                        "version": "1.0.0"
                    }
                }
            },
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Authorization": "Bearer test-mcp-key"
            }
        )
        
        print("=== initialize 응답 ===")
        print(f"Status: {resp.status_code}")
        print(f"Headers: {dict(resp.headers)}")
        
        response_data = parse_sse_response(resp)
        print(f"Response: {json.dumps(response_data, indent=2) if response_data else 'No data'}")
        
        # 세션 ID 추출
        session_id = resp.headers.get("mcp-session-id")
        if not session_id and response_data:
            if "result" in response_data and "sessionId" in response_data["result"]:
                session_id = response_data["result"]["sessionId"]
        
        print(f"\nSession ID: {session_id}")
        
        # 세션 ID를 헤더에 추가
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": "Bearer test-mcp-key"
        }
        if session_id:
            headers["mcp-session-id"] = session_id
        # tools/list 요청
        resp = await client.post(
            "http://localhost:8001/mcp/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {}  # 빈 params 추가
            },
            headers=headers
        )
        
        print("\n=== tools/list 응답 ===")
        print(f"Status: {resp.status_code}")
        response_data = parse_sse_response(resp)
        print(f"Response: {json.dumps(response_data, indent=2) if response_data else 'No data'}")
        
        # tools/call search_vectors 요청
        resp = await client.post(
            "http://localhost:8001/mcp/",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "search_vectors",
                    "arguments": {
                        "query": "test query",
                        "collection": "documents",
                        "limit": 5
                    }
                }
            },
            headers=headers
        )
        
        print("\n=== tools/call search_vectors 응답 ===")
        print(f"Status: {resp.status_code}")
        response_data = parse_sse_response(resp)
        print(f"Response: {json.dumps(response_data, indent=2) if response_data else 'No data'}")


if __name__ == "__main__":
    asyncio.run(test_direct_mcp())