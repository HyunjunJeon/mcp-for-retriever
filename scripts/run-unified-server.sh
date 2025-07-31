#!/bin/bash

# 통합 MCP 서버 실행 스크립트
# 다양한 프로파일로 서버를 쉽게 실행할 수 있습니다.

set -e

# 색상 정의
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 기본값
PROFILE="BASIC"
TRANSPORT="stdio"
PORT="8001"

# 사용법 출력
usage() {
    echo "사용법: $0 [옵션]"
    echo ""
    echo "옵션:"
    echo "  -p, --profile <PROFILE>  서버 프로파일 (BASIC|AUTH|CONTEXT|CACHED|COMPLETE|CUSTOM)"
    echo "                          기본값: BASIC"
    echo "  -t, --transport <MODE>   전송 모드 (stdio|http)"
    echo "                          기본값: stdio"
    echo "  --port <PORT>           HTTP 포트 (http 모드에서만 사용)"
    echo "                          기본값: 8001"
    echo "  -e, --env <FILE>        환경 변수 파일"
    echo "  -h, --help              이 도움말 표시"
    echo ""
    echo "프로파일 설명:"
    echo "  BASIC    - 최소 기능 (인증 없음)"
    echo "  AUTH     - 인증 기능 활성화"
    echo "  CONTEXT  - 인증 + 컨텍스트 추적"
    echo "  CACHED   - 인증 + Redis 캐싱"
    echo "  COMPLETE - 모든 기능 활성화"
    echo "  CUSTOM   - 환경 변수로 개별 설정"
    echo ""
    echo "예시:"
    echo "  $0 --profile COMPLETE --transport http"
    echo "  $0 -p AUTH -t stdio"
    echo "  $0 -p CUSTOM  # .env 파일에서 MCP_ENABLE_* 변수로 개별 기능 제어"
    exit 0
}

# 옵션 파싱
while [[ $# -gt 0 ]]; do
    case $1 in
        -p|--profile)
            PROFILE="$2"
            shift 2
            ;;
        -t|--transport)
            TRANSPORT="$2"
            shift 2
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        -e|--env)
            ENV_FILE="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "알 수 없는 옵션: $1"
            usage
            ;;
    esac
done

# 스크립트가 실행되는 디렉토리로 이동
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/.."

# .env 파일 확인 및 로드
if [ -n "$ENV_FILE" ]; then
    if [ ! -f "$ENV_FILE" ]; then
        echo -e "${RED}❌ 환경 변수 파일을 찾을 수 없습니다: $ENV_FILE${NC}"
        exit 1
    fi
    echo -e "${BLUE}📋 환경 변수 파일 로드: $ENV_FILE${NC}"
    export $(cat "$ENV_FILE" | grep -v '^#' | xargs)
elif [ -f .env ]; then
    echo -e "${BLUE}📋 기본 .env 파일 로드${NC}"
    export $(cat .env | grep -v '^#' | xargs)
else
    echo -e "${YELLOW}⚠️  .env 파일이 없습니다. 환경 변수를 직접 설정해주세요.${NC}"
fi

# 환경 변수 설정
export MCP_PROFILE="$PROFILE"
export MCP_TRANSPORT="$TRANSPORT"
export MCP_SERVER_PORT="$PORT"

# 프로파일별 필수 환경 변수 확인
case $PROFILE in
    AUTH|CONTEXT|CACHED|COMPLETE)
        if [ -z "$MCP_INTERNAL_API_KEY" ]; then
            echo -e "${YELLOW}⚠️  MCP_INTERNAL_API_KEY가 설정되지 않았습니다.${NC}"
            echo "설정 예시: export MCP_INTERNAL_API_KEY=your-secure-api-key-at-least-32-chars"
        fi
        if [ -z "$JWT_SECRET_KEY" ]; then
            echo -e "${YELLOW}⚠️  JWT_SECRET_KEY가 설정되지 않았습니다.${NC}"
            echo "설정 예시: export JWT_SECRET_KEY=your-secure-jwt-key-at-least-32-chars"
        fi
        ;;
esac

# 실행 정보 출력
echo ""
echo -e "${GREEN}🚀 통합 MCP 서버 시작${NC}"
echo "================================"
echo -e "프로파일: ${BLUE}$PROFILE${NC}"
echo -e "전송 모드: ${BLUE}$TRANSPORT${NC}"
if [ "$TRANSPORT" = "http" ]; then
    echo -e "HTTP 포트: ${BLUE}$PORT${NC}"
fi
echo ""

# 프로파일별 활성화된 기능 출력
echo -e "${YELLOW}📋 활성화된 기능:${NC}"
case $PROFILE in
    BASIC)
        echo "  - 기본 검색 도구"
        echo "  - 에러 핸들러"
        ;;
    AUTH)
        echo "  - 기본 검색 도구"
        echo "  - JWT 기반 인증"
        echo "  - 유효성 검사"
        echo "  - 향상된 로깅"
        ;;
    CONTEXT)
        echo "  - 기본 검색 도구"
        echo "  - JWT 기반 인증"
        echo "  - 컨텍스트 추적"
        echo "  - 메트릭 수집"
        echo "  - 유효성 검사"
        ;;
    CACHED)
        echo "  - 기본 검색 도구"
        echo "  - JWT 기반 인증"
        echo "  - Redis 캐싱"
        echo "  - 캐시 관리 도구"
        echo "  - 유효성 검사"
        ;;
    COMPLETE)
        echo "  - 모든 기능 활성화"
        echo "  - 인증, 컨텍스트, 캐싱"
        echo "  - 속도 제한, 메트릭"
        echo "  - 모든 도구 사용 가능"
        ;;
    CUSTOM)
        echo "  - 환경 변수로 개별 설정"
        ;;
esac
echo ""

# 서버 실행
echo -e "${GREEN}▶️  서버 실행 중...${NC}"
echo ""

# 실행 명령어 출력 (디버깅용)
echo -e "${BLUE}실행 명령어:${NC}"
echo "uv run python -m src.server_unified"
echo ""

# 서버 실행
exec uv run python -m src.server_unified