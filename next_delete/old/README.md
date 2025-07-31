# Old Server Files (Deprecated)

이 폴더는 리팩토링 이전의 원본 서버 파일들을 보관합니다.

## 📁 파일 목록

- `server_auth_original.py` - 인증 기능이 있는 서버
- `server_context_original.py` - 컨텍스트 추적 기능이 있는 서버
- `server_with_cache_original.py` - Redis 캐싱이 통합된 서버
- `server_complete_original.py` - 모든 기능이 통합된 서버

## ⚠️ 주의사항

**이 파일들은 더 이상 사용되지 않습니다!**

새로운 통합 서버를 사용하세요:
```bash
# 통합 서버 사용
python -m src.server_unified
```

## 🔄 마이그레이션

기존 서버에서 새로운 통합 서버로 마이그레이션하려면 [마이그레이션 가이드](../../docs/migration-guide.md)를 참조하세요.

## 📌 참조용으로만 보관

이 파일들은 다음 용도로만 보관됩니다:
- 코드 히스토리 참조
- 기능 구현 방식 확인
- 문제 발생 시 비교 분석

## 🗓️ 제거 예정

이 폴더는 향후 메이저 버전 업데이트 시 완전히 제거될 예정입니다.