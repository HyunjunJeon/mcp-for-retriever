#!/bin/bash

# SSE 통합 테스트 실행 스크립트

echo "🚀 SSE 프록시 통합 테스트 시작..."

# 환경 변수 설정
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
export LOG_LEVEL="INFO"
export ENVIRONMENT="test"

# 색상 코드
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 서비스 상태 확인
check_service() {
    local name=$1
    local url=$2
    
    if curl -s -o /dev/null -w "%{http_code}" "$url" | grep -E "200|404" > /dev/null; then
        echo -e "${GREEN}✅ $name is running${NC}"
        return 0
    else
        echo -e "${RED}❌ $name is not running${NC}"
        return 1
    fi
}

echo "📋 서비스 상태 확인..."
services_ok=true

if ! check_service "Auth Gateway" "http://localhost:8000/health"; then
    services_ok=false
fi

# MCP Server는 FastMCP로 HTTP 스트리밍만 지원하므로 포트 확인
if nc -z localhost 8001 2>/dev/null; then
    echo -e "${GREEN}✅ MCP Server is running (port 8001)${NC}"
else
    echo -e "${RED}❌ MCP Server is not running${NC}"
    services_ok=false
fi

if [ "$services_ok" = false ]; then
    echo -e "${YELLOW}⚠️  일부 서비스가 실행되지 않았습니다.${NC}"
    echo "다음 명령으로 서비스를 시작하세요:"
    echo "  ./scripts/start-docker.sh"
    exit 1
fi

# 테스트 실행 옵션 파싱
VERBOSE=""
SPECIFIC_TEST=""
MARKERS=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--verbose)
            VERBOSE="-v"
            shift
            ;;
        -vv|--very-verbose)
            VERBOSE="-vv"
            shift
            ;;
        -k|--test)
            SPECIFIC_TEST="-k $2"
            shift 2
            ;;
        -m|--marker)
            MARKERS="-m $2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [-v|--verbose] [-k|--test TEST_NAME] [-m|--marker MARKER]"
            exit 1
            ;;
    esac
done

# 테스트 실행
echo ""
echo "🧪 SSE 통합 테스트 실행 중..."

# pytest 실행
uv run pytest tests/integration/test_sse_integration.py \
    $VERBOSE \
    $SPECIFIC_TEST \
    $MARKERS \
    --tb=short \
    --disable-warnings \
    --asyncio-mode=auto

# 결과 확인
if [ $? -eq 0 ]; then
    echo -e "\n${GREEN}✅ 모든 SSE 통합 테스트가 성공했습니다!${NC}"
else
    echo -e "\n${RED}❌ 일부 테스트가 실패했습니다.${NC}"
    exit 1
fi

# 개별 SSE 테스트도 실행 (선택적)
if [ -z "$SPECIFIC_TEST" ]; then
    echo ""
    echo "📋 추가 SSE 테스트 실행..."
    
    # 기존 SSE 테스트들도 실행
    for test_file in tests/integration/mcp_tests/test_sse*.py; do
        if [ -f "$test_file" ]; then
            echo -e "\n🔄 실행: $(basename $test_file)"
            uv run pytest "$test_file" -v --tb=short --disable-warnings --asyncio-mode=auto
        fi
    done
fi

echo -e "\n✨ SSE 테스트 완료!"