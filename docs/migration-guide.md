# MCP 서버 통합 마이그레이션 가이드

## 📋 개요

MCP 서버가 하나의 통합 서버(`server_unified.py`)로 리팩토링되었습니다. 이 가이드는 기존 서버 파일에서 새로운 통합 서버로 마이그레이션하는 방법을 설명합니다.

## 🔄 변경 사항

### 이전 구조 (4개의 개별 서버)
- `server_auth.py` - 인증 서버
- `server_context.py` - 컨텍스트 추적 서버
- `server_with_cache.py` - 캐싱 서버
- `server_complete.py` - 완전 통합 서버

### 새로운 구조 (1개의 통합 서버)
- `server_unified.py` - 프로파일 기반 통합 서버
- `config/` - 중앙 집중식 설정 관리
- 레거시 호환 파일들 (Deprecation 경고 포함)

## 🚀 빠른 시작

### 1. 프로파일을 사용한 실행

```bash
# 기본 서버 (인증 없음)
MCP_PROFILE=BASIC python -m src.server_unified

# 인증 서버 (기존 server_auth.py와 동일)
MCP_PROFILE=AUTH python -m src.server_unified

# 컨텍스트 서버 (기존 server_context.py와 동일)
MCP_PROFILE=CONTEXT python -m src.server_unified

# 캐싱 서버 (기존 server_with_cache.py와 동일)
MCP_PROFILE=CACHED python -m src.server_unified

# 완전 통합 서버 (기존 server_complete.py와 동일)
MCP_PROFILE=COMPLETE python -m src.server_unified
```

### 2. 환경 변수 파일 사용

```bash
# 프로파일별 환경 변수 파일 사용
cp .env.auth .env
python -m src.server_unified

# 또는 직접 지정
python -m src.server_unified --env .env.complete
```

### 3. 커스텀 설정

```bash
# 개별 기능 활성화/비활성화
MCP_PROFILE=CUSTOM \
  MCP_ENABLE_AUTH=true \
  MCP_ENABLE_CACHE=true \
  MCP_ENABLE_RATE_LIMIT=false \
  python -m src.server_unified
```

## 📝 상세 마이그레이션 가이드

### server_auth.py → 통합 서버

#### 기존 방식
```bash
python -m src.server_auth
```

#### 새로운 방식
```bash
# 방법 1: 프로파일 사용
MCP_PROFILE=AUTH python -m src.server_unified

# 방법 2: 환경 변수 파일
cp .env.auth .env
python -m src.server_unified

# 방법 3: 개별 설정
MCP_ENABLE_AUTH=true \
MCP_INTERNAL_API_KEY=your-key \
AUTH_GATEWAY_URL=http://localhost:8000 \
python -m src.server_unified
```

### server_context.py → 통합 서버

#### 기존 방식
```bash
python -m src.server_context
```

#### 새로운 방식
```bash
# 방법 1: 프로파일 사용
MCP_PROFILE=CONTEXT python -m src.server_unified

# 방법 2: AUTH + CONTEXT 기능 활성화
MCP_ENABLE_AUTH=true \
MCP_ENABLE_CONTEXT=true \
MCP_ENABLE_METRICS=true \
python -m src.server_unified
```

### server_with_cache.py → 통합 서버

#### 기존 방식
```bash
python -m src.server_with_cache
```

#### 새로운 방식
```bash
# 방법 1: 프로파일 사용
MCP_PROFILE=CACHED python -m src.server_unified

# 방법 2: 캐싱 설정 직접 지정
MCP_ENABLE_CACHE=true \
REDIS_URL=redis://localhost:6379/0 \
CACHE_TTL_WEB=300 \
CACHE_TTL_VECTOR=900 \
CACHE_TTL_DB=600 \
python -m src.server_unified
```

### server_complete.py → 통합 서버

#### 기존 방식
```bash
python -m src.server_complete
```

#### 새로운 방식
```bash
# 방법 1: 프로파일 사용 (권장)
MCP_PROFILE=COMPLETE python -m src.server_unified

# 방법 2: 환경 변수 파일
cp .env.complete .env
python -m src.server_unified
```

## 🐳 Docker 마이그레이션

### 기존 Dockerfile
```dockerfile
# 각 서버별 개별 실행
CMD ["python", "-m", "src.server_auth"]
CMD ["python", "-m", "src.server_complete"]
```

### 새로운 Dockerfile
```dockerfile
# 프로파일 기반 실행
ENV MCP_PROFILE=COMPLETE
CMD ["python", "-m", "src.server_unified"]
```

