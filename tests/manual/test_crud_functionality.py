#!/usr/bin/env python3
"""CRUD 도구 기능 테스트"""

import asyncio
import httpx
import json

async def test_crud_functionality():
    """CRUD 도구의 실제 기능 테스트"""
    auth_base_url = "http://localhost:8000"
    
    # Admin 사용자로 로그인
    async with httpx.AsyncClient() as client:
        print("=== CRUD 도구 기능 테스트 ===\n")
        
        # 로그인
        login_resp = await client.post(
            f"{auth_base_url}/auth/login",
            json={"email": "admin@example.com", "password": "Admin123!"}
        )
        
        if login_resp.status_code != 200:
            print("Admin 로그인 실패")
            return
            
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # 1. 컬렉션 생성 테스트
        print("1. 컬렉션 생성 테스트")
        create_resp = await client.post(
            f"{auth_base_url}/mcp/proxy",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "create_vector_collection",
                    "arguments": {
                        "collection": "test_collection",
                        "vector_size": 1536,
                        "distance_metric": "cosine"
                    }
                },
                "id": 1
            },
            headers=headers
        )
        
        print(f"   상태 코드: {create_resp.status_code}")
        if create_resp.status_code == 200:
            result = create_resp.json()
            print(f"   응답: {json.dumps(result, indent=2, ensure_ascii=False)}")
        print()
        
        # 2. 문서 생성 테스트
        print("2. 문서 생성 테스트")
        doc_resp = await client.post(
            f"{auth_base_url}/mcp/proxy",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "create_vector_document",
                    "arguments": {
                        "collection": "test_collection",
                        "document": {
                            "id": "doc1",
                            "text": "이것은 테스트 문서입니다.",
                            "metadata": {"category": "test"}
                        }
                    }
                },
                "id": 2
            },
            headers=headers
        )
        
        print(f"   상태 코드: {doc_resp.status_code}")
        if doc_resp.status_code == 200:
            result = doc_resp.json()
            if "error" in result:
                print(f"   에러: {result['error']}")
            else:
                print(f"   결과: 성공")
        print()
        
        # 3. 문서 업데이트 테스트
        print("3. 문서 업데이트 테스트")
        update_resp = await client.post(
            f"{auth_base_url}/mcp/proxy",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "update_vector_document",
                    "arguments": {
                        "collection": "test_collection",
                        "document": {
                            "id": "doc1",
                            "text": "업데이트된 테스트 문서입니다.",
                            "metadata": {"category": "updated"}
                        }
                    }
                },
                "id": 3
            },
            headers=headers
        )
        
        print(f"   상태 코드: {update_resp.status_code}")
        if update_resp.status_code == 200:
            result = update_resp.json()
            if "error" in result:
                print(f"   에러: {result['error']}")
            else:
                print(f"   결과: 성공")
        print()
        
        # 4. 문서 삭제 테스트
        print("4. 문서 삭제 테스트")
        delete_resp = await client.post(
            f"{auth_base_url}/mcp/proxy",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "delete_vector_document",
                    "arguments": {
                        "collection": "test_collection",
                        "document_id": "doc1"
                    }
                },
                "id": 4
            },
            headers=headers
        )
        
        print(f"   상태 코드: {delete_resp.status_code}")
        if delete_resp.status_code == 200:
            result = delete_resp.json()
            if "error" in result:
                print(f"   에러: {result['error']}")
            else:
                print(f"   결과: 성공")

if __name__ == "__main__":
    asyncio.run(test_crud_functionality())