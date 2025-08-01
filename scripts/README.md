# MCP Retriever Scripts

Docker 기반 MCP Retriever 운영을 위한 스크립트 모음입니다.

## 🚀 주요 스크립트

### 서비스 관리

- **`start-docker.sh`**: Docker Compose로 모든 서비스 시작

  ```bash
  ./scripts/start-docker.sh          # 일반 시작
  ./scripts/start-docker.sh --build  # 이미지 재빌드 후 시작
  ```

- **`stop-docker.sh`**: 모든 서비스 중지

  ```bash
  ./scripts/stop-docker.sh
  ```

### 모니터링 및 디버깅

- **`test-services.sh`**: 서비스 상태 확인 및 기본 테스트

  ```bash
  ./scripts/test-services.sh
  ```

  - PostgreSQL, Redis, Qdrant 연결 테스트
  - Auth Gateway 및 MCP Server 헬스체크
  - 기본 인증 플로우 테스트
  - MCP 도구 목록 확인

- **`logs-docker.sh`**: Docker 컨테이너 로그 확인

  ```bash
  ./scripts/logs-docker.sh                # 모든 서비스 로그
  ./scripts/logs-docker.sh mcp-server -f  # MCP Server 실시간 로그
  ./scripts/logs-docker.sh auth-gateway -n 50  # Auth Gateway 최근 50줄
  ```

### 테스트

- **`run-integration-tests.sh`**: Docker 환경에서 통합 테스트 실행

  ```bash
  ./scripts/run-integration-tests.sh
  ```

## 📁 디렉토리 구조

```
scripts/
├── start-docker.sh         # Docker 서비스 시작
├── stop-docker.sh          # Docker 서비스 중지
├── test-services.sh        # 서비스 상태 확인
├── logs-docker.sh          # 로그 확인
├── run-integration-tests.sh # 통합 테스트 실행
└── db-init/               # 데이터베이스 초기화 스크립트
    ├── init_auth_db.py    # Auth DB 초기화 (Docker에서 자동 실행)
    └── init_permissions.sql # 권한 테이블 초기화
```

## 💡 사용 팁

1. **서비스 시작 순서**

   ```bash
   ./scripts/start-docker.sh --build  # 첫 실행 또는 코드 변경 시
   ./scripts/test-services.sh         # 서비스 상태 확인
   ```

2. **문제 해결**

   ```bash
   ./scripts/logs-docker.sh -f        # 실시간 로그로 문제 확인
   ./scripts/stop-docker.sh           # 서비스 재시작
   ./scripts/start-docker.sh
   ```

3. **개발 중 모니터링**

   ```bash
   # 터미널 1: 로그 모니터링
   ./scripts/logs-docker.sh -f
   
   # 터미널 2: 주기적 상태 확인
   watch -n 10 ./scripts/test-services.sh
   ```

## ⚠️ 주의사항

- 모든 스크립트는 프로젝트 루트에서 실행해야 합니다
- Docker Desktop이 실행 중이어야 합니다
- 첫 실행 시 `.env` 파일 설정이 필요합니다
