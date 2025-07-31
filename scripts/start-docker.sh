#!/bin/bash

# MCP Retriever Docker Compose 시작 스크립트

set -e

echo "🚀 MCP Retriever Docker Compose 시작 스크립트"
echo "=========================================="

# 스크립트가 실행되는 디렉토리로 이동
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/.."

# .env 파일 확인
if [ ! -f .env ]; then
    echo "⚠️  .env 파일이 없습니다. .env.example에서 복사합니다..."
    cp .env.example .env
    echo "✅ .env 파일이 생성되었습니다. 필요한 환경 변수를 설정해주세요:"
    echo "   - TAVILY_API_KEY: Tavily API 키"
    echo "   - JWT_SECRET_KEY: JWT 비밀 키 (프로덕션에서는 반드시 변경)"
    echo ""
    read -p "계속하시겠습니까? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Docker Compose 파일 선택 (루트 레벨 우선)
COMPOSE_FILE="docker-compose.yml"
if [ ! -f "$COMPOSE_FILE" ]; then
    echo "⚠️  루트 레벨 docker-compose.yml 파일이 없습니다. docker/ 디렉토리를 확인합니다."
    COMPOSE_FILE="docker/docker-compose.yml"
fi

if [ ! -f "$COMPOSE_FILE" ]; then
    echo "❌ Docker Compose 파일을 찾을 수 없습니다."
    exit 1
fi

echo "📋 사용할 Docker Compose 파일: $COMPOSE_FILE"

# 옵션 파싱
BUILD_FLAG=""
DETACH_FLAG="-d"

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --build) BUILD_FLAG="--build"; shift ;;
        --no-detach) DETACH_FLAG=""; shift ;;
        --help) 
            echo "사용법: $0 [옵션]"
            echo "옵션:"
            echo "  --build      : 이미지를 다시 빌드합니다"
            echo "  --no-detach  : 백그라운드가 아닌 포그라운드에서 실행합니다"
            echo "  --help       : 이 도움말을 표시합니다"
            exit 0
            ;;
        *) echo "알 수 없는 옵션: $1"; exit 1 ;;
    esac
done

# 기존 컨테이너 정리
echo "🧹 기존 컨테이너 정리 중..."
docker-compose -f "$COMPOSE_FILE" down

# 볼륨 생성 (필요한 경우)
echo "📦 볼륨 확인 중..."
docker volume create postgres_data 2>/dev/null || true
docker volume create qdrant_data 2>/dev/null || true
docker volume create redis_data 2>/dev/null || true

# Docker Compose 시작
echo "🐳 Docker Compose 시작 중..."
docker-compose -f "$COMPOSE_FILE" up $BUILD_FLAG $DETACH_FLAG

# 백그라운드에서 실행된 경우 상태 확인
if [ -n "$DETACH_FLAG" ]; then
    echo ""
    echo "⏳ 서비스가 시작되기를 기다리는 중..."
    sleep 10
    
    echo ""
    echo "📊 컨테이너 상태:"
    docker-compose -f "$COMPOSE_FILE" ps
    
    echo ""
    echo "✅ MCP Retriever 시스템이 시작되었습니다!"
    echo ""
    echo "🌐 접속 정보:"
    echo "   - Auth Gateway: http://localhost:8000"
    echo "   - MCP Server: http://localhost:8001"
    echo "   - PostgreSQL: localhost:5432"
    echo "   - Qdrant: http://localhost:6333"
    echo "   - Redis: localhost:6379"
    echo ""
    echo "📝 로그 확인:"
    echo "   docker-compose -f $COMPOSE_FILE logs -f [서비스명]"
    echo ""
    echo "🛑 종료하려면:"
    echo "   docker-compose -f $COMPOSE_FILE down"
fi