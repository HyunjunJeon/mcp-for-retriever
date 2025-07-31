# 보안

- JWT 토큰 기반 인증 (Access Token + Refresh Token)
- 사용자별 데이터 격리 (Level Security)
- API Rate Limiting (Redis 기반)
- 입력 데이터 Sanitization

## 성능

- PostgreSQL Connection Pooling (asyncpg)
- Qdrant 배치 처리 및 인덱스 최적화
- FastAPI 비동기 처리
- 캐싱 전략 (Redis)

## 모니터링

- 각 도구별 응답 시간 추적
- 사용자별 사용량 통계
- 에러 로깅 및 알림
