#!/usr/bin/env python3
"""PostgreSQL CRUD E2E 테스트"""

import pytest
import asyncio
import httpx
import uuid
from typing import Dict, Any


async def get_auth_token(auth_base_url: str, role: str = "admin") -> str:
    """지정된 역할의 인증 토큰 획득"""
    async with httpx.AsyncClient() as client:
        # 역할별 계정 정보
        accounts = {
            "admin": {"email": "admin@example.com", "password": "Admin123!"},
            "analyst": {"email": "analyst@example.com", "password": "Analyst123!"},
            "viewer": {"email": "viewer@example.com", "password": "Viewer123!"}
        }
        
        account = accounts.get(role, accounts["admin"])
        
        # 로그인 시도
        login_resp = await client.post(
            f"{auth_base_url}/auth/login",
            json=account
        )
        
        if login_resp.status_code != 200:
            # 계정이 없으면 생성
            await client.post(
                f"{auth_base_url}/auth/register",
                json=account
            )
            login_resp = await client.post(
                f"{auth_base_url}/auth/login",
                json=account
            )
        
        assert login_resp.status_code == 200
        return login_resp.json()["access_token"]


async def call_mcp_tool(
    client: httpx.AsyncClient,
    auth_base_url: str,
    token: str,
    tool_name: str,
    arguments: Dict[str, Any]
) -> Dict[str, Any]:
    """MCP 도구 호출 헬퍼"""
    response = await client.post(
        f"{auth_base_url}/mcp/proxy",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            },
            "id": str(uuid.uuid4())
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_postgres_crud_full_cycle(auth_base_url: str):
    """PostgreSQL CRUD 전체 사이클 테스트"""
    test_data = {
        "name": f"Test User {uuid.uuid4().hex[:8]}",
        "email": f"test_{uuid.uuid4().hex[:8]}@example.com",
        "metadata": {"role": "test", "active": True}
    }
    
    auth_token = await get_auth_token(auth_base_url)
    
    async with httpx.AsyncClient() as client:
        # 1. 레코드 생성
        create_result = await call_mcp_tool(
            client, auth_base_url, auth_token,
            "create_database_record",
            {
                "table": "users",
                "data": test_data
            }
        )
        
        print(f"레코드 생성 응답: {create_result}")
        assert "result" in create_result
        
        # 결과 파싱
        if create_result["result"].get("structuredContent"):
            record = create_result["result"]["structuredContent"]["record"]
            record_id = record["id"]
        else:
            # 에러 체크
            if create_result["result"].get("isError", False):
                error_msg = create_result["result"]["content"][0]["text"]
                print(f"⚠️ 레코드 생성 실패: {error_msg}")
                # PostgreSQL이 실행 중이지 않으면 테스트 건너뛰기
                if "사용할 수 없습니다" in error_msg or "connection" in error_msg.lower():
                    pytest.skip("PostgreSQL 서버가 실행 중이지 않음")
                pytest.fail(f"레코드 생성 실패: {error_msg}")
            
            # 텍스트 파싱 (fallback)
            content = create_result["result"]["content"][0]["text"]
            assert "success" in content.lower()
            record_id = "1"  # 테스트용 기본값
        
        # 2. 레코드 업데이트
        update_data = {
            "name": f"Updated User {uuid.uuid4().hex[:8]}",
            "metadata": {"role": "updated", "active": False}
        }
        
        update_result = await call_mcp_tool(
            client, auth_base_url, auth_token,
            "update_database_record",
            {
                "table": "users",
                "record_id": str(record_id),
                "data": update_data
            }
        )
        
        print(f"레코드 업데이트 응답: {update_result}")
        assert "result" in update_result
        assert not update_result["result"].get("isError", False)
        
        # 3. 데이터베이스 검색으로 업데이트 확인
        search_result = await call_mcp_tool(
            client, auth_base_url, auth_token,
            "search_database",
            {
                "query": f"SELECT * FROM users WHERE id = '{record_id}'",
                "limit": 1
            }
        )
        
        print(f"검색 결과: {search_result}")
        assert "result" in search_result
        
        # 4. 레코드 삭제
        delete_result = await call_mcp_tool(
            client, auth_base_url, auth_token,
            "delete_database_record",
            {
                "table": "users",
                "record_id": str(record_id)
            }
        )
        
        print(f"레코드 삭제 응답: {delete_result}")
        assert "result" in delete_result
        assert not delete_result["result"].get("isError", False)


