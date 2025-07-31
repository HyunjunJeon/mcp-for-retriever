#!/bin/bash
# 테스트용 서버 시작 스크립트

echo "=== 테스트 서버 시작 ==="

# 환경 변수 설정
export JWT_SECRET_KEY="test-secret-key"
export MCP_INTERNAL_API_KEY="test-internal-key"
export TAVILY_API_KEY="test-tavily-key"
export MCP_TRANSPORT="http"

# Qdrant 메모리 모드 설정
export QDRANT_HOST=":memory:"
export QDRANT_PORT="6333"

# 기존 프로세스 종료
pkill -f "auth.server" 2>/dev/null || true
pkill -f "server_unified" 2>/dev/null || true

sleep 1

# Auth Gateway 시작
echo "Auth Gateway 시작..."
uv run python -m src.auth.server > auth_test.log 2>&1 &
AUTH_PID=$!
echo "Auth Gateway PID: $AUTH_PID"

sleep 2

# MCP Server 시작
echo "MCP Server 시작..."
uv run python -m src.server_unified > mcp_test.log 2>&1 &
MCP_PID=$!
echo "MCP Server PID: $MCP_PID"

sleep 2

# 상태 확인
echo ""
echo "서버 상태:"
if ps -p $AUTH_PID > /dev/null; then
    echo "✅ Auth Gateway 실행 중 (PID: $AUTH_PID)"
else
    echo "❌ Auth Gateway 시작 실패"
fi

if ps -p $MCP_PID > /dev/null; then
    echo "✅ MCP Server 실행 중 (PID: $MCP_PID)"
else
    echo "❌ MCP Server 시작 실패"
fi

echo ""
echo "테스트 완료 후 다음 명령으로 서버 종료:"
echo "kill $AUTH_PID $MCP_PID"

# PID 파일 저장
echo "$AUTH_PID $MCP_PID" > test_server_pids.txt