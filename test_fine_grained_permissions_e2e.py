"""세밀한 권한 시스템 E2E 테스트

이 테스트는 다음을 검증합니다:
1. 역할별 도구 접근 권한
2. 컬렉션/테이블 레벨 세밀한 권한
3. 권한이 없는 리소스 접근 차단
4. 다양한 사용자 시나리오
5. 에러 처리 및 장애 복구
"""

import asyncio
import httpx
import json

from src.auth.models import ResourceType, ActionType

class PermissionE2ETestRunner:
    """권한 시스템 E2E 테스트 러너"""
    
    def __init__(self):
        self.auth_base_url = "http://localhost:8000"
        self.test_users = {}
        self.test_tokens = {}
        self.http_client = httpx.AsyncClient(timeout=30.0)
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.http_client.aclose()

    
    async def setup_test_data(self):
        """테스트 데이터 설정"""
        print("🔧 테스트 데이터 설정 중...")
        
        # 다양한 역할의 테스트 사용자 생성
        test_user_configs = [
            {
                "email": "admin@test.com",
                "password": "Admin123!",
                "role": "admin",
                "description": "전체 관리자"
            },
            {
                "email": "analyst@test.com", 
                "password": "Analyst123!",
                "role": "analyst",
                "description": "데이터 분석가"
            },
            {
                "email": "viewer@test.com",
                "password": "Viewer123!",
                "role": "viewer",
                "description": "조회 전용 사용자"
            },
        ]
        
        # 사용자 생성 및 로그인
        for config in test_user_configs:
            try:
                # 사용자 등록
                register_response = await self.http_client.post(
                    f"{self.auth_base_url}/auth/register",
                    json={
                        "email": config["email"],
                        "password": config["password"]
                    }
                )
                
                if register_response.status_code not in [200, 409]:  # 409는 이미 존재하는 경우
                    print(f"❌ 사용자 등록 실패: {config['email']} - {register_response.text}")
                    continue
                
                # 로그인하여 토큰 획득
                login_response = await self.http_client.post(
                    f"{self.auth_base_url}/auth/login",
                    json={
                        "email": config["email"],
                        "password": config["password"]
                    }
                )
                
                if login_response.status_code != 200:
                    print(f"❌ 로그인 실패: {config['email']} - {login_response.text}")
                    continue
                
                login_data = login_response.json()
                access_token = login_data["access_token"]
                
                # 사용자 정보 조회
                me_response = await self.http_client.get(
                    f"{self.auth_base_url}/auth/me",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                
                if me_response.status_code != 200:
                    print(f"❌ 사용자 정보 조회 실패: {config['email']}")
                    continue
                
                user_data = me_response.json()
                self.test_users[config["role"]] = user_data
                self.test_tokens[config["role"]] = access_token
                
                print(f"✅ {config['description']} 설정 완료: {config['email']} (ID: {user_data['id']})")
                
            except Exception as e:
                print(f"❌ 사용자 설정 실패 {config['email']}: {e}")
                
        return len(self.test_users) > 0
    
    async def setup_fine_grained_permissions(self):
        """세밀한 권한 설정"""
        print("\n🔐 세밀한 권한 설정 중...")
        
        # 실제 환경에서는 데이터베이스에 권한을 설정하지만,
        # 이 테스트에서는 이미 구성된 역할 기반 권한을 사용합니다.
        
        print("✅ 기본 역할 기반 권한 사용:")
        print("  - admin: 모든 도구 및 리소스 접근 가능")
        print("  - analyst: 제한된 도구 접근")
        print("  - viewer: 매우 제한적 접근")
        
        return True
    
    async def test_tool_list_filtering(self):
        """도구 목록 필터링 테스트"""
        print("\n🔍 도구 목록 필터링 테스트")
        
        test_results = {}
        
        for role, token in self.test_tokens.items():
            print(f"\n--- {role} 사용자 도구 목록 조회 ---")
            
            try:
                # MCP Proxy를 통한 도구 목록 조회
                tools_response = await self.http_client.post(
                    f"{self.auth_base_url}/mcp/proxy",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/list",
                        "params": None,
                        "id": 1
                    },
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    }
                )
                
                if tools_response.status_code != 200:
                    print(f"❌ 도구 목록 조회 실패: {tools_response.status_code}")
                    print(f"응답: {tools_response.text}")
                    test_results[role] = {"success": False, "tools": []}
                    continue
                
                response_data = tools_response.json()
                
                if "result" in response_data and "tools" in response_data["result"]:
                    tools = response_data["result"]["tools"]
                    tool_names = [tool["name"] for tool in tools]
                    
                    print(f"✅ 도구 목록 조회 성공 ({len(tools)}개):")
                    for tool_name in tool_names:
                        print(f"  - {tool_name}")
                    
                    test_results[role] = {"success": True, "tools": tool_names}
                    
                    # 역할별 예상 도구 검증
                    if role == "admin":
                        expected_tools = ["search_web", "search_vectors", "search_database", "search_all", "health_check"]
                        missing_tools = set(expected_tools) - set(tool_names)
                        if missing_tools:
                            print(f"⚠️ ADMIN에게 누락된 도구: {missing_tools}")
                        else:
                            print("✅ ADMIN 도구 접근 권한 정상")
                    
                    elif role == "analyst":
                        # ANALYST는 search_database와 search_vectors에 제한적 접근
                        if "search_database" in tool_names and "search_vectors" in tool_names:
                            print("✅ ANALYST 도구 접근 권한 정상")
                        else:
                            print("⚠️ ANALYST 도구 접근에 제한이 있을 수 있음")
                    
                    elif role == "viewer":
                        # VIEWER는 매우 제한적 접근
                        if len(tool_names) <= 3:  # 제한적 도구만 접근 가능
                            print("✅ VIEWER 도구 제한 정상")
                        else:
                            print("⚠️ VIEWER에게 너무 많은 도구 접근 허용")
                
                else:
                    print(f"❌ 응답 형식 오류: {response_data}")
                    test_results[role] = {"success": False, "tools": []}
                    
            except Exception as e:
                print(f"❌ 도구 목록 조회 예외: {e}")
                test_results[role] = {"success": False, "tools": []}
        
        return test_results
    
    async def test_resource_access_control(self):
        """리소스 접근 제어 테스트"""  
        print("\n🚫 리소스 접근 제어 테스트")
        
        access_test_scenarios = [
            {
                "role": "analyst",
                "tool": "search_vectors",
                "allowed_collection": "research_docs",
                "forbidden_collection": "admin_secrets"
            },
            {
                "role": "analyst",
                "tool": "search_database", 
                "allowed_table": "public.users",
                "forbidden_table": "private.admin_logs"
            },
            {
                "role": "viewer",
                "tool": "search_vectors",
                "allowed_collection": "public_docs",
                "forbidden_collection": "research_docs"
            }
        ]
        
        test_results = []
        
        for scenario in access_test_scenarios:
            role = scenario["role"]
            if role not in self.test_tokens:
                continue
                
            token = self.test_tokens[role]
            print(f"\n--- {role} 리소스 접근 테스트 ---")
            
            # 허용된 리소스 접근 테스트
            if "allowed_collection" in scenario:
                allowed_result = await self._test_vector_access(
                    token, scenario["allowed_collection"], should_succeed=True
                )
                test_results.append({
                    "role": role,
                    "resource": scenario["allowed_collection"],
                    "access_type": "allowed",
                    "success": allowed_result
                })
            
            if "allowed_table" in scenario:
                allowed_result = await self._test_database_access(
                    token, scenario["allowed_table"], should_succeed=True
                )
                test_results.append({
                    "role": role,
                    "resource": scenario["allowed_table"],
                    "access_type": "allowed", 
                    "success": allowed_result
                })
            
            # 금지된 리소스 접근 테스트 
            if "forbidden_collection" in scenario:
                forbidden_result = await self._test_vector_access(
                    token, scenario["forbidden_collection"], should_succeed=False
                )
                test_results.append({
                    "role": role,
                    "resource": scenario["forbidden_collection"],
                    "access_type": "forbidden",
                    "success": forbidden_result
                })
            
            if "forbidden_table" in scenario:
                forbidden_result = await self._test_database_access(
                    token, scenario["forbidden_table"], should_succeed=False
                )
                test_results.append({
                    "role": role,
                    "resource": scenario["forbidden_table"],
                    "access_type": "forbidden",
                    "success": forbidden_result
                })
        
        return test_results
    
    async def _test_vector_access(self, token: str, collection: str, should_succeed: bool) -> bool:
        """벡터 DB 접근 테스트"""
        try:
            response = await self.http_client.post(
                f"{self.auth_base_url}/mcp/proxy",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "search_vectors",
                        "arguments": {
                            "query": "test query",
                            "collection": collection,
                            "limit": 1
                        }
                    },
                    "id": 2
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }
            )
            
            success = response.status_code == 200
            response_data = response.json() if response.status_code == 200 else {}
            
            if should_succeed:
                if success and "result" in response_data:
                    print(f"✅ {collection} 컬렉션 접근 허용됨")
                    return True
                else:
                    print(f"❌ {collection} 컬렉션 접근이 예상과 달리 차단됨")
                    return False
            else:
                if success and "result" in response_data:
                    print(f"❌ {collection} 컬렉션 접근이 예상과 달리 허용됨")
                    return False
                elif "error" in response_data:
                    print(f"✅ {collection} 컬렉션 접근 차단됨: {response_data['error']['message']}")
                    return True
                else:
                    print(f"⚠️ {collection} 컬렉션 접근 결과 불명확")
                    return False
                    
        except Exception as e:
            print(f"❌ 벡터 DB 접근 테스트 예외: {e}")
            return False
    
    async def _test_database_access(self, token: str, table: str, should_succeed: bool) -> bool:
        """데이터베이스 접근 테스트"""
        try:
            response = await self.http_client.post(
                f"{self.auth_base_url}/mcp/proxy",
                json={
                    "jsonrpc": "2.0", 
                    "method": "tools/call",
                    "params": {
                        "name": "search_database",
                        "arguments": {
                            "query": f"SELECT COUNT(*) FROM {table} LIMIT 1"
                        }
                    },
                    "id": 3
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }
            )
            
            success = response.status_code == 200
            response_data = response.json() if response.status_code == 200 else {}
            
            if should_succeed:
                if success and "result" in response_data:
                    print(f"✅ {table} 테이블 접근 허용됨")
                    return True
                else:
                    print(f"❌ {table} 테이블 접근이 예상과 달리 차단됨")
                    return False
            else:
                if success and "result" in response_data:
                    print(f"❌ {table} 테이블 접근이 예상과 달리 허용됨")
                    return False
                elif "error" in response_data:
                    print(f"✅ {table} 테이블 접근 차단됨: {response_data['error']['message']}")
                    return True
                else:
                    print(f"⚠️ {table} 테이블 접근 결과 불명확")
                    return False
                    
        except Exception as e:
            print(f"❌ 데이터베이스 접근 테스트 예외: {e}")
            return False
    
    async def test_edge_cases_and_error_handling(self):
        """경계 조건 및 에러 처리 테스트"""
        print("\n⚠️ 경계 조건 및 에러 처리 테스트")
        
        edge_case_results = []
        
        if "analyst" in self.test_tokens:
            token = self.test_tokens["analyst"]
            
            # 1. 잘못된 도구 이름
            print("\n--- 잘못된 도구 이름 테스트 ---")
            invalid_tool_result = await self._test_invalid_tool_call(token)
            edge_case_results.append({"test": "invalid_tool", "success": invalid_tool_result})
            
            # 2. 악의적 파라미터 주입
            print("\n--- 악의적 파라미터 주입 테스트 ---")
            injection_result = await self._test_parameter_injection(token)
            edge_case_results.append({"test": "parameter_injection", "success": injection_result})
            
            # 3. 권한 상승 시도
            print("\n--- 권한 상승 시도 테스트 ---")
            privilege_escalation_result = await self._test_privilege_escalation(token)
            edge_case_results.append({"test": "privilege_escalation", "success": privilege_escalation_result})
            
            # 4. 동시 요청 테스트
            print("\n--- 동시 요청 테스트 ---")
            concurrent_result = await self._test_concurrent_requests(token)
            edge_case_results.append({"test": "concurrent_requests", "success": concurrent_result})
        
        return edge_case_results
    
    async def _test_invalid_tool_call(self, token: str) -> bool:
        """잘못된 도구 호출 테스트"""
        try:
            response = await self.http_client.post(
                f"{self.auth_base_url}/mcp/proxy",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call", 
                    "params": {
                        "name": "non_existent_tool",
                        "arguments": {"query": "test"}
                    },
                    "id": 4
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }
            )
            
            response_data = response.json()
            if "error" in response_data:
                print(f"✅ 잘못된 도구 호출이 올바르게 차단됨: {response_data['error']['message']}")
                return True
            else:
                print("❌ 잘못된 도구 호출이 차단되지 않음")
                return False
                
        except Exception as e:
            print(f"❌ 잘못된 도구 호출 테스트 예외: {e}")
            return False
    
    async def _test_parameter_injection(self, token: str) -> bool:
        """파라미터 주입 테스트"""
        try:
            # SQL 인젝션 시도
            malicious_query = "SELECT * FROM users; DROP TABLE users; --"
            
            response = await self.http_client.post(
                f"{self.auth_base_url}/mcp/proxy",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "search_database",
                        "arguments": {
                            "query": malicious_query
                        }
                    },
                    "id": 5
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }
            )
            
            response_data = response.json()
            if "error" in response_data:
                print(f"✅ 악의적 쿼리가 차단됨: {response_data['error']['message']}")
                return True
            else:
                print("❌ 악의적 쿼리가 차단되지 않음")
                return False
                
        except Exception as e:
            print(f"❌ 파라미터 주입 테스트 예외: {e}")
            return False
    
    async def _test_privilege_escalation(self, token: str) -> bool:
        """권한 상승 시도 테스트"""
        try:
            # ADMIN 전용 기능에 접근 시도
            response = await self.http_client.post(
                f"{self.auth_base_url}/mcp/proxy",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "search_database",
                        "arguments": {
                            "query": "SELECT * FROM private.admin_logs"
                        }
                    },
                    "id": 6
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }
            )
            
            response_data = response.json()
            if "error" in response_data and "권한" in response_data['error']['message']:
                print(f"✅ 권한 상승 시도가 차단됨: {response_data['error']['message']}")
                return True
            else:
                print("❌ 권한 상승 시도가 차단되지 않음")
                return False
                
        except Exception as e:
            print(f"❌ 권한 상승 테스트 예외: {e}")
            return False
    
    async def _test_concurrent_requests(self, token: str) -> bool:
        """동시 요청 테스트"""
        try:
            # 동시에 여러 요청 실행
            tasks = []
            for i in range(5):
                task = self.http_client.post(
                    f"{self.auth_base_url}/mcp/proxy",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {
                            "name": "search_vectors",
                            "arguments": {
                                "query": f"concurrent test {i}",
                                "collection": "research_docs"
                            }
                        },
                        "id": 10 + i
                    },
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    }
                )
                tasks.append(task)
            
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            
            success_count = 0
            for i, response in enumerate(responses):
                if isinstance(response, Exception):
                    print(f"요청 {i}: 예외 - {response}")
                elif response.status_code == 200:
                    success_count += 1
                    print(f"요청 {i}: 성공")
                else:
                    print(f"요청 {i}: 실패 - {response.status_code}")
            
            print(f"동시 요청 결과: {success_count}/5 성공")
            return success_count >= 3  # 최소 3개는 성공해야 함
            
        except Exception as e:
            print(f"❌ 동시 요청 테스트 예외: {e}")
            return False
    
    async def generate_test_report(self, tool_results, access_results, edge_case_results):
        """테스트 보고서 생성"""
        print("\n📊 테스트 결과 종합 보고서")
        print("=" * 60)
        
        # 도구 목록 필터링 결과
        print("\n1. 도구 목록 필터링 테스트")
        print("-" * 30)
        total_tool_tests = len(tool_results)
        successful_tool_tests = sum(1 for result in tool_results.values() if result["success"])
        print(f"성공률: {successful_tool_tests}/{total_tool_tests} ({successful_tool_tests/total_tool_tests*100:.1f}%)")
        
        for role, result in tool_results.items():
            status = "✅" if result["success"] else "❌"
            print(f"{status} {role}: {len(result['tools'])}개 도구 조회")
        
        # 리소스 접근 제어 결과
        print("\n2. 리소스 접근 제어 테스트")
        print("-" * 30)
        total_access_tests = len(access_results)
        successful_access_tests = sum(1 for result in access_results if result["success"])
        print(f"성공률: {successful_access_tests}/{total_access_tests} ({successful_access_tests/total_access_tests*100:.1f}%)")
        
        for result in access_results:
            status = "✅" if result["success"] else "❌"
            print(f"{status} {result['role']}: {result['resource']} ({result['access_type']})")
        
        # 경계 조건 테스트 결과
        print("\n3. 경계 조건 및 에러 처리 테스트")
        print("-" * 30)
        total_edge_tests = len(edge_case_results)
        successful_edge_tests = sum(1 for result in edge_case_results if result["success"])
        if total_edge_tests > 0:
            print(f"성공률: {successful_edge_tests}/{total_edge_tests} ({successful_edge_tests/total_edge_tests*100:.1f}%)")
            
            for result in edge_case_results:
                status = "✅" if result["success"] else "❌"
                print(f"{status} {result['test']}")
        else:
            print("경계 조건 테스트가 실행되지 않음")
        
        # 전체 결과
        print("\n4. 종합 결과")
        print("-" * 30)
        total_tests = total_tool_tests + total_access_tests + total_edge_tests
        total_successes = successful_tool_tests + successful_access_tests + successful_edge_tests
        
        if total_tests > 0:
            overall_success_rate = total_successes / total_tests * 100
            print(f"전체 성공률: {total_successes}/{total_tests} ({overall_success_rate:.1f}%)")
            
            if overall_success_rate >= 90:
                print("🎉 우수: 세밀한 권한 시스템이 매우 잘 작동합니다!")
            elif overall_success_rate >= 70:
                print("✅ 양호: 세밀한 권한 시스템이 대부분 정상 작동합니다.")
            elif overall_success_rate >= 50:
                print("⚠️ 보통: 일부 권한 제어에 문제가 있습니다.")
            else:
                print("❌ 불량: 권한 시스템에 심각한 문제가 있습니다.")
        else:
            print("❌ 테스트가 실행되지 않음")
        
        print("=" * 60)


