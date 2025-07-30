#!/bin/bash

# MCP Retriever Docker Compose 종료 스크립트

set -e

echo "🛑 MCP Retriever Docker Compose 종료 스크립트"
echo "==========================================="

# 스크립트가 실행되는 디렉토리로 이동
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/.."

# Docker Compose 파일 선택
COMPOSE_FILE="docker-compose.local.yml"
if [ ! -f "$COMPOSE_FILE" ]; then
    COMPOSE_FILE="docker-compose.yml"
fi

echo "📋 사용할 Docker Compose 파일: $COMPOSE_FILE"

# 옵션 파싱
REMOVE_VOLUMES=""

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --volumes) REMOVE_VOLUMES="-v"; shift ;;
        --help) 
            echo "사용법: $0 [옵션]"
            echo "옵션:"
            echo "  --volumes : 볼륨도 함께 삭제합니다"
            echo "  --help    : 이 도움말을 표시합니다"
            exit 0
            ;;
        *) echo "알 수 없는 옵션: $1"; exit 1 ;;
    esac
done

# 컨테이너 종료
echo "🔌 컨테이너 종료 중..."
docker-compose -f "$COMPOSE_FILE" down $REMOVE_VOLUMES

if [ -n "$REMOVE_VOLUMES" ]; then
    echo "🗑️  볼륨이 삭제되었습니다."
fi

echo "✅ MCP Retriever 시스템이 종료되었습니다."