#!/bin/bash

# MCP Retriever Docker Compose 로그 확인 스크립트

set -e

# 스크립트가 실행되는 디렉토리로 이동
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/.."

# Docker Compose 파일 선택
COMPOSE_FILE="docker-compose.local.yml"
if [ ! -f "$COMPOSE_FILE" ]; then
    COMPOSE_FILE="docker-compose.yml"
fi

# 서비스 이름 (첫 번째 인수)
SERVICE=$1

# 옵션 파싱
FOLLOW=""
TAIL="100"

shift # 첫 번째 인수 제거

while [[ "$#" -gt 0 ]]; do
    case $1 in
        -f|--follow) FOLLOW="-f"; shift ;;
        -n|--tail) TAIL="$2"; shift 2 ;;
        --help) 
            echo "사용법: $0 [서비스명] [옵션]"
            echo ""
            echo "서비스명:"
            echo "  postgres      : PostgreSQL 데이터베이스"
            echo "  qdrant        : Qdrant 벡터 데이터베이스"
            echo "  redis         : Redis 캐시"
            echo "  auth-gateway  : 인증 게이트웨이"
            echo "  mcp-server    : MCP 서버"
            echo "  (비어있음)     : 모든 서비스"
            echo ""
            echo "옵션:"
            echo "  -f, --follow     : 실시간 로그 추적"
            echo "  -n, --tail <줄수> : 마지막 N줄만 표시 (기본값: 100)"
            echo "  --help           : 이 도움말을 표시합니다"
            exit 0
            ;;
        *) echo "알 수 없는 옵션: $1"; exit 1 ;;
    esac
done

# 로그 표시
if [ -z "$SERVICE" ]; then
    echo "📜 모든 서비스 로그 (마지막 $TAIL 줄)"
    docker-compose -f "$COMPOSE_FILE" logs --tail="$TAIL" $FOLLOW
else
    echo "📜 $SERVICE 서비스 로그 (마지막 $TAIL 줄)"
    docker-compose -f "$COMPOSE_FILE" logs --tail="$TAIL" $FOLLOW "$SERVICE"
fi