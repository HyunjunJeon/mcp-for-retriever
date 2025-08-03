#!/bin/bash

# E2E 테스트 실행 스크립트

set -e

echo "🧪 MCP Retriever E2E 테스트 실행"

# 환경 변수 설정
export PLAYWRIGHT_HEADLESS=${PLAYWRIGHT_HEADLESS:-true}
export AUTH_URL=${AUTH_URL:-http://localhost:8000}
export MCP_URL=${MCP_URL:-http://localhost:8001}

# Docker 서비스 상태 확인
echo "📋 Docker 서비스 상태 확인..."
if ! docker ps | grep -q "mcp-auth-gateway"; then
    echo "❌ Auth Gateway 서비스가 실행되지 않았습니다."
    echo "   ./scripts/start-docker.sh 명령으로 서비스를 시작하세요."
    exit 1
fi

if ! docker ps | grep -q "mcp-server"; then
    echo "❌ MCP Server 서비스가 실행되지 않았습니다."
    echo "   ./scripts/start-docker.sh 명령으로 서비스를 시작하세요."
    exit 1
fi

echo "✅ Docker 서비스가 실행 중입니다."

# 서비스 상태 확인
echo "🔍 서비스 헬스 체크..."
timeout 30 bash -c 'until curl -f http://localhost:8000/health > /dev/null 2>&1; do echo "Auth Gateway 대기 중..."; sleep 2; done'
timeout 30 bash -c 'until curl -f http://localhost:8001/health > /dev/null 2>&1; do echo "MCP Server 대기 중..."; sleep 2; done'

echo "✅ 모든 서비스가 준비되었습니다."

# Playwright 브라우저 설치 확인
echo "🌐 Playwright 브라우저 확인..."
if ! uv run playwright install --help > /dev/null 2>&1; then
    echo "📥 Playwright 의존성 설치 중..."
    uv add --dev playwright
fi

echo "📥 Playwright 브라우저 설치 중..."
uv run playwright install chromium

# E2E 테스트 실행
echo "🚀 E2E 테스트 시작..."

# 테스트 인자 처리
TEST_ARGS="$@"
if [ -z "$TEST_ARGS" ]; then
    TEST_ARGS="tests/e2e/"
fi

# pytest 실행
uv run pytest \
    $TEST_ARGS \
    -v \
    --tb=short \
    --capture=no \
    --maxfail=5 \
    -m "e2e" \
    --browser=chromium \
    --headed=${PLAYWRIGHT_HEADLESS:-false}

echo "✅ E2E 테스트 완료!"