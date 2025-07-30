#!/bin/bash

# 로컬 환경에서 서비스 실행 및 테스트 (Docker 없이)

set -e

echo "🏃 로컬 환경 테스트 (Docker 없이)"
echo "================================"

# 스크립트가 실행되는 디렉토리로 이동
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/.."

# 색상 정의
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# .env 파일 확인
if [ ! -f .env ]; then
    echo "⚠️  .env 파일이 없습니다. .env.example에서 복사합니다..."
    cp .env.example .env
fi

# 환경 변수 로드
export $(cat .env | grep -v '^#' | xargs)

# PID 파일 디렉토리
PID_DIR=".pids"
mkdir -p "$PID_DIR"

# 서비스 종료 함수
cleanup() {
    echo ""
    echo "🛑 서비스 종료 중..."
    
    # Auth 서버 종료
    if [ -f "$PID_DIR/auth.pid" ]; then
        kill $(cat "$PID_DIR/auth.pid") 2>/dev/null || true
        rm "$PID_DIR/auth.pid"
    fi
    
    # MCP 서버 종료
    if [ -f "$PID_DIR/mcp.pid" ]; then
        kill $(cat "$PID_DIR/mcp.pid") 2>/dev/null || true
        rm "$PID_DIR/mcp.pid"
    fi
    
    echo "✅ 서비스가 종료되었습니다."
}

# 종료 시 cleanup 실행
trap cleanup EXIT

# Auth 서버 시작
echo "🚀 Auth Gateway 시작 중..."
uv run python -m src.auth.server > "$PID_DIR/auth.log" 2>&1 &
echo $! > "$PID_DIR/auth.pid"

# MCP 서버 시작 (HTTP 모드) - 통합 서버 사용
echo "🚀 MCP Server 시작 중 (HTTP 모드)..."
MCP_PROFILE=COMPLETE MCP_TRANSPORT=http MCP_SERVER_PORT=8001 uv run python -m src.server_unified > "$PID_DIR/mcp.log" 2>&1 &
echo $! > "$PID_DIR/mcp.pid"

# 서비스가 시작될 때까지 대기
echo "⏳ 서비스가 시작되기를 기다리는 중..."
sleep 5

# 헬스체크
echo ""
echo "🏥 헬스체크 실행..."

# Auth Gateway 헬스체크
echo -n "🔍 Auth Gateway 헬스체크... "
if curl -s -f http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ 성공${NC}"
else
    echo -e "${RED}❌ 실패${NC}"
    echo "Auth 서버 로그:"
    tail -n 20 "$PID_DIR/auth.log"
fi

# MCP Server 체크
echo -n "🔍 MCP Server 체크... "
if curl -s -f -X POST http://localhost:8001/ \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}' > /dev/null 2>&1; then
    echo -e "${GREEN}✅ 성공${NC}"
else
    echo -e "${RED}❌ 실패${NC}"
    echo "MCP 서버 로그:"
    tail -n 20 "$PID_DIR/mcp.log"
fi

# 간단한 통합 테스트
echo ""
echo "🧪 간단한 통합 테스트 실행..."

# 1. Auth 테스트
echo -n "🔐 로그인 테스트... "
login_response=$(curl -s -X POST http://localhost:8000/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email": "admin@example.com", "password": "Admin123!"}' 2>/dev/null)

if echo "$login_response" | grep -q "access_token"; then
    echo -e "${GREEN}✅ 성공${NC}"
    ACCESS_TOKEN=$(echo "$login_response" | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)
else
    echo -e "${RED}❌ 실패${NC}"
fi

# 2. MCP 도구 목록 테스트
echo -n "🔧 MCP 도구 목록 조회... "
tools_response=$(curl -s -X POST http://localhost:8001/ \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}' 2>/dev/null)

if echo "$tools_response" | grep -q "search_web"; then
    echo -e "${GREEN}✅ 성공${NC}"
else
    echo -e "${RED}❌ 실패${NC}"
    echo "응답: $tools_response"
fi

# Python 테스트 실행 옵션
echo ""
read -p "Python 통합 테스트를 실행하시겠습니까? (y/n) " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "🧪 Python 통합 테스트 실행..."
    uv run python tests/integration/test_docker_integration.py
fi

echo ""
echo "📋 로그 확인:"
echo "   - Auth 서버: tail -f $PID_DIR/auth.log"
echo "   - MCP 서버: tail -f $PID_DIR/mcp.log"
echo ""
echo "🛑 종료하려면 Ctrl+C를 누르세요..."

# 서비스 유지
wait