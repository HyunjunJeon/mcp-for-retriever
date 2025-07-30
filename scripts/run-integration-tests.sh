#!/bin/bash

# Docker 환경에서 통합 테스트 실행 스크립트

set -e

echo "🧪 Docker 통합 테스트 실행"
echo "========================"

# 스크립트가 실행되는 디렉토리로 이동
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/.."

# 색상 정의
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Docker 상태 확인
echo "🐳 Docker 상태 확인 중..."
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}❌ Docker가 실행되지 않고 있습니다. Docker Desktop을 시작해주세요.${NC}"
    exit 1
fi

# 서비스 상태 확인
echo "📊 서비스 상태 확인 중..."
docker-compose -f docker-compose.local.yml ps

# 서비스가 모두 실행 중인지 확인
services=("mcp-postgres" "mcp-qdrant" "mcp-redis" "mcp-auth-gateway" "mcp-server")
all_running=true

for service in "${services[@]}"; do
    if ! docker ps --format "table {{.Names}}" | grep -q "^${service}$"; then
        echo -e "${RED}❌ ${service}가 실행되지 않고 있습니다.${NC}"
        all_running=false
    fi
done

if [ "$all_running" = false ]; then
    echo -e "${YELLOW}⚠️  일부 서비스가 실행되지 않고 있습니다.${NC}"
    echo "다음 명령으로 서비스를 시작하세요:"
    echo "  ./scripts/start-docker.sh"
    exit 1
fi

echo -e "${GREEN}✅ 모든 서비스가 실행 중입니다.${NC}"

# 서비스가 준비될 때까지 대기
echo "⏳ 서비스가 준비되기를 기다리는 중..."
sleep 5

# 기본 헬스체크
echo ""
echo "🏥 기본 헬스체크 실행..."
./scripts/test-services.sh

# Python 통합 테스트 실행
echo ""
echo "🧪 Python 통합 테스트 실행..."

# 가상환경이 활성화되어 있는지 확인
if [ -z "$VIRTUAL_ENV" ]; then
    echo "가상환경 활성화 중..."
    source .venv/bin/activate 2>/dev/null || {
        echo -e "${YELLOW}⚠️  가상환경이 없습니다. uv를 사용하여 실행합니다.${NC}"
        UV_RUN="uv run"
    }
else
    UV_RUN=""
fi

# pytest 실행
echo ""
if [ -n "$1" ] && [ "$1" = "--verbose" ]; then
    $UV_RUN pytest tests/integration/test_docker_integration.py -v -s
else
    $UV_RUN pytest tests/integration/test_docker_integration.py -v
fi

# 테스트 결과
if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✅ 모든 통합 테스트가 성공했습니다!${NC}"
    echo ""
    echo "📋 다음 단계:"
    echo "   - API 문서 확인: http://localhost:8000/docs"
    echo "   - Qdrant 대시보드: http://localhost:6333/dashboard"
    echo "   - 로그 확인: ./scripts/logs-docker.sh [서비스명]"
else
    echo ""
    echo -e "${RED}❌ 일부 테스트가 실패했습니다.${NC}"
    echo ""
    echo "🔍 디버깅을 위한 명령어:"
    echo "   - 서비스 로그: ./scripts/logs-docker.sh [서비스명]"
    echo "   - 컨테이너 상태: docker-compose -f docker-compose.local.yml ps"
    echo "   - 상세 테스트: $0 --verbose"
    exit 1
fi