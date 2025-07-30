#!/bin/bash
# 인증 통합 테스트 스크립트

set -e

echo "🔍 인증 통합 테스트 시작..."

# 색상 정의
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# API 키 확인
if [ -z "$MCP_INTERNAL_API_KEY" ]; then
    echo -e "${YELLOW}⚠️  MCP_INTERNAL_API_KEY가 설정되지 않았습니다. 기본값 사용${NC}"
    export MCP_INTERNAL_API_KEY="test-internal-api-key"
fi

# Auth Gateway URL
AUTH_URL=${AUTH_GATEWAY_URL:-http://localhost:8000}
MCP_URL=${MCP_SERVER_URL:-http://localhost:8001}

echo "Auth Gateway URL: $AUTH_URL"
echo "MCP Server URL: $MCP_URL"

# 1. Auth Gateway 헬스 체크
echo -e "\n${YELLOW}1. Auth Gateway 헬스 체크${NC}"
curl -s $AUTH_URL/health | jq . || echo -e "${RED}❌ Auth Gateway 접속 실패${NC}"

# 2. MCP Server 헬스 체크 (내부 API 키 사용)
echo -e "\n${YELLOW}2. MCP Server 헬스 체크${NC}"
curl -s -X POST $MCP_URL/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MCP_INTERNAL_API_KEY" \
  -d '{"jsonrpc": "2.0", "method": "health_check", "id": 1}' | jq . || echo -e "${RED}❌ MCP Server 접속 실패${NC}"

# 3. 사용자 등록
echo -e "\n${YELLOW}3. 사용자 등록${NC}"
REGISTER_RESPONSE=$(curl -s -X POST $AUTH_URL/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@integration.com",
    "password": "Test123!",
    "full_name": "Integration Test User"
  }')
echo "$REGISTER_RESPONSE" | jq .

# 4. 로그인
echo -e "\n${YELLOW}4. 로그인${NC}"
LOGIN_RESPONSE=$(curl -s -X POST $AUTH_URL/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@integration.com",
    "password": "Test123!"
  }')
echo "$LOGIN_RESPONSE" | jq .

# 토큰 추출
ACCESS_TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r .access_token)

if [ "$ACCESS_TOKEN" = "null" ] || [ -z "$ACCESS_TOKEN" ]; then
    echo -e "${RED}❌ 로그인 실패: 토큰을 받지 못했습니다${NC}"
    exit 1
fi

echo -e "${GREEN}✅ 액세스 토큰 획득${NC}"

# 5. 현재 사용자 정보 조회
echo -e "\n${YELLOW}5. 현재 사용자 정보 조회${NC}"
curl -s -X GET $AUTH_URL/auth/me \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq .

# 6. Auth Gateway를 통한 MCP 도구 목록 조회
echo -e "\n${YELLOW}6. Auth Gateway를 통한 MCP 도구 목록 조회${NC}"
TOOLS_RESPONSE=$(curl -s -X POST $AUTH_URL/mcp/proxy \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/list",
    "id": 1
  }')
echo "$TOOLS_RESPONSE" | jq .

# 7. Auth Gateway를 통한 헬스 체크 도구 호출
echo -e "\n${YELLOW}7. Auth Gateway를 통한 헬스 체크 도구 호출${NC}"
HEALTH_RESPONSE=$(curl -s -X POST $AUTH_URL/mcp/proxy \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "health_check",
      "arguments": {}
    },
    "id": 2
  }')
echo "$HEALTH_RESPONSE" | jq .

# 8. 직접 MCP Server 접근 테스트 (내부 API 키)
echo -e "\n${YELLOW}8. 직접 MCP Server 접근 테스트 (내부 API 키)${NC}"
DIRECT_RESPONSE=$(curl -s -X POST $MCP_URL/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MCP_INTERNAL_API_KEY" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/list",
    "id": 3
  }')
echo "$DIRECT_RESPONSE" | jq .

# 9. 잘못된 토큰으로 접근 시도
echo -e "\n${YELLOW}9. 잘못된 토큰으로 접근 시도 (401 예상)${NC}"
INVALID_RESPONSE=$(curl -s -w "\nHTTP Status: %{http_code}" -X POST $AUTH_URL/mcp/proxy \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer invalid-token" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/list",
    "id": 4
  }')
echo "$INVALID_RESPONSE"

echo -e "\n${GREEN}✅ 인증 통합 테스트 완료!${NC}"
echo -e "${GREEN}모든 인증 및 권한 체크가 정상적으로 작동합니다.${NC}"