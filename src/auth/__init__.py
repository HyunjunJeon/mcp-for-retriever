"""
MCP 서버용 JWT 기반 인증 모듈

이 모듈은 MCP(Model Context Protocol) 서버의 인증과 권한 관리를 담당합니다.
역할 기반 접근 제어(RBAC)를 지원하며 JWT 토큰을 사용합니다.

주요 구성 요소:
    - models: 데이터 모델 정의 (사용자, 역할 등)
    - database: SQLAlchemy ORM 기반 데이터베이스 설정
    - repositories: 데이터 액세스 레이어 (Repository 패턴)
    - services: 비즈니스 로직 서비스 (인증, JWT, RBAC, MCP 프록시)
    - dependencies: FastAPI 의존성 주입 함수
    - server: JWT 기반 인증 게이트웨이 서버
"""
