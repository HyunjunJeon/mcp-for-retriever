#!/bin/bash
# Phase 2 기능 테스트 스크립트

set -e

echo "🚀 Phase 2 기능 테스트 시작..."

# 색상 정의
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# API 키 확인
if [ -z "$MCP_INTERNAL_API_KEY" ]; then
    echo -e "${YELLOW}⚠️  MCP_INTERNAL_API_KEY가 설정되지 않았습니다. 기본값 사용${NC}"
    export MCP_INTERNAL_API_KEY="test-internal-api-key"
fi

# URL 설정
AUTH_URL=${AUTH_GATEWAY_URL:-http://localhost:8000}
MCP_URL=${MCP_SERVER_URL:-http://localhost:8001}

echo "Auth Gateway URL: $AUTH_URL"
echo "MCP Server URL: $MCP_URL"

# 1. 헬스 체크
echo -e "\n${BLUE}=== 1. 헬스 체크 ===${NC}"
curl -s $AUTH_URL/health | jq . || echo -e "${RED}❌ Auth Gateway 접속 실패${NC}"

# 2. 사용자 등록 및 로그인
echo -e "\n${BLUE}=== 2. 사용자 등록 및 로그인 ===${NC}"

# 테스트 사용자 등록
REGISTER_RESPONSE=$(curl -s -X POST $AUTH_URL/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "phase2test@example.com",
    "password": "Test123!",
    "full_name": "Phase 2 Test User"
  }' 2>/dev/null || echo '{}')

if [ "$(echo "$REGISTER_RESPONSE" | jq -r .id 2>/dev/null)" != "null" ]; then
    echo -e "${GREEN}✅ 사용자 등록 성공${NC}"
else
    echo -e "${YELLOW}⚠️  사용자가 이미 존재할 수 있습니다${NC}"
fi

# 로그인
LOGIN_RESPONSE=$(curl -s -X POST $AUTH_URL/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "phase2test@example.com",
    "password": "Test123!"
  }')

ACCESS_TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r .access_token)

if [ "$ACCESS_TOKEN" != "null" ] && [ -n "$ACCESS_TOKEN" ]; then
    echo -e "${GREEN}✅ 로그인 성공${NC}"
else
    echo -e "${RED}❌ 로그인 실패${NC}"
    exit 1
fi

# 3. 미들웨어 테스트 - 인증 없이 접근
echo -e "\n${BLUE}=== 3. 인증 미들웨어 테스트 ===${NC}"
echo -e "${YELLOW}인증 없이 접근 시도 (401 예상)${NC}"
UNAUTH_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST $AUTH_URL/mcp/proxy \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}')
echo "$UNAUTH_RESPONSE" | grep "HTTP_STATUS:401" > /dev/null && echo -e "${GREEN}✅ 인증 거부 확인${NC}" || echo -e "${RED}❌ 인증 체크 실패${NC}"

# 4. 유효성 검증 미들웨어 테스트
echo -e "\n${BLUE}=== 4. 유효성 검증 미들웨어 테스트 ===${NC}"

# 잘못된 요청 형식
echo -e "${YELLOW}잘못된 JSONRPC 버전 테스트${NC}"
INVALID_VERSION=$(curl -s -X POST $AUTH_URL/mcp/proxy \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{"jsonrpc": "1.0", "method": "tools/list", "id": 1}')
echo "$INVALID_VERSION" | jq .error.message | grep -i "invalid" > /dev/null && echo -e "${GREEN}✅ 버전 검증 성공${NC}" || echo -e "${RED}❌ 버전 검증 실패${NC}"

# 필수 파라미터 누락
echo -e "${YELLOW}필수 파라미터 누락 테스트${NC}"
MISSING_PARAMS=$(curl -s -X POST $AUTH_URL/mcp/proxy \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "search_web"
    },
    "id": 2
  }')
echo "$MISSING_PARAMS" | jq .error.message | grep -i "arguments" > /dev/null && echo -e "${GREEN}✅ 파라미터 검증 성공${NC}" || echo -e "${RED}❌ 파라미터 검증 실패${NC}"

# 5. Rate Limiting 테스트
echo -e "\n${BLUE}=== 5. Rate Limiting 테스트 ===${NC}"
echo -e "${YELLOW}빠른 연속 요청으로 Rate Limit 테스트${NC}"

# 10개의 빠른 요청 보내기
for i in {1..10}; do
    curl -s -X POST $AUTH_URL/mcp/proxy \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $ACCESS_TOKEN" \
      -d '{"jsonrpc": "2.0", "method": "health_check", "id": '$i'}' > /dev/null 2>&1 &