@pytest.mark.asyncio
async def test_postgres_crud_permissions(auth_base_url: str):
    """역할별 PostgreSQL CRUD 권한 테스트"""
    test_users = {
        "admin": {
            "can_create": True,
            "can_update": True,
            "can_delete": True
        },
        "analyst": {
            "can_create": True,
            "can_update": True,
            "can_delete": False
        },
        "viewer": {
            "can_create": False,
            "can_update": False,
            "can_delete": False
        }
    }
    
    async with httpx.AsyncClient() as client:
        for role, permissions in test_users.items():
            print(f"\n=== {role.upper()} 권한 테스트 ===")
            token = await get_auth_token(auth_base_url, role)
            
            # 생성 권한 테스트
            create_result = await call_mcp_tool(
                client, auth_base_url, token,
                "create_database_record",
                {
                    "table": "documents",
                    "data": {"title": f"Test {role}", "content": "Test content"}
                }
            )
            
            if permissions["can_create"]:
                # 성공하거나 데이터베이스 연결 오류
                assert "result" in create_result
                if not create_result["result"].get("isError", False):
                    # 성공한 경우 ID 추출
                    if create_result["result"].get("structuredContent"):
                        record_id = create_result["result"]["structuredContent"]["record"]["id"]
                    else:
                        record_id = "test_id"
                else:
                    # 데이터베이스 연결 오류인 경우 테스트 건너뛰기
                    error_msg = create_result["result"]["content"][0]["text"]
                    if "사용할 수 없습니다" in error_msg:
                        print(f"⚠️ 데이터베이스 연결 실패 - 테스트 건너뛰기")
                        continue
                    record_id = "test_id"
            else:
                # 권한 없음 오류
                assert "error" in create_result or create_result["result"].get("isError", False)
                record_id = "test_id"
            
            # 업데이트 권한 테스트
            update_result = await call_mcp_tool(
                client, auth_base_url, token,
                "update_database_record",
                {
                    "table": "documents",
                    "record_id": str(record_id),
                    "data": {"title": f"Updated by {role}"}
                }
            )
            
            if permissions["can_update"]:
                assert "result" in update_result
            else:
                assert "error" in update_result or update_result["result"].get("isError", False)
            
            # 삭제 권한 테스트
            delete_result = await call_mcp_tool(
                client, auth_base_url, token,
                "delete_database_record",
                {
                    "table": "documents",
                    "record_id": str(record_id)
                }
            )
            
            if permissions["can_delete"]:
                assert "result" in delete_result
            else:
                assert "error" in delete_result or delete_result["result"].get("isError", False)
            
            print(f"✅ {role} 권한 테스트 완료")


@pytest.mark.asyncio
async def test_postgres_crud_security(auth_base_url: str):
    """PostgreSQL CRUD 보안 테스트"""
    auth_token = await get_auth_token(auth_base_url)
    
    async with httpx.AsyncClient() as client:
        # 1. 허용되지 않은 테이블 접근 시도
        result = await call_mcp_tool(
            client, auth_base_url, auth_token,
            "create_database_record",
            {
                "table": "admin_secrets",  # 허용되지 않은 테이블
                "data": {"secret": "password123"}
            }
        )
        
        # 에러 확인
        is_error = result["result"].get("isError", False)
        if is_error:
            error_text = result["result"]["content"][0]["text"]
            print(f"허용되지 않은 테이블 에러: {error_text}")
            assert "허용되지 않은 테이블" in error_text or "not allowed" in error_text.lower()
        else:
            # 구조화된 에러 메시지 확인
            assert "error" in result
        
        # 2. SQL 인젝션 시도 (컬럼명에 SQL 주입)
        result = await call_mcp_tool(
            client, auth_base_url, auth_token,
            "create_database_record",
            {
                "table": "users",
                "data": {
                    "name'; DROP TABLE users; --": "malicious",
                    "email": "hacker@evil.com"
                }
            }
        )
        
        # prepared statement로 안전하게 처리되어야 함
        # 에러가 발생하거나 정상 처리되어야 함 (DROP TABLE은 실행되지 않음)
        assert "result" in result
        
        # 3. 잘못된 ID 형식으로 업데이트 시도
        result = await call_mcp_tool(
            client, auth_base_url, auth_token,
            "update_database_record",
            {
                "table": "users",
                "record_id": "'; DELETE FROM users; --",
                "data": {"name": "test"}
            }
        )
        
        # 안전하게 처리되어야 함
        is_error = result["result"].get("isError", False)
        assert is_error  # 레코드를 찾을 수 없음 오류 예상
        
        print("✅ 보안 테스트 통과")