### docker-compose.yml 업데이트
```yaml
services:
  mcp-server:
    image: mcp-retriever:latest
    environment:
      - MCP_PROFILE=COMPLETE  # 원하는 프로파일 설정
      - MCP_INTERNAL_API_KEY=${MCP_INTERNAL_API_KEY}
      - TAVILY_API_KEY=${TAVILY_API_KEY}
      # ... 기타 환경 변수
    command: ["python", "-m", "src.server_unified"]
```

## 🔧 설정 옵션

### 프로파일 옵션

| 프로파일 | 설명 | 활성화된 기능 |
|---------|------|-------------|
| BASIC | 기본 서버 | 최소 기능만 활성화 |
| AUTH | 인증 서버 | 인증, 유효성 검사, 로깅 |
| CONTEXT | 컨텍스트 서버 | 인증 + 컨텍스트 추적, 메트릭 |
| CACHED | 캐싱 서버 | 인증 + Redis 캐싱 |
| COMPLETE | 완전 통합 서버 | 모든 기능 활성화 |
| CUSTOM | 사용자 정의 | 환경 변수로 개별 설정 |

### 기능 플래그

| 환경 변수 | 설명 | 기본값 |
|----------|------|--------|
| MCP_ENABLE_AUTH | 인증 기능 활성화 | false |
| MCP_ENABLE_CONTEXT | 컨텍스트 추적 활성화 | false |
| MCP_ENABLE_CACHE | Redis 캐싱 활성화 | false |
| MCP_ENABLE_RATE_LIMIT | 속도 제한 활성화 | false |
| MCP_ENABLE_METRICS | 메트릭 수집 활성화 | false |
| MCP_ENABLE_VALIDATION | 요청 검증 활성화 | false |
| MCP_ENABLE_ERROR_HANDLER | 에러 처리 활성화 | true |
| MCP_ENABLE_ENHANCED_LOGGING | 향상된 로깅 활성화 | false |

## ⚠️ 주의사항

### 1. 기존 서버 파일 제거됨

**중요**: 기존 서버 파일들(`server_auth.py`, `server_context.py`, `server_with_cache.py`, `server_complete.py`)은 완전히 제거되었습니다.

- 하위 호환성 없음
- 반드시 `server_unified.py`를 사용해야 함
- 원본 파일은 `src/old/` 폴더에서 참조 가능

### 2. 환경 변수 우선순위

1. 명령줄에서 직접 설정한 환경 변수
2. .env 파일의 환경 변수
3. 프로파일 기본값
4. 시스템 기본값

### 3. 설정 검증

통합 서버는 시작 시 설정을 자동으로 검증합니다:

- 필수 API 키 확인
- 설정 간 의존성 확인
- 보안 설정 검증

## 🔍 문제 해결

### 1. ImportError 발생

```bash
[ERROR] 통합 서버를 로드할 수 없습니다: No module named 'src.config'
```

**해결 방법:**
```bash
# 의존성 재설치
uv sync

# 또는
pip install -e .
```

### 2. 설정 검증 실패

```bash
[ERROR] 설정 검증 실패: ['인증이 활성화되었지만 MCP_INTERNAL_API_KEY가 설정되지 않음']
```

**해결 방법:**
```bash
# 필수 환경 변수 설정
export MCP_INTERNAL_API_KEY=your-secure-key
```

### 3. 기능이 작동하지 않음

**확인 사항:**
1. 올바른 프로파일을 사용하고 있는지 확인
2. 필요한 기능이 활성화되어 있는지 확인
3. 환경 변수가 올바르게 설정되어 있는지 확인

```bash
# 현재 설정 확인
python -c "from src.config import ServerConfig; print(ServerConfig.from_env().to_dict())"
```

## 📚 추가 리소스

- [리팩토링 계획 문서](./refactoring-plan.md)
- [아키텍처 문서](../reference_docs/architecture.md)
- [환경 변수 가이드](../README.md#환경-변수)

## 💬 지원

마이그레이션 중 문제가 발생하면 다음을 참조하세요:

1. 이 가이드의 문제 해결 섹션
2. [GitHub Issues](https://github.com/your-repo/issues)
3. 프로젝트 문서의 FAQ 섹션

## 🎯 다음 단계

1. 통합 서버로 마이그레이션 완료
2. 테스트 실행으로 기능 확인
3. 필요에 따라 커스텀 설정 적용
4. 프로덕션 배포 준비

---

*마지막 업데이트: 2024-01-30*