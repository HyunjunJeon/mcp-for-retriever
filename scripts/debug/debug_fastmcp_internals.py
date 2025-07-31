"""FastMCP Client 내부 동작 상세 분석"""

import asyncio
import json
from fastmcp import Client
import httpx
import logging
from unittest.mock import patch

# 로깅 활성화
logging.basicConfig(level=logging.DEBUG)

# 모든 HTTP 요청을 로깅하는 패치
class LoggingTransport(httpx.HTTPTransport):
    def handle_request(self, request):
        print(f"\n🌐 HTTP Request:")
        print(f"  URL: {request.url}")
        print(f"  Method: {request.method}")
        print(f"  Headers: {dict(request.headers)}")
        if request.content:
            try:
                if hasattr(request, 'json'):
                    body = request.json()
                else:
                    body = json.loads(request.content.decode())
                print(f"  Body: {json.dumps(body, indent=4, ensure_ascii=False)}")
            except:
                print(f"  Raw Body: {request.content}")
        
        response = super().handle_request(request)
        
        print(f"\n📨 HTTP Response:")
        print(f"  Status: {response.status_code}")
        print(f"  Headers: {dict(response.headers)}")
        try:
            if response.headers.get('content-type', '').startswith('text/event-stream'):
                print(f"  SSE Content: {response.text}")
            else:
                response_json = response.json()
                print(f"  JSON: {json.dumps(response_json, indent=4, ensure_ascii=False)}")
        except:
            print(f"  Raw Content: {response.text}")
        print("=" * 60)
        
        return response


# AsyncTransport도 패치
class LoggingAsyncTransport(httpx.AsyncHTTPTransport):
    async def handle_async_request(self, request):
        print(f"\n🌐 Async HTTP Request:")
        print(f"  URL: {request.url}")
        print(f"  Method: {request.method}")
        print(f"  Headers: {dict(request.headers)}")
        if request.content:
            try:
                body = json.loads(request.content.decode())
                print(f"  Body: {json.dumps(body, indent=4, ensure_ascii=False)}")
            except:
                print(f"  Raw Body: {request.content}")
        
        response = await super().handle_async_request(request)
        
        print(f"\n📨 Async HTTP Response:")
        print(f"  Status: {response.status_code}")
        print(f"  Headers: {dict(response.headers)}")
        try:
            if response.headers.get('content-type', '').startswith('text/event-stream'):
                print(f"  SSE Content: {response.text}")
            else:
                response_json = response.json()
                print(f"  JSON: {json.dumps(response_json, indent=4, ensure_ascii=False)}")
        except:
            print(f"  Raw Content: {response.text}")
        print("=" * 60)
        
        return response


async def debug_fastmcp_with_logging():
    """로깅이 활성화된 FastMCP Client 테스트"""
    print("=== FastMCP Client 상세 로깅 ===")
    
    # HTTP 클라이언트에 로깅 트랜스포트 적용
    with patch('httpx.AsyncClient') as mock_client_class:
        def create_logged_client(*args, **kwargs):
            # AsyncHTTPTransport 사용
            kwargs['transport'] = LoggingAsyncTransport()
            return httpx.AsyncClient(*args, **kwargs)
        
        mock_client_class.side_effect = create_logged_client
        
        try:
            async with Client(
                "http://localhost:8001/mcp/",
                auth="Bearer test-mcp-key"
            ) as client:
                print("✅ FastMCP Client 연결 성공")
                
                # list_tools 호출
                print("\n🔧 FastMCP Client: list_tools() 호출")
                tools = await client.list_tools()
                print(f"📋 도구 목록 ({len(tools)}개):")
                for tool in tools:
                    print(f"  - {tool.name}: {tool.description}")
                
                if tools:
                    # 첫 번째 도구 호출
                    print(f"\n🛠️ FastMCP Client: {tools[0].name} 호출")
                    if tools[0].name == "health_check":
                        result = await client.call_tool("health_check", {})
                        print(f"🏥 결과: {result.data}")
                
        except Exception as e:
            print(f"❌ FastMCP Client 오류: {e}")
            import traceback
            traceback.print_exc()


async def analyze_mcp_protocol():
    """MCP 프로토콜 분석"""
    print("\n=== MCP 프로토콜 분석 ===")
    
    # 1. 어떤 메소드들이 지원되는지 확인
    print("\n--- 지원되는 MCP 메소드 확인 ---")
    async with httpx.AsyncClient() as client:
        # 잘못된 메소드로 요청해서 서버가 지원하는 메소드 목록을 확인
        response = await client.post(
            "http://localhost:8001/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "unsupported_method",
                "id": 1
            },
            headers={
                "Authorization": "Bearer test-mcp-key",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            }
        )
        print(f"Unsupported method 응답: {response.status_code}")
        print(f"응답 내용: {response.text}")


async def test_initialize_variations():
    """다양한 initialize 형식 테스트"""
    print("\n=== 다양한 initialize 형식 테스트 ===")
    
    async with httpx.AsyncClient() as client:
        variations = [
            {
                "name": "최소 initialize",
                "payload": {
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "Test", "version": "1.0"}
                    },
                    "id": 1
                }
            },
            {
                "name": "빈 capabilities",
                "payload": {
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "Test", "version": "1.0"}
                    },
                    "id": 1
                }
            }
        ]
        
        for i, variation in enumerate(variations, 1):
            print(f"\n--- {variation['name']} ---")
            
            response = await client.post(
                "http://localhost:8001/mcp/",
                json=variation['payload'],
                headers={
                    "Authorization": "Bearer test-mcp-key",
                    "Content-Type": "application/json",  
                    "Accept": "application/json, text/event-stream"
                }
            )
            
            print(f"상태: {response.status_code}")
            session_id = response.headers.get("mcp-session-id")
            print(f"세션 ID: {session_id}")
            
            if session_id:
                # 이 세션으로 tools/list 시도
                print(f"세션 {session_id}로 tools/list 시도...")
                tools_response = await client.post(
                    "http://localhost:8001/mcp/",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/list",
                        "id": 2
                    },
                    headers={
                        "Authorization": "Bearer test-mcp-key",
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                        "mcp-session-id": session_id
                    }
                )
                
                print(f"Tools/list 상태: {tools_response.status_code}")
                if "tools" in tools_response.text:
                    print("✅ 성공! - 도구 목록 포함")
                    return True
                else:
                    print(f"❌ 실패: {tools_response.text[:200]}")
    
    return False


async def main():
    """메인 함수"""
    await analyze_mcp_protocol()
    await debug_fastmcp_with_logging()
    success = await test_initialize_variations()
    
    if success:
        print("\n🎉 성공적인 형식 발견!")
    else:
        print("\n😞 모든 시도 실패")


if __name__ == "__main__":
    asyncio.run(main())