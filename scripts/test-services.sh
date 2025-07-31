#!/bin/bash

# MCP Retriever 서비스 테스트 스크립트

set -e

echo "🧪 MCP Retriever 서비스 테스트"
echo "=============================="

# 색상 정의
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 테스트 함수
test_service() {
    local service_name=$1
    local url=$2
    local expected_status=${3:-200}
    
    echo -n "🔍 $service_name 테스트 중... "
    
    response=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "000")
    
    if [ "$response" = "$expected_status" ]; then
        echo -e "${GREEN}✅ 성공${NC} (상태 코드: $response)"
        return 0
    else
        echo -e "${RED}❌ 실패${NC} (상태 코드: $response, 예상: $expected_status)"
        return 1
    fi
}

# 서비스가 시작될 때까지 대기
echo "⏳ 서비스가 시작되기를 기다리는 중..."
sleep 5

# 서비스 테스트
echo ""
echo "📡 서비스 연결 테스트:"
echo "----------------------"

# PostgreSQL 테스트
echo -n "🔍 PostgreSQL 테스트 중... "
if docker exec mcp-postgres pg_isready -U mcp_user -d mcp_retriever > /dev/null 2>&1; then
    echo -e "${GREEN}✅ 성공${NC}"
else
    echo -e "${RED}❌ 실패${NC}"
fi

# Redis 테스트
echo -n "🔍 Redis 테스트 중... "
if docker exec mcp-redis redis-cli ping > /dev/null 2>&1; then
    echo -e "${GREEN}✅ 성공${NC}"
else
    echo -e "${RED}❌ 실패${NC}"
fi

# HTTP 서비스 테스트
test_service "Qdrant 헬스체크" "http://localhost:6333/health"
test_service "Auth Gateway 헬스체크" "http://localhost:8000/health"
test_service "MCP Server" "http://localhost:8001" "404"  # FastMCP는 루트에서 404 반환

echo ""
echo "🔐 Auth API 테스트:"
echo "-------------------"

# 기본 사용자로 로그인 테스트
echo -n "🔍 기본 관리자 로그인 테스트 중... "
login_response=$(curl -s -X POST "http://localhost:8000/auth/login" \
    -H "Content-Type: application/json" \
    -d '{
        "email": "admin@example.com",
        "password": "Admin123!"
    }' 2>/dev/null)

if echo "$login_response" | grep -q "access_token"; then
    echo -e "${GREEN}✅ 성공${NC}"
    
    # 토큰 추출
    ACCESS_TOKEN=$(echo "$login_response" | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)
    
    # 토큰으로 사용자 정보 조회
    echo -n "🔍 토큰 검증 테스트 중... "
    me_response=$(curl -s -X GET "http://localhost:8000/auth/me" \
        -H "Authorization: Bearer $ACCESS_TOKEN" 2>/dev/null)
    
    if echo "$me_response" | grep -q "admin@example.com"; then
        echo -e "${GREEN}✅ 성공${NC}"
    else
        echo -e "${RED}❌ 실패${NC}"
    fi
else
    echo -e "${RED}❌ 실패${NC}"
fi

echo ""
echo "🔧 MCP 도구 테스트:"
echo "------------------"

# MCP 도구 목록 조회 (HTTP 모드에서는 다른 엔드포인트 사용)
echo -n "🔍 MCP 도구 목록 조회 중... "
tools_response=$(curl -s -X POST "http://localhost:8001/" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer your-internal-api-key-change-in-production" \
    -d '{
        "jsonrpc": "2.0",
        "method": "tools/list",
        "id": 1
    }' 2>/dev/null)

if echo "$tools_response" | grep -q "search_web\|search_vectors\|search_database"; then
    echo -e "${GREEN}✅ 성공${NC}"
    echo -e "${YELLOW}   발견된 도구: search_web, search_vectors, search_database, search_all, health_check${NC}"
else
    echo -e "${RED}❌ 실패${NC}"
    echo "   응답: $tools_response"
fi

echo ""
echo "📊 테스트 완료!"
echo ""
echo "💡 추가 테스트를 위한 명령어:"
echo "   - 컨테이너 상태: docker-compose ps"
echo "   - 로그 확인: ./scripts/logs-docker.sh [서비스명]"
echo "   - API 문서: http://localhost:8000/docs (Auth Gateway)"
echo "   - 통합 테스트: uv run python tests/integration_custom/test_complete_system.py"