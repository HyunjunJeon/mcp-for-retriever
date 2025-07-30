"""사용자 인증 서비스 테스트"""

from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import SecretStr

from src.auth.models import User, UserCreate, UserLogin, AuthTokens
from src.auth.services.auth_service import AuthService, AuthenticationError
from src.auth.services.jwt_service import JWTService
from src.auth.repositories.user_repository import UserRepository


class TestAuthService:
    """인증 서비스 테스트"""

    @pytest.fixture
    def mock_user_repository(self) -> Mock:
        """Mock UserRepository"""
        return Mock(spec=UserRepository)

    @pytest.fixture
    def mock_jwt_service(self) -> Mock:
        """Mock JWTService"""
        return Mock(spec=JWTService)

    @pytest.fixture
    def auth_service(
        self,
        mock_user_repository: Mock,
        mock_jwt_service: Mock,
    ) -> AuthService:
        """AuthService 픽스처"""
        return AuthService(
            user_repository=mock_user_repository,
            jwt_service=mock_jwt_service,
        )

    @pytest.fixture
    def sample_user(self) -> User:
        """샘플 사용자"""
        return User(
            id="user-123",
            email="test@example.com",
            hashed_password="$2b$12$hashed_password_here",
            is_active=True,
            roles=["user"],
        )

    @pytest.mark.asyncio
    async def test_register_user_success(
        self,
        auth_service: AuthService,
        mock_user_repository: Mock,
    ) -> None:
        """사용자 등록 성공 테스트"""
        # Given
        user_create = UserCreate(
            email="newuser@example.com",
            password=SecretStr("StrongPassword123!"),
            roles=["user"],
        )
        
        created_user = User(
            id="new-user-123",
            email=user_create.email,
            hashed_password="$2b$12$hashed_password",
            is_active=True,
            roles=user_create.roles,
        )
        
        mock_user_repository.get_by_email = AsyncMock(return_value=None)
        mock_user_repository.create = AsyncMock(return_value=created_user)

        # When
        result = await auth_service.register(user_create)

        # Then
        assert result.id == created_user.id
        assert result.email == created_user.email
        assert result.roles == created_user.roles
        assert result.is_active is True
        
        # 비밀번호가 해시되었는지 확인
        mock_user_repository.create.assert_called_once()
        call_args = mock_user_repository.create.call_args[0][0]
        assert call_args["hashed_password"] != user_create.password.get_secret_value()
        assert call_args["hashed_password"].startswith("$2b$")

    @pytest.mark.asyncio
    async def test_register_user_email_exists(
        self,
        auth_service: AuthService,
        mock_user_repository: Mock,
        sample_user: User,
    ) -> None:
        """이미 존재하는 이메일로 등록 시도 테스트"""
        # Given
        user_create = UserCreate(
            email=sample_user.email,
            password=SecretStr("Password123!"),
            roles=["user"],
        )
        
        mock_user_repository.get_by_email = AsyncMock(return_value=sample_user)

        # When & Then
        with pytest.raises(AuthenticationError) as exc_info:
            await auth_service.register(user_create)
        
        assert "이미 등록된 이메일" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_login_success(
        self,
        auth_service: AuthService,
        mock_user_repository: Mock,
        mock_jwt_service: Mock,
        sample_user: User,
    ) -> None:
        """로그인 성공 테스트"""
        # Given
        user_login = UserLogin(
            email="test@example.com",
            password=SecretStr("CorrectPassword123!"),
        )
        
        mock_user_repository.get_by_email = AsyncMock(return_value=sample_user)
        mock_jwt_service.create_access_token.return_value = "access_token_123"
        mock_jwt_service.create_refresh_token.return_value = "refresh_token_123"
        
        # 비밀번호 검증을 위해 verify_password 메서드 mock
        auth_service.verify_password = Mock(return_value=True)

        # When
        tokens = await auth_service.login(user_login)

        # Then
        assert isinstance(tokens, AuthTokens)
        assert tokens.access_token == "access_token_123"
        assert tokens.refresh_token == "refresh_token_123"
        assert tokens.token_type == "Bearer"
        
        mock_jwt_service.create_access_token.assert_called_once_with(
            user_id=sample_user.id,
            email=sample_user.email,
            roles=sample_user.roles,
        )
        mock_jwt_service.create_refresh_token.assert_called_once_with(
            user_id=sample_user.id,
        )

    @pytest.mark.asyncio
    async def test_login_user_not_found(
        self,
        auth_service: AuthService,
        mock_user_repository: Mock,
    ) -> None:
        """존재하지 않는 사용자로 로그인 시도 테스트"""
        # Given
        user_login = UserLogin(
            email="notfound@example.com",
            password=SecretStr("Password123!"),
        )
        
        mock_user_repository.get_by_email = AsyncMock(return_value=None)

        # When & Then
        with pytest.raises(AuthenticationError) as exc_info:
            await auth_service.login(user_login)
        
        assert "이메일 또는 비밀번호가 올바르지 않습니다" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_login_wrong_password(
        self,
        auth_service: AuthService,
        mock_user_repository: Mock,
        sample_user: User,
    ) -> None:
        """잘못된 비밀번호로 로그인 시도 테스트"""
        # Given
        user_login = UserLogin(
            email="test@example.com",
            password=SecretStr("WrongPassword123!"),
        )
        
        mock_user_repository.get_by_email = AsyncMock(return_value=sample_user)
        auth_service.verify_password = Mock(return_value=False)

        # When & Then
        with pytest.raises(AuthenticationError) as exc_info:
            await auth_service.login(user_login)
        
        assert "이메일 또는 비밀번호가 올바르지 않습니다" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_login_inactive_user(
        self,
        auth_service: AuthService,
        mock_user_repository: Mock,
        sample_user: User,
    ) -> None:
        """비활성화된 사용자로 로그인 시도 테스트"""
        # Given
        inactive_user = User(
            **{**sample_user.model_dump(), "is_active": False}
        )
        user_login = UserLogin(
            email="test@example.com",
            password=SecretStr("CorrectPassword123!"),
        )
        
        mock_user_repository.get_by_email = AsyncMock(return_value=inactive_user)
        auth_service.verify_password = Mock(return_value=True)

        # When & Then
        with pytest.raises(AuthenticationError) as exc_info:
            await auth_service.login(user_login)
        
        assert "계정이 비활성화되었습니다" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_refresh_token_success(
        self,
        auth_service: AuthService,
        mock_user_repository: Mock,
        mock_jwt_service: Mock,
        sample_user: User,
    ) -> None:
        """토큰 갱신 성공 테스트"""
        # Given
        refresh_token = "valid_refresh_token"
        
        mock_user_repository.get_by_id = AsyncMock(return_value=sample_user)
        mock_jwt_service.refresh_access_token.return_value = "new_access_token"
        mock_jwt_service.decode_token.return_value = Mock(
            user_id=sample_user.id,
            token_type="refresh",
        )

        # When
        new_tokens = await auth_service.refresh_tokens(refresh_token)

        # Then
        assert isinstance(new_tokens, AuthTokens)
        assert new_tokens.access_token == "new_access_token"
        assert new_tokens.refresh_token == refresh_token
        assert new_tokens.token_type == "Bearer"
        
        mock_jwt_service.refresh_access_token.assert_called_once_with(
            refresh_token=refresh_token,
            email=sample_user.email,
            roles=sample_user.roles,
        )

    @pytest.mark.asyncio
    async def test_refresh_token_invalid(
        self,
        auth_service: AuthService,
        mock_jwt_service: Mock,
    ) -> None:
        """잘못된 리프레시 토큰으로 갱신 시도 테스트"""
        # Given
        refresh_token = "invalid_refresh_token"
        mock_jwt_service.decode_token.return_value = None

        # When & Then
        with pytest.raises(AuthenticationError) as exc_info:
            await auth_service.refresh_tokens(refresh_token)
        
        assert "유효하지 않은 리프레시 토큰" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_refresh_token_user_not_found(
        self,
        auth_service: AuthService,
        mock_user_repository: Mock,
        mock_jwt_service: Mock,
    ) -> None:
        """존재하지 않는 사용자의 토큰 갱신 시도 테스트"""
        # Given
        refresh_token = "valid_refresh_token"
        
        mock_jwt_service.decode_token.return_value = Mock(
            user_id="non-existent-user",
            token_type="refresh",
        )
        mock_user_repository.get_by_id = AsyncMock(return_value=None)

        # When & Then
        with pytest.raises(AuthenticationError) as exc_info:
            await auth_service.refresh_tokens(refresh_token)
        
        assert "사용자를 찾을 수 없습니다" in str(exc_info.value)

    def test_hash_password(self, auth_service: AuthService) -> None:
        """비밀번호 해시 테스트"""
        # Given
        password = "TestPassword123!"

        # When
        hashed = auth_service.hash_password(password)

        # Then
        assert hashed != password
        assert hashed.startswith("$2b$")
        assert len(hashed) > 50

    def test_verify_password_correct(self, auth_service: AuthService) -> None:
        """올바른 비밀번호 검증 테스트"""
        # Given
        password = "TestPassword123!"
        hashed = auth_service.hash_password(password)

        # When
        is_valid = auth_service.verify_password(password, hashed)

        # Then
        assert is_valid is True

    def test_verify_password_incorrect(self, auth_service: AuthService) -> None:
        """잘못된 비밀번호 검증 테스트"""
        # Given
        password = "TestPassword123!"
        hashed = auth_service.hash_password(password)
        wrong_password = "WrongPassword123!"

        # When
        is_valid = auth_service.verify_password(wrong_password, hashed)

        # Then
        assert is_valid is False