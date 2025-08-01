"""
비동기 SQLite 기반 인증 서비스

이 모듈은 SQLite 데이터베이스를 사용하는 비동기 인증 서비스를 제공합니다.
토큰 무효화 기능을 위해 비동기 메서드가 필요한 경우 사용합니다.
"""

from typing import Optional

from passlib.context import CryptContext
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    UserCreate,
    UserLogin,
    UserResponse,
    AuthTokens,
)
from ..repositories.sqlite_user_repository import SQLiteUserRepository
from ..repositories.token_repository import TokenRepository
from .jwt_service import JWTService


logger = structlog.get_logger(__name__)


class AsyncSQLiteAuthService:
    """
    비동기 SQLite 기반 통합 인증 서비스

    JWT 기반 인증과 SQLite 데이터베이스를 결합한 비동기 인증 서비스입니다.
    토큰 무효화 기능을 위한 비동기 메서드를 제공합니다.
    """

    def __init__(
        self,
        jwt_service: JWTService,
        token_repository: Optional[TokenRepository] = None,
    ):
        """
        인증 서비스 초기화

        Args:
            jwt_service (JWTService): JWT 토큰 관리 서비스
            token_repository (Optional[TokenRepository]): 토큰 저장소
        """
        self.jwt_service = jwt_service
        self.token_repository = token_repository
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def hash_password(self, password: str) -> str:
        """비밀번호 해싱"""
        return self.pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """비밀번호 검증"""
        return self.pwd_context.verify(plain_password, hashed_password)

    async def register(
        self, user_data: UserCreate, session: AsyncSession
    ) -> UserResponse:
        """
        새 사용자 등록

        Args:
            user_data (UserCreate): 사용자 등록 정보
            session (AsyncSession): 데이터베이스 세션

        Returns:
            UserResponse: 생성된 사용자 정보

        Raises:
            AuthenticationError: 이메일 중복 등 유효성 검사 실패
        """
        # SQLite Repository 생성
        repository = SQLiteUserRepository(session)

        # 이메일 중복 확인
        existing_user = await repository.get_by_email(user_data.email)
        if existing_user:
            logger.warning("이메일 중복으로 회원가입 실패", email=user_data.email)
            # Clean Code: 보안상 이메일 정보는 노출하지 않음
            raise AuthenticationError("이미 등록된 이메일입니다")

        # 비밀번호 해싱
        hashed_password = self.hash_password(user_data.password)

        try:
            # 사용자 생성
            user = await repository.create(
                {
                    "email": user_data.email,
                    "username": user_data.username,
                    "password_hash": hashed_password,
                    "roles": user_data.roles or ["user"],
                    "is_active": True,
                    "is_verified": False,
                }
            )

            logger.info("새 사용자 등록 완료", user_id=user.id, email=user.email)

            # 민감한 정보 제외하고 반환
            return UserResponse(
                id=user.id,
                email=user.email,
                username=user.username,
                is_active=user.is_active,
                is_verified=user.is_verified,
                roles=user.roles,
                created_at=user.created_at,
            )

        except Exception as e:
            logger.error(
                "사용자 생성 중 데이터베이스 오류", error=str(e), email=user_data.email
            )
            raise AuthenticationError("사용자 등록 중 오류가 발생했습니다")

    async def login(self, credentials: UserLogin, session: AsyncSession) -> AuthTokens:
        """
        사용자 로그인 및 토큰 발급

        Args:
            credentials (UserLogin): 로그인 자격 증명
            session (AsyncSession): 데이터베이스 세션

        Returns:
            AuthTokens: 액세스 및 리프레시 토큰

        Raises:
            AuthenticationError: 인증 실패
        """
        # SQLite Repository 생성
        repository = SQLiteUserRepository(session)

        # 사용자 조회
        user = await repository.get_by_email(credentials.email)
        if not user:
            logger.warning(
                "존재하지 않는 사용자로 로그인 시도", email=credentials.email
            )
            raise AuthenticationError("이메일 또는 비밀번호가 올바르지 않습니다")

        # 비밀번호 검증
        if not self.verify_password(credentials.password, user.password_hash):
            logger.warning("잘못된 비밀번호로 로그인 시도", email=credentials.email)
            raise AuthenticationError("이메일 또는 비밀번호가 올바르지 않습니다")

        # 계정 활성화 확인
        if not user.is_active:
            logger.warning("비활성화된 계정으로 로그인 시도", email=credentials.email)
            raise AuthenticationError("계정이 비활성화되었습니다")

        # JWT 토큰 생성
        access_token = self.jwt_service.create_access_token(
            user_id=user.id, email=user.email, roles=user.roles
        )

        refresh_token = self.jwt_service.create_refresh_token(user_id=user.id)

        logger.info("사용자 로그인 성공", user_id=user.id, email=user.email)

        return AuthTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=self.jwt_service.access_token_expire_minutes * 60,
        )

    async def refresh_tokens(
        self, refresh_token: str, session: AsyncSession
    ) -> AuthTokens:
        """
        리프레시 토큰으로 새 액세스 토큰 발급 (비동기 버전)

        Args:
            refresh_token (str): 리프레시 토큰
            session (AsyncSession): 데이터베이스 세션

        Returns:
            AuthTokens: 새로운 액세스 토큰

        Raises:
            AuthenticationError: 토큰 검증 실패
        """
        # 리프레시 토큰 검증
        token_data = self.jwt_service.decode_token(refresh_token)

        if not token_data:
            raise AuthenticationError("유효하지 않은 토큰입니다")

        # 이전 리프레시 토큰 무효화
        if self.token_repository and token_data.jti:
            try:
                await self.token_repository.revoke_token(token_data.jti)
                logger.info("이전 리프레시 토큰 무효화", jti=token_data.jti)
            except Exception as e:
                logger.error("토큰 무효화 실패", error=str(e), jti=token_data.jti)

        # SQLite Repository 생성
        repository = SQLiteUserRepository(session)

        # 사용자 조회
        user = await repository.get_by_id(token_data.user_id)
        if not user or not user.is_active:
            raise AuthenticationError("유효하지 않은 사용자입니다")

        # 새 액세스 토큰 생성
        access_token = self.jwt_service.create_access_token(
            user_id=user.id, email=user.email, roles=user.roles
        )

        # 새 리프레시 토큰 생성 (토큰 rotation)
        new_refresh_token = self.jwt_service.create_refresh_token(user_id=user.id)

        logger.info("토큰 갱신 성공", user_id=user.id)

        return AuthTokens(
            access_token=access_token,
            refresh_token=new_refresh_token,  # 새 리프레시 토큰 발급
            token_type="bearer",
            expires_in=self.jwt_service.access_token_expire_minutes * 60,
        )

    async def logout(self, user_id: str, device_id: Optional[str] = None) -> bool:
        """
        로그아웃 (토큰 무효화)

        Args:
            user_id (str): 사용자 ID
            device_id (Optional[str]): 특정 디바이스만 로그아웃

        Returns:
            bool: 성공 여부
        """
        if self.jwt_service.token_repository:
            if device_id:
                # 특정 디바이스 토큰만 무효화
                return await self.jwt_service.revoke_refresh_token(user_id, device_id)
            else:
                # 모든 토큰 무효화
                count = await self.jwt_service.revoke_all_user_tokens(user_id)
                return count > 0

        return False

    async def get_current_user(self, token: str, session: AsyncSession) -> UserResponse:
        """
        JWT 토큰으로 현재 사용자 조회

        Args:
            token (str): JWT 액세스 토큰
            session (AsyncSession): 데이터베이스 세션

        Returns:
            UserResponse: 현재 사용자 정보

        Raises:
            AuthenticationError: 토큰 검증 실패 또는 사용자 없음
        """
        # 토큰 검증
        token_data = self.jwt_service.decode_token(token)

        if not token_data:
            raise AuthenticationError("유효하지 않은 토큰입니다")

        # SQLite Repository 생성
        repository = SQLiteUserRepository(session)

        # 사용자 조회
        user = await repository.get_by_id(token_data.user_id)
        if not user:
            raise AuthenticationError("사용자를 찾을 수 없습니다")

        if not user.is_active:
            raise AuthenticationError("계정이 비활성화되었습니다")

        # 응답 모델로 변환
        return UserResponse(
            id=user.id,
            email=user.email,
            username=user.username,
            is_active=user.is_active,
            is_verified=user.is_verified,
            roles=user.roles,
            created_at=user.created_at,
        )


class AuthenticationError(Exception):
    """인증 실패 예외"""

    pass