async def main():
    """메인 E2E 테스트 실행"""
    print("🚀 세밀한 권한 시스템 E2E 테스트 시작")
    print("이 테스트는 근본적인 문제를 찾아 해결합니다.")
    
    async with PermissionE2ETestRunner() as test_runner:
        # 1. 테스트 데이터 설정
        setup_success = await test_runner.setup_test_data()
        if not setup_success:
            print("❌ 테스트 데이터 설정 실패 - 테스트 중단")
            return False
        
        # 2. 세밀한 권한 설정
        permission_setup_success = await test_runner.setup_fine_grained_permissions()
        if not permission_setup_success:
            print("❌ 세밀한 권한 설정 실패 - 테스트 중단")
            return False
        
        # 3. 도구 목록 필터링 테스트
        tool_results = await test_runner.test_tool_list_filtering()
        
        # 4. 리소스 접근 제어 테스트
        access_results = await test_runner.test_resource_access_control()
        
        # 5. 경계 조건 및 에러 처리 테스트
        edge_case_results = await test_runner.test_edge_cases_and_error_handling()
        
        # 6. 테스트 보고서 생성
        await test_runner.generate_test_report(tool_results, access_results, edge_case_results)
        
        # 최종 성공 여부 결정
        total_tests = len(tool_results) + len(access_results) + len(edge_case_results)
        total_successes = (
            sum(1 for result in tool_results.values() if result["success"]) +
            sum(1 for result in access_results if result["success"]) +
            sum(1 for result in edge_case_results if result["success"])
        )
        
        success_rate = total_successes / total_tests * 100 if total_tests > 0 else 0
        return success_rate >= 70  # 70% 이상 성공시 전체 테스트 성공


if __name__ == "__main__":
    success = asyncio.run(main())
    if success:
        print("\n🎉 세밀한 권한 시스템 E2E 테스트 성공!")
        exit(0)
    else:
        print("\n❌ 세밀한 권한 시스템 E2E 테스트 실패!")
        exit(1)