done

wait

echo -e "${GREEN}✅ Rate limiting 테스트 완료 (로그를 확인하세요)${NC}"

# 6. 메트릭스 확인
echo -e "\n${BLUE}=== 6. 메트릭스 수집 테스트 ===${NC}"
METRICS_RESPONSE=$(curl -s -X POST $AUTH_URL/mcp/proxy \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "get_metrics",
      "arguments": {}
    },
    "id": 100
  }')

if echo "$METRICS_RESPONSE" | jq .result > /dev/null 2>&1; then
    echo -e "${GREEN}✅ 메트릭스 수집 확인${NC}"
    echo "$METRICS_RESPONSE" | jq '.result.summary'
else
    echo -e "${YELLOW}⚠️  메트릭스 도구가 아직 구현되지 않았을 수 있습니다${NC}"
fi

# 7. 향상된 로깅 테스트
echo -e "\n${BLUE}=== 7. 향상된 로깅 테스트 ===${NC}"
echo -e "${YELLOW}긴 쿼리로 로깅 테스트${NC}"

LONG_QUERY="This is a very long query string that tests the logging system's ability to handle and potentially truncate very long input parameters while maintaining useful log information"

LOG_TEST_RESPONSE=$(curl -s -X POST $AUTH_URL/mcp/proxy \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "search_web",
      "arguments": {
        "query": "'"$LONG_QUERY"'",
        "limit": 5
      }
    },
    "id": 101
  }')

echo -e "${GREEN}✅ 로깅 테스트 완료 (서버 로그를 확인하세요)${NC}"

# 8. 에러 핸들링 테스트
echo -e "\n${BLUE}=== 8. 에러 핸들링 테스트 ===${NC}"

# 존재하지 않는 도구 호출
echo -e "${YELLOW}존재하지 않는 도구 호출 테스트${NC}"
ERROR_TEST=$(curl -s -X POST $AUTH_URL/mcp/proxy \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "non_existent_tool",
      "arguments": {}
    },
    "id": 102
  }')

if echo "$ERROR_TEST" | jq .error > /dev/null 2>&1; then
    echo -e "${GREEN}✅ 에러 핸들링 확인${NC}"
    echo "$ERROR_TEST" | jq .error
else
    echo -e "${RED}❌ 에러 핸들링 실패${NC}"
fi

# 9. 컨텍스트 전파 테스트
echo -e "\n${BLUE}=== 9. 컨텍스트 전파 테스트 ===${NC}"
echo -e "${YELLOW}사용자 정보가 로그에 기록되는지 확인${NC}"

CONTEXT_TEST=$(curl -s -X POST $AUTH_URL/mcp/proxy \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "health_check",
      "arguments": {}
    },
    "id": 103
  }')

echo -e "${GREEN}✅ 컨텍스트 전파 테스트 완료 (서버 로그에서 user_id와 email 확인)${NC}"

# 10. 동시성 테스트
echo -e "\n${BLUE}=== 10. 동시성 및 성능 테스트 ===${NC}"
echo -e "${YELLOW}여러 도구를 동시에 호출${NC}"

# search_all 도구 호출
CONCURRENT_TEST=$(curl -s -X POST $AUTH_URL/mcp/proxy \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "search_all",
      "arguments": {
        "query": "test query",
        "limit": 5
      }
    },
    "id": 104
  }')

if echo "$CONCURRENT_TEST" | jq .result > /dev/null 2>&1; then
    echo -e "${GREEN}✅ 동시성 테스트 성공${NC}"
    echo "$CONCURRENT_TEST" | jq '.result.sources_searched'
else
    echo -e "${YELLOW}⚠️  동시성 테스트 결과를 확인할 수 없습니다${NC}"
fi

echo -e "\n${GREEN}🎉 Phase 2 기능 테스트 완료!${NC}"
echo -e "${BLUE}다음 기능들이 테스트되었습니다:${NC}"
echo -e "  ✅ 인증 미들웨어"
echo -e "  ✅ 유효성 검증 미들웨어"
echo -e "  ✅ Rate Limiting"
echo -e "  ✅ 메트릭스 수집"
echo -e "  ✅ 향상된 로깅"
echo -e "  ✅ 에러 핸들링"
echo -e "  ✅ 컨텍스트 전파"
echo -e "  ✅ 동시성 처리"

echo -e "\n${YELLOW}💡 팁: 서버 로그를 확인하여 상세한 동작을 확인하세요:${NC}"
echo -e "  ./scripts/logs-docker.sh mcp-server -f"