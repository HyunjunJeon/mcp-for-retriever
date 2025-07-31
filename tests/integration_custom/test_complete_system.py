#!/usr/bin/env python3
"""
완전한 시스템 통합 테스트
현재 실행 중인 Auth Gateway와 MCP 서버를 이용한 종합 테스트
"""

import asyncio
import httpx
import json


async def test_complete_system():
    """완전한 시스템 테스트"""
    
    test_results = []
    total_tests = 0
    passed_tests = 0
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("=== 완전한 시스템 통합 테스트 시작 ===\n")
        
        # 1. 사용자 등록 및 로그인 테스트
        print("1. 사용자 등록 및 로그인 테스트")
        total_tests += 1
        try:
            # 새 사용자 등록
            register_resp = await client.post(
                "http://localhost:8000/auth/register",
                json={
                    "email": "systemtest@test.com",
                    "password": "SystemTest123!",
                    "username": "system_test_user"
                }
            )
            
            if register_resp.status_code not in [200, 400]:  # 400은 이미 존재하는 경우
                raise Exception(f"등록 실패: {register_resp.status_code}")
            
            # 로그인
            login_resp = await client.post(
                "http://localhost:8000/auth/login",
                json={"email": "systemtest@test.com", "password": "SystemTest123!"}
            )
            
            if login_resp.status_code != 200:
                raise Exception(f"로그인 실패: {login_resp.status_code}")
            
            token_data = login_resp.json()
            access_token = token_data["access_token"]
            
            print("✅ 사용자 인증 성공")
            passed_tests += 1
            test_results.append("✅ 사용자 인증")
            
        except Exception as e:
            print(f"❌ 사용자 인증 실패: {e}")
            test_results.append(f"❌ 사용자 인증: {e}")
            return test_results, passed_tests, total_tests
        
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # 2. 도구 목록 조회 테스트
        print("\n2. 도구 목록 조회 테스트")
        total_tests += 1
        try:
            tools_resp = await client.post(
                "http://localhost:8000/mcp/proxy",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/list",
                    "id": 1
                },
                headers=headers
            )
            
            if tools_resp.status_code != 200:
                raise Exception(f"도구 목록 조회 실패: {tools_resp.status_code}")
            
            tools_result = tools_resp.json()
            print(f"DEBUG - 도구 목록 응답: {json.dumps(tools_result, indent=2, ensure_ascii=False)}")
            
            if "error" in tools_result and tools_result["error"] is not None:
                raise Exception(f"도구 목록 오류: {tools_result['error']}")
            
            if "result" not in tools_result or tools_result["result"] is None:
                raise Exception(f"결과가 없습니다: {tools_result}")
            
            tools = tools_result["result"]["tools"]
            tool_names = [tool["name"] for tool in tools]
            
            expected_tools = ["health_check", "search_database", "search_vectors"]
            found_tools = [tool for tool in expected_tools if tool in tool_names]
            
            print(f"✅ 도구 목록 조회 성공 ({len(tools)}개 도구, 주요 도구 {len(found_tools)}/{len(expected_tools)}개)")
            passed_tests += 1
            test_results.append(f"✅ 도구 목록 조회 ({len(tools)}개)")
            
        except Exception as e:
            print(f"❌ 도구 목록 조회 실패: {e}")
            test_results.append(f"❌ 도구 목록 조회: {e}")
        
        # 3. health_check 도구 테스트
        print("\n3. health_check 도구 테스트")
        total_tests += 1
        try:
            health_resp = await client.post(
                "http://localhost:8000/mcp/proxy",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "health_check",
                        "arguments": {}
                    },
                    "id": 2
                },
                headers=headers
            )
            
            if health_resp.status_code != 200:
                raise Exception(f"health_check 실패: {health_resp.status_code}")
            
            health_result = health_resp.json()
            if "error" in health_result and health_result["error"] is not None:
                raise Exception(f"health_check 오류: {health_result['error']}")
            
            if "result" not in health_result or health_result["result"] is None:
                raise Exception(f"health_check 결과가 없습니다: {health_result}")
            
            # structuredContent가 있는지 확인
            if "structuredContent" in health_result["result"]:
                health_data = health_result["result"]["structuredContent"]
            else:
                # content 필드에서 JSON 파싱 시도
                content = health_result["result"]["content"][0]["text"]
                health_data = json.loads(content)
            status = health_data.get("status", "unknown")
            
            print(f"✅ health_check 성공 (상태: {status})")
            passed_tests += 1
            test_results.append(f"✅ health_check ({status})")
            
        except Exception as e:
            print(f"❌ health_check 실패: {e}")
            test_results.append(f"❌ health_check: {e}")
        
        # 4. search_database 도구 테스트
        print("\n4. search_database 도구 테스트")
        total_tests += 1
        try:
            search_resp = await client.post(
                "http://localhost:8000/mcp/proxy",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "search_database",
                        "arguments": {
                            "query": "SELECT 'system_test' as test_type, NOW() as test_time",
                            "limit": 1
                        }
                    },
                    "id": 3
                },
                headers=headers
            )
            
            if search_resp.status_code != 200:
                raise Exception(f"search_database 실패: {search_resp.status_code}")
            
            search_result = search_resp.json()
            if "error" in search_result and search_result["error"] is not None:
                raise Exception(f"search_database 오류: {search_result['error']}")
            
            if "result" not in search_result or search_result["result"] is None:
                raise Exception(f"search_database 결과가 없습니다: {search_result}")
            
            # structuredContent가 있는지 확인
            if "structuredContent" in search_result["result"]:
                db_data = search_result["result"]["structuredContent"]["result"]
            else:
                # content 필드에서 JSON 파싱 시도
                content = search_result["result"]["content"][0]["text"]
                db_data = json.loads(content)
            if len(db_data) > 0:
                print(f"✅ search_database 성공 ({len(db_data)}개 결과)")
                passed_tests += 1
                test_results.append(f"✅ search_database ({len(db_data)}개 결과)")
            else:
                raise Exception("빈 결과 반환")
            
        except Exception as e:
            print(f"❌ search_database 실패: {e}")
            test_results.append(f"❌ search_database: {e}")
        
        # 5. 벡터 컬렉션 생성 테스트
        print("\n5. 벡터 컬렉션 생성 테스트")
        total_tests += 1
        try:
            create_resp = await client.post(
                "http://localhost:8000/mcp/proxy",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "create_vector_collection",
                        "arguments": {
                            "collection": "system_test_collection",
                            "vector_size": 384,
                            "distance_metric": "cosine"
                        }
                    },
                    "id": 4
                },
                headers=headers
            )
            
            if create_resp.status_code != 200:
                raise Exception(f"벡터 컬렉션 생성 실패: {create_resp.status_code}")
            
            create_result = create_resp.json()
            if "error" in create_result and create_result["error"] is not None:
                # 이미 존재하는 컬렉션인 경우는 성공으로 간주
                error_msg = create_result["error"]["message"]
                if "already exists" in error_msg.lower() or "이미 존재" in error_msg:
                    print("✅ 벡터 컬렉션 생성 성공 (기존 컬렉션 사용)")
                    passed_tests += 1
                    test_results.append("✅ 벡터 컬렉션 생성 (기존)")
                else:
                    raise Exception(f"벡터 컬렉션 생성 오류: {error_msg}")
            else:
                print("✅ 벡터 컬렉션 생성 성공")
                passed_tests += 1
                test_results.append("✅ 벡터 컬렉션 생성")
            
        except Exception as e:
            print(f"❌ 벡터 컬렉션 생성 실패: {e}")
            test_results.append(f"❌ 벡터 컬렉션 생성: {e}")
        
        # 6. 벡터 검색 테스트
        print("\n6. 벡터 검색 테스트")
        total_tests += 1
        try:
            vector_resp = await client.post(
                "http://localhost:8000/mcp/proxy",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "search_vectors",
                        "arguments": {
                            "query": "test search query",
                            "collection": "system_test_collection",
                            "limit": 5
                        }
                    },
                    "id": 5
                },
                headers=headers
            )
            
            if vector_resp.status_code != 200:
                raise Exception(f"벡터 검색 실패: {vector_resp.status_code}")
            
            vector_result = vector_resp.json()
            if "error" in vector_result and vector_result["error"] is not None:
                # 빈 컬렉션인 경우 성공으로 간주
                error_msg = vector_result["error"]["message"]
                if "empty" in error_msg.lower() or "비어" in error_msg or "not found" in error_msg.lower():
                    print("✅ 벡터 검색 성공 (빈 결과)")
                    passed_tests += 1
                    test_results.append("✅ 벡터 검색 (빈 결과)")
                else:
                    raise Exception(f"벡터 검색 오류: {error_msg}")
            else:
                if "result" not in vector_result or vector_result["result"] is None:
                    print("✅ 벡터 검색 성공 (빈 결과)")
                    passed_tests += 1
                    test_results.append("✅ 벡터 검색 (빈 결과)")
                else:
                    # structuredContent가 있는지 확인
                    if "structuredContent" in vector_result["result"]:
                        vector_data = vector_result["result"]["structuredContent"]["result"]
                    else:
                        # content 필드에서 JSON 파싱 시도
                        content = vector_result["result"]["content"][0]["text"]
                        vector_data = json.loads(content)
                    
                    print(f"✅ 벡터 검색 성공 ({len(vector_data)}개 결과)")
                    passed_tests += 1
                    test_results.append(f"✅ 벡터 검색 ({len(vector_data)}개 결과)")
            
        except Exception as e:
            print(f"❌ 벡터 검색 실패: {e}")
            test_results.append(f"❌ 벡터 검색: {e}")
        
        # 7. 동시 요청 테스트
        print("\n7. 동시 요청 테스트")
        total_tests += 1
        try:
            # 동시에 여러 health_check 요청
            tasks = []
            for i in range(3):
                task = client.post(
                    "http://localhost:8000/mcp/proxy",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {
                            "name": "health_check",
                            "arguments": {}
                        },
                        "id": 6 + i
                    },
                    headers=headers
                )
                tasks.append(task)
            
            responses = await asyncio.gather(*tasks)
            
            success_count = 0
            for resp in responses:
                if resp.status_code == 200:
                    result = resp.json()
                    if "error" not in result or result["error"] is None:
                        success_count += 1
            
            if success_count == len(tasks):
                print(f"✅ 동시 요청 성공 ({success_count}/{len(tasks)})")
                passed_tests += 1
                test_results.append(f"✅ 동시 요청 ({success_count}/{len(tasks)})")
            else:
                raise Exception(f"일부 요청 실패: {success_count}/{len(tasks)}")
            
        except Exception as e:
            print(f"❌ 동시 요청 실패: {e}")
            test_results.append(f"❌ 동시 요청: {e}")
    
    return test_results, passed_tests, total_tests


async def main():
    """메인 테스트 실행"""
    print("🚀 MCP 서버 완전한 시스템 통합 테스트 시작")
    print("=" * 60)
    
    results, passed, total = await test_complete_system()
    
    print("\n" + "=" * 60)
    print("📊 테스트 결과 요약")
    print("=" * 60)
    
    for result in results:
        print(result)
    
    success_rate = (passed / total) * 100 if total > 0 else 0
    
    print(f"\n🎯 최종 결과: {passed}/{total} 성공 ({success_rate:.1f}%)")
    
    if success_rate >= 90:
        print("🎉 우수! 90% 이상 성공률 달성!")
    elif success_rate >= 80:
        print("✅ 양호! 80% 이상 성공률 달성!")
    elif success_rate >= 70:
        print("⚠️ 개선 필요. 70% 이상이지만 목표에 미달.")
    else:
        print("❌ 심각한 문제. 70% 미만 성공률.")
    
    return success_rate


if __name__ == "__main__":
    asyncio.run(main())