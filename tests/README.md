# MCP Retriever 테스트

Docker 기반 MCP Retriever의 테스트 스위트입니다.

## 📁 디렉토리 구조

```
tests/
├── unit/                    # 단위 테스트
│   ├── test_auth/          # 인증 서비스 테스트
│   ├── test_middleware/    # 미들웨어 테스트
│   ├── test_retrievers/    # Retriever 구현 테스트
│   └── test_utils/         # 유틸리티 테스트
├── integration/            # 통합 테스트
│   ├── test_auth_integration.py         # 인증 통합
│   ├── test_bearer_auth.py              # Bearer 토큰 인증
│   ├── test_comprehensive_integration.py # 종합 통합 테스트
│   ├── test_docker_integration.py       # Docker 환경 테스트
│   ├── test_jwt_auto_refresh_integration.py # JWT 자동 갱신
│   ├── test_search_tools.py             # 검색 도구 테스트
│   ├── test_server_profiles.py          # 서버 프로파일 테스트
│   └── test_token_revocation_integration.py # 토큰 무효화
├── fixtures/               # 테스트 픽스처
│   └── mock_retriever.py   # Mock Retriever 구현
└── conftest.py            # pytest 전역 설정
```

## 🧪 테스트 실행

### Docker 환경에서 테스트

```bash
# 전체 테스트 실행
./scripts/run-integration-tests.sh

# 특정 테스트 모듈 실행
docker exec -it mcp-server pytest tests/unit/test_token_revocation.py -v

# 단위 테스트만 실행
docker exec -it mcp-server pytest tests/unit/ -v

# 통합 테스트만 실행
docker exec -it mcp-server pytest tests/integration/ -v
```

### 로컬 개발 환경 (선택사항)

```bash
# 환경 설정
uv sync

# 단위 테스트 실행
uv run pytest tests/unit/ -v

# 특정 테스트 파일 실행
uv run pytest tests/unit/test_auth/test_jwt_service.py -v

# 커버리지 확인
uv run pytest --cov=src --cov-report=html
```

## 📋 주요 테스트

### 단위 테스트 (unit/)

- **인증 (test_auth/)**
  - `test_auth_service.py`: 인증 서비스 로직
  - `test_jwt_service.py`: JWT 토큰 생성/검증
  - `test_rbac_service.py`: 역할 기반 접근 제어

- **미들웨어 (test_middleware/)**
  - `test_auth.py`: 인증 미들웨어
  - `test_rate_limit.py`: 속도 제한
  - `test_validation.py`: 요청 검증

- **Retrievers (test_retrievers/)**
  - `test_tavily.py`: Tavily 웹 검색
  - `test_qdrant.py`: Qdrant 벡터 검색
  - `test_postgres.py`: PostgreSQL 검색

### 통합 테스트 (integration/)

- **핵심 기능**
  - `test_comprehensive_integration.py`: 전체 시스템 통합 테스트
  - `test_docker_integration.py`: Docker 환경 검증
  - `test_search_tools.py`: 모든 검색 도구 통합

- **인증 & 보안**
  - `test_auth_integration.py`: 인증 플로우
  - `test_bearer_auth.py`: Bearer 토큰 인증
  - `test_jwt_auto_refresh_integration.py`: 토큰 자동 갱신
  - `test_token_revocation_integration.py`: 토큰 무효화

## 🔍 테스트 작성 가이드

### 단위 테스트

```python
import pytest
from src.auth.services.jwt_service import JWTService

class TestJWTService:
    def test_create_access_token(self):
        jwt_service = JWTService(secret_key="test-key")
        token = jwt_service.create_access_token(
            user_id="user-123",
            email="test@example.com"
        )
        assert token is not None
```

### 통합 테스트

```python
import pytest
import httpx

@pytest.mark.asyncio
async def test_auth_flow():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # 로그인
        response = await client.post("/auth/login", json={
            "email": "test@example.com",
            "password": "Test123!"
        })
        assert response.status_code == 200
        token = response.json()["access_token"]
        
        # 인증된 요청
        response = await client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
```

## 📊 테스트 커버리지

현재 테스트 커버리지 목표:
- 단위 테스트: 80% 이상
- 통합 테스트: 핵심 시나리오 100%

커버리지 확인:
```bash
docker exec -it mcp-server pytest --cov=src --cov-report=term-missing
```

## 🚀 CI/CD 통합

GitHub Actions에서 자동 실행:
- PR 생성 시 단위 테스트 실행
- main 브랜치 병합 시 전체 테스트 실행

## ⚠️ 주의사항

1. **Docker 환경 필수**
   - 모든 통합 테스트는 Docker 환경 필요
   - 데이터베이스 연결 테스트는 실제 서비스 필요

2. **테스트 격리**
   - 각 테스트는 독립적으로 실행 가능해야 함
   - 테스트 간 상태 공유 금지

3. **Mock 사용**
   - 외부 API (Tavily) 호출은 Mock 사용
   - 단위 테스트에서는 데이터베이스 Mock 사용