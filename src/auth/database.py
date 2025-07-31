"""
MCP 서버 인증 시스템 데이터베이스 설정 및 모델

이 모듈은 MCP(Model Context Protocol) 서버의 인증 및 권한 관리를 위한
데이터베이스 모델과 설정을 정의합니다. SQLAlchemy ORM을 사용하여
비동기 데이터베이스 작업을 지원합니다.

주요 컴포넌트:
    User: 사용자 정보 저장 테이블
    RevokedToken: 무효화된 JWT 토큰 관리 테이블
    user_roles: 사용자-역할 다대다 관계 테이블
    user_permissions: 사용자-도구 권한 매핑 테이블

데이터베이스 특징:
    - 비동기 SQLAlchemy ORM 사용
    - UTC 기준 타임스탬프 관리
    - 인덱스 최적화로 검색 성능 향상
    - 외래키 제약조건으로 데이터 무결성 보장
    - 연결 풀링으로 성능 최적화

보안 고려사항:
    - 비밀번호는 해시된 형태로만 저장
    - 토큰 무효화를 통한 안전한 로그아웃
    - 권한 부여 추적 및 감사 로그
    - UUID 기반 사용자 ID로 예측 불가능성

"""

import os
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Table
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime, UTC

# SQLAlchemy ORM 기본 클래스
# 모든 데이터베이스 모델이 상속받는 베이스 클래스
Base = declarative_base()

# 사용자-역할 다대다 관계 테이블
# 한 사용자가 여러 역할을 가질 수 있고, 한 역할이 여러 사용자에게 할당될 수 있음
user_roles = Table(
    'user_roles',  # 테이블 이름
    Base.metadata,  # 메타데이터 연결
    Column('user_id', String, ForeignKey('users.id')),  # 사용자 ID (외래키)
    Column('role', String)  # 역할 이름 (예: "admin", "user", "moderator")
)

# 사용자별 도구 접근 권한 매핑 테이블
# 사용자가 특정 MCP 도구에 대한 접근 권한을 가지는지 추적
user_permissions = Table(
    'user_permissions',  # 테이블 이름
    Base.metadata,  # 메타데이터 연결
    Column('user_id', String, ForeignKey('users.id')),  # 사용자 ID (외래키)
    Column('tool_name', String),  # MCP 도구 이름 (예: "search_web", "search_vectors")
    Column('granted_at', DateTime, default=lambda: datetime.now(UTC)),  # 권한 부여 시각 (UTC)
    Column('granted_by', String)  # 권한을 부여한 관리자 ID (감사 목적)
)


class User(Base):
    """
    사용자 정보 테이블
    
    MCP 서버에 인증하는 사용자들의 기본 정보를 저장합니다.
    JWT 기반 인증과 RBAC(Role-Based Access Control) 시스템의 중심이 되는 모델입니다.
    
    보안 특징:
        - 비밀번호는 bcrypt로 해시되어 저장 (평문 저장 안함)
        - 이메일은 고유 제약조건으로 중복 방지
        - UUID 기반 ID로 예측 불가능한 사용자 식별
        - 계정 활성화 상태로 접근 제어
        
    관계:
        - user_roles: 다대다 관계로 여러 역할 할당 가능
        - user_permissions: 도구별 세밀한 권한 제어
        
    인덱싱:
        - email: 로그인 시 빠른 조회를 위한 인덱스
        - id: 기본키로 자동 인덱싱
    """
    __tablename__ = "users"
    
    # 기본키: UUID 문자열 형태의 고유 식별자
    id = Column(String, primary_key=True)
    
    # 이메일: 로그인 ID로 사용, 고유 제약조건과 인덱스 적용
    email = Column(String, unique=True, nullable=False, index=True)
    
    # 사용자명: 선택적 사용자 이름
    username = Column(String, nullable=True)
    
    # 해시된 비밀번호: bcrypt로 안전하게 해시된 비밀번호 저장
    password_hash = Column(String, nullable=False)
    
    # 이메일 인증 상태
    is_verified = Column(Boolean, default=False)
    
    # 계정 활성화 상태: 비활성화된 계정은 로그인 불가
    is_active = Column(Boolean, default=True)
    
    # 생성 시각: 계정 생성 시점 (UTC 기준)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    
    # 수정 시각: 계정 정보 변경 시점 (UTC 기준, 자동 업데이트)
    updated_at = Column(DateTime, onupdate=lambda: datetime.now(UTC))
    
    # 사용자 메타데이터는 별도 쿼리로 처리 (SQLite에서는 간단한 구조 유지)


