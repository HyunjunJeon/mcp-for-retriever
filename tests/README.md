# Tests Directory Structure

이 디렉토리는 프로젝트의 모든 테스트와 디버그 코드를 포함합니다.

## 디렉토리 구조

### `/e2e/` - End-to-End 테스트
공식 E2E 테스트 스위트입니다.
- `test_mcp_client_e2e.py`: FastMCP 클라이언트를 사용한 전체 시스템 테스트
- `test_fine_grained_permissions.py`: 세밀한 권한 시스템 테스트
- `test_gateway_integration.py`: Auth Gateway 통합 테스트

### `/unit/` - 단위 테스트
개별 컴포넌트의 단위 테스트입니다.
- `test_resource_permissions.py`: 리소스 권한 단위 테스트

### `/integration_custom/` - 커스텀 통합 테스트
수동으로 작성된 통합 테스트입니다.
- `test_complete_system.py`: **메인 시스템 통합 테스트** (85.7% 성공률 달성!)
  - 사용자 인증부터 모든 도구 테스트까지 포함
  - 현재 실행 중인 서버 기반 테스트

### `/debug/` - 디버깅 스크립트
개발 중 디버깅을 위한 스크립트들입니다.
- `debug_mcp_init.py`: MCP 서버 초기화 직접 테스트
- `debug_mcp_search.py`: Auth Gateway를 통한 MCP 검색 테스트
- `debug_user_info.py`: 사용자 정보 및 역할 확인

### `/manual/` - 수동 테스트 스크립트
개발 과정에서 생성된 수동 테스트들입니다.
- `test_crud_functionality.py`: CRUD 기능 테스트
- `test_mcp_tools.py`: MCP 도구 기본 테스트
- `test_mcp_tools_with_session.py`: 세션 기반 MCP 도구 테스트
- `test_qdrant_memory_mode.py`: Qdrant 메모리 모드 테스트
- `test_vector_crud_tools.py`: 벡터 CRUD 도구 테스트
- `start_test_servers.sh`: 테스트 서버 시작 스크립트
- `test_server_pids.txt`: 서버 PID 관리 파일

## 테스트 실행 방법

### 1. 공식 E2E 테스트
```bash
uv run pytest tests/e2e/ -v
```

### 2. 커스텀 통합 테스트 (권장)
```bash
# 현재 실행 중인 서버 기반 테스트
uv run python tests/integration_custom/test_complete_system.py
```

### 3. 단위 테스트
```bash
uv run pytest tests/unit/ -v
```

### 4. 디버깅 스크립트
```bash
# MCP 서버 직접 테스트
uv run python tests/debug/debug_mcp_init.py

# Auth Gateway 통합 테스트
uv run python tests/debug/debug_mcp_search.py
```

## 현재 성과

🎉 **test_complete_system.py에서 85.7% 성공률 달성!** (6/7 테스트 성공)

### ✅ 성공한 기능들:
- 사용자 인증 시스템
- 도구 목록 조회 (9개 도구)
- 헬스 체크
- 데이터베이스 검색
- 벡터 컬렉션 생성
- 동시 요청 처리

### 🚧 개선 영역:
- 벡터 검색 (빈 결과 처리)

## 개발 가이드라인

1. **새로운 테스트 추가**: 적절한 디렉토리에 추가
2. **디버깅**: `/debug/` 디렉토리 사용
3. **임시 테스트**: `/manual/` 디렉토리 사용 후 정리
4. **공식 테스트**: `/e2e/` 또는 `/unit/` 디렉토리 사용