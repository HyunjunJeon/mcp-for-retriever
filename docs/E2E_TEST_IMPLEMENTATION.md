# MCP Retriever E2E 테스트 구현 문서

## 개요
이 문서는 MCP Retriever 프로젝트의 E2E 테스트 구현 과정과 결과를 정리한 것입니다.

## 완료된 작업

### 1. Playwright 테스트 환경 설정 (Task ID: 18bdcca5-2b9b-4b60-8664-4aa65a8a133e)

#### 구현 내용
- **의존성 추가**: 
  - `playwright==1.49.0`
  - `pytest-playwright==0.5.2`
- **브라우저 설치**: Chromium 139.0.7258.5
- **디렉토리 구조**: `tests/e2e/playwright/` 생성
- **픽스처 설정**: 
  - `browser_context_args`: viewport 1280x720, HTTPS 에러 무시
  - `auth_page`, `mcp_page`: 서버 URL 설정
  - `playwright_headless`: 환경 변수 기반 제어

#### 주요 파일
- `tests/conftest.py`: Playwright 픽스처 추가
- `tests/e2e/playwright/test_setup.py`: 환경 검증 테스트
- `scripts/run-playwright-tests.sh`: 실행 스크립트

### 2. Auth Gateway UI 페이지 구현 및 테스트 (Task ID: eea80a77-cb6a-496d-9dd8-279a78dba327)

#### 구현 내용
- **HTML 페이지**:
  - `/auth/register-page`: 회원가입 폼
  - `/auth/login-page`: 로그인 폼 + JWT 토큰 표시
- **JavaScript 기능**:
  - Fetch API를 통한 비동기 API 호출
  - JWT 토큰 localStorage 저장
  - /auth/me 엔드포인트 테스트
  - 실시간 에러/성공 메시지 표시

#### 문제 해결
1. **인코딩 오류**: `src/auth/__init__.py` 파일의 null bytes 문제 해결
2. **비밀번호 검증**: 대문자+소문자+숫자 필수 규칙 확인
3. **에러 처리**: 422 Validation Error 상세 메시지 표시

#### 테스트 결과
```python
# test_auth_simple.py 실행 결과
✅ Registration successful for test_147215ed@example.com
✅ Login successful, tokens displayed
✅ User info retrieved successfully
✅ All tests passed!
```

## 기술 스택
- **Frontend**: Vanilla JavaScript, HTML5, CSS3
- **Testing**: Playwright, pytest-asyncio
- **Backend**: FastAPI (Auth Gateway)
- **Database**: PostgreSQL 17

## 실행 방법

### 1. 환경 설정
```bash
# 의존성 설치
uv sync

# Playwright 브라우저 설치
uv run playwright install chromium
```

### 2. 서버 실행
```bash
# PostgreSQL 실행 (Docker)
docker run -d --name mcp-postgres-test -p 5432:5432 \
  -e POSTGRES_USER=mcp_user \
  -e POSTGRES_PASSWORD=mcp_password \
  -e POSTGRES_DB=mcp_retriever \
  postgres:17-alpine

# Auth Gateway 실행
JWT_SECRET_KEY=test-secret \
POSTGRES_DSN=postgresql://mcp_user:mcp_password@localhost:5432/mcp_retriever \
uv run python -m src.auth.server
```

### 3. 테스트 실행
```bash
# Playwright E2E 테스트
PLAYWRIGHT_HEADLESS=true AUTH_URL=http://localhost:8000 \
uv run pytest tests/e2e/playwright/ -v

# 브라우저 표시 모드
./scripts/run-playwright-tests.sh --headed
```

## 다음 작업 예정

### 3. MCP 프로토콜 브라우저 클라이언트 구현
- JavaScript로 MCP JSON-RPC 프로토콜 구현
- tools/list, tools/call 메서드 지원
- JWT 토큰 기반 인증

### 4. Retriever 데이터 CRUD 인터페이스 구현
- Vector DB (Qdrant) CRUD 작업
- PostgreSQL 데이터 관리
- MCP 도구로 노출

### 5. 전체 사용자 여정 E2E 시나리오 테스트
- 회원가입 → 로그인 → 데이터 CRUD 전체 플로우
- 성능 측정 및 스크린샷 캡처

### 6. 장애 복구 및 에러 처리 E2E 테스트
- 서비스 장애 시뮬레이션
- 자동 복구 검증
- Circuit Breaker 패턴 테스트

## 참고 사항
- 비밀번호는 반드시 대문자, 소문자, 숫자를 포함해야 함
- JWT 토큰은 30분 유효, 리프레시 토큰은 7일 유효
- 모든 테스트는 격리된 환경에서 실행되어야 함