class RevokedToken(Base):
    """
    무효화된 JWT 토큰 블랙리스트 테이블
    
    로그아웃이나 보안상의 이유로 무효화된 JWT 토큰들을 저장합니다.
    JWT는 stateless하기 때문에 서버에서 강제로 무효화하려면 블랙리스트가 필요합니다.
    
    보안 목적:
        - 로그아웃 시 토큰 즉시 무효화
        - 계정 탈취 의심 시 긴급 토큰 차단
        - 권한 변경 시 기존 토큰 무효화
        - 토큰 만료 전 강제 차단
        
    성능 최적화:
        - token 필드에 인덱스로 빠른 조회
        - expires_at으로 만료된 토큰 자동 정리
        - 배치 삭제로 테이블 크기 관리
        
    데이터 라이프사이클:
        1. 토큰 무효화 요청 시 레코드 생성
        2. 토큰 검증 시 블랙리스트 확인
        3. 만료 시간 도달 후 정리 작업으로 삭제
    """
    __tablename__ = "revoked_tokens"
    
    # 기본키: 무효화 레코드의 고유 식별자 (UUID)
    id = Column(String, primary_key=True)
    
    # 무효화된 JWT 토큰 문자열 (고유 제약조건과 인덱스)
    token = Column(String, unique=True, nullable=False, index=True)
    
    # 토큰 무효화 시점 (UTC 기준)
    revoked_at = Column(DateTime, default=lambda: datetime.now(UTC))
    
    # 원래 토큰 만료 시점 (정리 작업 기준)
    expires_at = Column(DateTime, nullable=False)


# 데이터베이스 연결 설정
# 환경변수에서 AUTH_DATABASE_URL을 읽어오며, 기본값은 SQLite 파일 DB
# Docker 환경에서는 /data/auth.db로 저장하여 볼륨 마운트 가능
AUTH_DATABASE_URL = os.getenv("AUTH_DATABASE_URL", "sqlite+aiosqlite:///./auth.db")

# 비동기 SQLAlchemy 엔진 생성
# pool_pre_ping=True로 연결 유효성 자동 확인
engine = create_async_engine(
    AUTH_DATABASE_URL,
    echo=os.getenv("SQLALCHEMY_ECHO", "False").lower() == "true",  # 환경변수로 SQL 로깅 제어
    pool_pre_ping=True  # 연결 풀에서 연결 사용 전 ping 테스트
)

# 비동기 세션 팩토리 생성
# expire_on_commit=False로 커밋 후에도 객체 접근 가능
async_session_maker = sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False  # 커밋 후 객체 만료 방지
)


async def get_db():
    """
    FastAPI 의존성 주입용 데이터베이스 세션 제공
    
    비동기 컨텍스트 매니저를 사용하여 데이터베이스 세션을 생성하고
    요청 처리 완료 후 자동으로 세션을 정리합니다.
    
    사용 패턴:
        ```python
        @app.get("/users/")
        async def get_users(db: AsyncSession = Depends(get_db)):
            # db 세션 사용
            pass
        ```
        
    세션 관리:
        - 요청 시작 시 새 세션 생성
        - 요청 처리 중 세션 유지
        - 요청 완료 시 세션 자동 정리
        - 예외 발생 시에도 안전한 세션 해제
        
    Yields:
        AsyncSession: 비동기 데이터베이스 세션
    """
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """
    데이터베이스 테이블 초기화
    
    애플리케이션 시작 시 필요한 모든 테이블을 생성합니다.
    이미 존재하는 테이블은 건드리지 않으므로 안전하게 호출 가능합니다.
    
    초기화 과정:
        1. 엔진에서 새로운 연결 시작
        2. Base.metadata의 모든 테이블 정의 수집
        3. CREATE TABLE 문 실행 (IF NOT EXISTS 자동 적용)
        4. 외래키 제약조건 생성
        5. 인덱스 생성
        
    테이블 생성 순서:
        - users (기본 테이블)
        - user_roles (users 참조)
        - user_permissions (users 참조)  
        - revoked_tokens (독립 테이블)
        
    주의사항:
        - 프로덕션에서는 마이그레이션 도구 사용 권장
        - 스키마 변경 시 수동 처리 필요
        - 데이터 손실 방지를 위한 백업 필수
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)