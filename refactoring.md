# MCP 서버 리팩토링 계획

이 문서는 코드 리뷰 결과를 바탕으로 한 리팩토링 계획을 문서화합니다. 목표는 Clean Code Architecture(CCA) 강화, 중복 제거, 코드 분할 최적화, 핵심 기능 보강입니다.

## 1. Clean Code Architecture 강화

- 계층 분리: 인프라(예: database.py의 엔진 설정)를 config/로 이동하여 도메인과 분리.
- 의존성 역전: 기존 Repository 패턴 유지, 추가로 인프라 설정을 DI로 주입.

## 2. 중복 제거

- 서버 파일 통합: server.py, server_auth.py 등 중복 파일을 server.py로 병합. 플래그(enable_auth 등)로 기능 토글.
- 중복 함수(예: search_web) 제거.

## 3. 코드 분할 최적화

- utils 중앙화: 분산된 로깅/유틸 함수를 src/utils/로 이동.
- 불필요 서브디렉토리 정리.

## 4. 핵심 기능 보강

- 보안: API 키를 환경 변수로 변경 (예: os.getenv('TAVILY_API_KEY')).
- 테스트: 새 테스트 파일 추가, 커버리지 80% 목표.

## 구현 순서

1. refactoring.md 작성 (현재).
2. 서버 통합.
3. 인프라 분리.
4. utils 중앙화.
5. 기능 보강 및 테스트.

각 변경 후 테스트 검증.
