#!/bin/bash

# Docker 컨테이너 로그 확인 스크립트

# 색상 정의
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 사용법 출력
usage() {
    echo "사용법: $0 [서비스명] [옵션]"
    echo ""
    echo "서비스명:"
    echo "  auth-gateway  - Auth Gateway 로그"
    echo "  mcp-server    - MCP Server 로그"
    echo "  postgres      - PostgreSQL 로그"
    echo "  qdrant        - Qdrant 로그"
    echo "  redis         - Redis 로그"
    echo "  (생략 시 모든 서비스 로그 표시)"
    echo ""
    echo "옵션:"
    echo "  -f, --follow  실시간 로그 표시"
    echo "  -n <숫자>     표시할 로그 라인 수 (기본값: 100)"
    echo ""
    echo "예시:"
    echo "  $0                    # 모든 서비스 로그"
    echo "  $0 mcp-server -f      # MCP Server 실시간 로그"
    echo "  $0 auth-gateway -n 50 # Auth Gateway 최근 50줄"
    exit 0
}

# 옵션 파싱
SERVICE=""
FOLLOW=""
LINES="100"

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            usage
            ;;
        -f|--follow)
            FOLLOW="--follow"
            shift
            ;;
        -n)
            LINES="$2"
            shift 2
            ;;
        *)
            if [ -z "$SERVICE" ]; then
                SERVICE="$1"
            fi
            shift
            ;;
    esac
done

# docker-compose.yml이 있는 디렉토리로 이동
cd "$(dirname "$0")/.."

# 로그 표시
if [ -z "$SERVICE" ]; then
    echo -e "${BLUE}📋 모든 서비스 로그 (최근 ${LINES}줄)${NC}"
    echo "================================"
    docker-compose logs --tail="$LINES" $FOLLOW
else
    echo -e "${BLUE}📋 ${SERVICE} 로그 (최근 ${LINES}줄)${NC}"
    echo "================================"
    docker-compose logs --tail="$LINES" $FOLLOW "$SERVICE"
fi