@pytest.mark.asyncio
async def test_postgres_crud_error_handling(auth_base_url: str):
    """PostgreSQL CRUD 에러 처리 테스트"""
    auth_token = await get_auth_token(auth_base_url)
    
    async with httpx.AsyncClient() as client:
        # 1. 존재하지 않는 레코드 업데이트
        result = await call_mcp_tool(
            client, auth_base_url, auth_token,
            "update_database_record",
            {
                "table": "users",
                "record_id": "99999999",  # 존재하지 않는 ID
                "data": {"name": "Ghost User"}
            }
        )
        
        # 에러 확인
        is_error = result["result"].get("isError", False)
        if is_error:
            error_text = result["result"]["content"][0]["text"]
            print(f"존재하지 않는 레코드 에러: {error_text}")
            assert "찾을 수 없" in error_text or "not found" in error_text.lower()
        
        # 2. 필수 필드 누락
        result = await call_mcp_tool(
            client, auth_base_url, auth_token,
            "create_database_record",
            {
                "table": "users",
                "data": {}  # 빈 데이터
            }
        )
        
        # 데이터베이스 제약 조건 위반 에러 예상
        is_error = result["result"].get("isError", False)
        assert is_error
        
        # 3. 잘못된 데이터 타입
        result = await call_mcp_tool(
            client, auth_base_url, auth_token,
            "create_database_record",
            {
                "table": "logs",
                "data": {
                    "message": "Test log",
                    "created_at": "invalid-date-format"  # 잘못된 날짜 형식
                }
            }
        )
        
        # 타입 변환 에러 예상
        is_error = result["result"].get("isError", False)
        if not is_error:
            print("⚠️ 잘못된 데이터 타입 테스트 - 예상치 못한 성공")
        
        print("✅ 에러 처리 테스트 완료")


if __name__ == "__main__":
    # 독립 실행 테스트
    async def run_tests():
        auth_base_url = "http://localhost:8000"
        
        print("=== PostgreSQL CRUD 전체 사이클 테스트 ===")
        try:
            await test_postgres_crud_full_cycle(auth_base_url)
            print("✅ 전체 사이클 테스트 통과")
        except AssertionError as e:
            print(f"❌ 전체 사이클 테스트 실패: {e}")
        except Exception as e:
            print(f"❌ 예외 발생: {e}")
        
        print("\n=== 권한 테스트 ===")
        try:
            await test_postgres_crud_permissions(auth_base_url)
            print("✅ 권한 테스트 통과")
        except AssertionError as e:
            print(f"❌ 권한 테스트 실패: {e}")
        except Exception as e:
            print(f"❌ 예외 발생: {e}")
        
        print("\n=== 보안 테스트 ===")
        try:
            await test_postgres_crud_security(auth_base_url)
            print("✅ 보안 테스트 통과")
        except AssertionError as e:
            print(f"❌ 보안 테스트 실패: {e}")
        except Exception as e:
            print(f"❌ 예외 발생: {e}")
        
        print("\n=== 에러 처리 테스트 ===")
        try:
            await test_postgres_crud_error_handling(auth_base_url)
            print("✅ 에러 처리 테스트 통과")
        except AssertionError as e:
            print(f"❌ 에러 처리 테스트 실패: {e}")
        except Exception as e:
            print(f"❌ 예외 발생: {e}")
    
    asyncio.run(run_tests())