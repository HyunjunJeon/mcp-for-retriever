# 🚨 서버 파일 통합 안내

## 중요 공지

모든 서버 파일이 `server_unified.py`로 통합되었습니다!

### 현재 파일 구조

```
src/
├── server_unified.py          # ✅ 통합 서버 (이것만 사용)
└── old/                       # 📦 원본 파일들 (참조용)
    ├── server_auth_original.py
    ├── server_context_original.py
    ├── server_with_cache_original.py
    ├── server_complete_original.py
    └── README.md
```

### 사용 방법

#### 통합 서버 사용 ✅
```bash
# 기본 서버
MCP_PROFILE=BASIC python -m src.server_unified

# 인증 서버 (기존 server_auth.py 대체)
MCP_PROFILE=AUTH python -m src.server_unified

# 컨텍스트 서버 (기존 server_context.py 대체)
MCP_PROFILE=CONTEXT python -m src.server_unified

# 캐싱 서버 (기존 server_with_cache.py 대체)
MCP_PROFILE=CACHED python -m src.server_unified

# 완전 통합 서버 (기존 server_complete.py 대체)
MCP_PROFILE=COMPLETE python -m src.server_unified
```

### 주요 변경사항

1. **통합 서버**: 모든 기능이 하나의 서버에 통합
2. **프로파일 기반 설정**: 필요한 기능만 선택적 활성화
3. **중복 코드 제거**: 약 2,000줄의 중복 코드 제거
4. **향상된 설정 관리**: `src/config/` 디렉토리에서 중앙 관리

### ⚠️ 주의사항

- 기존 서버 파일들(`server_auth.py`, `server_context.py` 등)은 더 이상 존재하지 않습니다
- 반드시 `server_unified.py`를 사용하세요
- 원본 파일이 필요한 경우 `old/` 폴더를 참조하세요

### 도움말

자세한 내용은 [마이그레이션 가이드](../docs/migration-guide.md)를 참조하세요.

---

*마지막 업데이트: 2024-01-30*