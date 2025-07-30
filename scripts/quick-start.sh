#!/bin/bash

# 빠른 시작 스크립트
# 통합 서버를 다양한 모드로 쉽게 시작할 수 있습니다.

set -e

# 색상 정의
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

clear

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════╗"
echo "║       MCP 통합 서버 빠른 시작 도구       ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${NC}"

# 스크립트가 실행되는 디렉토리로 이동
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/.."

# .env 파일 확인
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠️  .env 파일이 없습니다.${NC}"
    echo ""
    read -p ".env.example에서 복사하시겠습니까? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cp .env.example .env
        echo -e "${GREEN}✅ .env 파일이 생성되었습니다.${NC}"
        echo ""
        echo "다음 환경 변수를 설정해주세요:"
        echo "  - TAVILY_API_KEY: Tavily API 키 (웹 검색용)"
        echo "  - MCP_INTERNAL_API_KEY: 내부 API 키 (최소 32자)"
        echo "  - JWT_SECRET_KEY: JWT 시크릿 키 (최소 32자)"
        echo ""
        read -p "지금 설정하시겠습니까? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            ${EDITOR:-nano} .env
        fi
    else
        exit 1
    fi
fi

# 메뉴 표시
echo -e "${BLUE}실행할 서버 프로파일을 선택하세요:${NC}"
echo ""
echo "1) BASIC    - 기본 서버 (인증 없음, 빠른 테스트용)"
echo "2) AUTH     - 인증 서버 (JWT 인증 활성화)"
echo "3) CONTEXT  - 컨텍스트 서버 (인증 + 사용자 추적)"
echo "4) CACHED   - 캐싱 서버 (인증 + Redis 캐싱)"
echo "5) COMPLETE - 완전 통합 서버 (모든 기능 활성화)"
echo "6) CUSTOM   - 사용자 정의 (환경 변수로 설정)"
echo ""
echo "0) 종료"
echo ""

read -p "선택 [0-6]: " choice

case $choice in
    1)
        PROFILE="BASIC"
        DESC="기본 서버"
        ;;
    2)
        PROFILE="AUTH"
        DESC="인증 서버"
        ;;
    3)
        PROFILE="CONTEXT"
        DESC="컨텍스트 서버"
        ;;
    4)
        PROFILE="CACHED"
        DESC="캐싱 서버"
        # Redis 확인
        echo ""
        echo -e "${YELLOW}📦 Redis 연결을 확인합니다...${NC}"
        if ! redis-cli ping > /dev/null 2>&1; then
            echo -e "${RED}❌ Redis가 실행 중이지 않습니다.${NC}"
            echo ""
            echo "Redis를 시작하려면:"
            echo "  - macOS: brew services start redis"
            echo "  - Linux: sudo systemctl start redis"
            echo "  - Docker: docker run -d -p 6379:6379 redis"
            exit 1
        fi
        echo -e "${GREEN}✅ Redis 연결 확인됨${NC}"
        ;;
    5)
        PROFILE="COMPLETE"
        DESC="완전 통합 서버"
        ;;
    6)
        PROFILE="CUSTOM"
        DESC="사용자 정의"
        echo ""
        echo -e "${YELLOW}환경 변수로 기능을 설정하세요:${NC}"
        echo "  MCP_ENABLE_AUTH=true"
        echo "  MCP_ENABLE_CACHE=true"
        echo "  MCP_ENABLE_CONTEXT=true"
        echo "  MCP_ENABLE_RATE_LIMIT=true"
        echo "  MCP_ENABLE_METRICS=true"
        echo ""
        ;;
    0)
        echo -e "${YELLOW}종료합니다.${NC}"
        exit 0
        ;;
    *)
        echo -e "${RED}잘못된 선택입니다.${NC}"
        exit 1
        ;;
esac

# 전송 모드 선택
echo ""
echo -e "${BLUE}전송 모드를 선택하세요:${NC}"
echo ""
echo "1) STDIO - 표준 입출력 (직접 통신)"
echo "2) HTTP  - HTTP/SSE 서버 (Claude Desktop, 웹 API 등에서 사용)"
echo ""

read -p "선택 [1-2]: " transport_choice

case $transport_choice in
    1)
        TRANSPORT="stdio"
        ;;
    2)
        TRANSPORT="http"
        read -p "포트 번호 (기본값: 8001): " PORT
        PORT=${PORT:-8001}
        ;;
    *)
        echo -e "${RED}잘못된 선택입니다.${NC}"
        exit 1
        ;;
esac

# 실행 확인
echo ""
echo -e "${GREEN}다음 설정으로 서버를 시작합니다:${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "프로파일: ${CYAN}$PROFILE${NC} ($DESC)"
echo -e "전송 모드: ${CYAN}$TRANSPORT${NC}"
if [ "$TRANSPORT" = "http" ]; then
    echo -e "포트: ${CYAN}$PORT${NC}"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

read -p "계속하시겠습니까? (y/n) " -n 1 -r
echo

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}취소되었습니다.${NC}"
    exit 0
fi

# 서버 실행
echo ""
echo -e "${GREEN}🚀 서버를 시작합니다...${NC}"
echo ""

if [ "$TRANSPORT" = "http" ]; then
    ./scripts/run-unified-server.sh --profile "$PROFILE" --transport "$TRANSPORT" --port "$PORT"
else
    ./scripts/run-unified-server.sh --profile "$PROFILE" --transport "$TRANSPORT"
fi