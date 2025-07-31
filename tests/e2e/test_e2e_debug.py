"""
E2E 테스트 디버깅용 스크립트
"""

import asyncio
import httpx
import json

async def test_full_e2e():
    async with httpx.AsyncClient() as client:
        # 1. 회원가입
        register_data = {
            'email': 'test@example.com',
            'password': 'Test123!'
        }
        
        try:
            register_resp = await client.post('http://localhost:8000/auth/register', json=register_data)
            print(f'Register Status: {register_resp.status_code}')
            if register_resp.status_code == 409:
                print('User already exists, continuing...')
        except Exception as e:
            print(f'Register error: {e}')
        
        # 2. 로그인
        login_data = {
            'email': 'test@example.com',
            'password': 'Test123!'
        }
        
        try:
            login_resp = await client.post('http://localhost:8000/auth/login', json=login_data)
            print(f'Login Status: {login_resp.status_code}')
            print(f'Login Response: {login_resp.text}')
            
            if login_resp.status_code != 200:
                print('Login failed!')
                return
            
            # 토큰 추출
            token_data = login_resp.json()
            access_token = token_data['access_token']
            print(f'Access Token: {access_token[:50]}...')
            
            # JWT 토큰 디코딩 (디버깅용)
            import base64
            parts = access_token.split('.')
            if len(parts) >= 2:
                # 패딩 추가
                payload = parts[1]
                payload += '=' * (4 - len(payload) % 4)
                decoded_payload = base64.b64decode(payload)
                print(f'JWT Payload: {decoded_payload.decode("utf-8")}')
                
            # 3. MCP proxy 호출 - 먼저 초기화
            headers = {'Authorization': f'Bearer {access_token}'}
            
            # 초기화 요청
            init_request = {
                'jsonrpc': '2.0',
                'method': 'initialize',
                'params': {
                    'protocolVersion': '2024-11-05',
                    'capabilities': {},
                    'clientInfo': {
                        'name': 'test-client',
                        'version': '1.0.0'
                    }
                },
                'id': 1
            }
            
            init_resp = await client.post('http://localhost:8000/mcp/proxy', json=init_request, headers=headers)
            print(f'MCP Init Status: {init_resp.status_code}')
            print(f'MCP Init Response: {init_resp.text}')
            
            # tools/list 요청
            mcp_request = {
                'jsonrpc': '2.0',
                'method': 'tools/list',
                'id': 2
            }
            
            mcp_resp = await client.post('http://localhost:8000/mcp/proxy', json=mcp_request, headers=headers)
            print(f'MCP Proxy Status: {mcp_resp.status_code}')
            print(f'MCP Proxy Response: {mcp_resp.text}')
            
        except Exception as e:
            print(f'Login/MCP error: {e}')

if __name__ == '__main__':
    asyncio.run(test_full_e2e())