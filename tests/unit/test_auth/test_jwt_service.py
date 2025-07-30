"""JWT 토큰 서비스 테스트"""

import asyncio
from datetime import datetime, timedelta, UTC
from typing import Any

import pytest
from jose import jwt, JWTError

from src.auth.services.jwt_service import JWTService, TokenData


class TestJWTService:
    """JWT 서비스 테스트"""

    @pytest.fixture
    def jwt_service(self) -> JWTService:
        """JWT 서비스 픽스처"""
        return JWTService(
            secret_key="test-secret-key-for-testing-only",
            algorithm="HS256",
            access_token_expire_minutes=30,
            refresh_token_expire_minutes=60 * 24 * 7,  # 7일
        )

    def test_create_access_token(self, jwt_service: JWTService) -> None:
        """액세스 토큰 생성 테스트"""
        # Given
        user_id = "test-user-123"
        email = "test@example.com"
        roles = ["user", "admin"]

        # When
        token = jwt_service.create_access_token(
            user_id=user_id,
            email=email,
            roles=roles,
        )

        # Then
        assert isinstance(token, str)
        assert len(token) > 0

        # 토큰 디코드하여 검증
        decoded = jwt.decode(
            token,
            jwt_service.secret_key,
            algorithms=[jwt_service.algorithm],
        )
        assert decoded["sub"] == user_id
        assert decoded["email"] == email
        assert decoded["roles"] == roles
        assert decoded["type"] == "access"
        assert "exp" in decoded
        assert "iat" in decoded

    def test_create_refresh_token(self, jwt_service: JWTService) -> None:
        """리프레시 토큰 생성 테스트"""
        # Given
        user_id = "test-user-123"

        # When
        token = jwt_service.create_refresh_token(user_id=user_id)

        # Then
        assert isinstance(token, str)
        assert len(token) > 0

        # 토큰 디코드하여 검증
        decoded = jwt.decode(
            token,
            jwt_service.secret_key,
            algorithms=[jwt_service.algorithm],
        )
        assert decoded["sub"] == user_id
        assert decoded["type"] == "refresh"
        assert "exp" in decoded
        assert "iat" in decoded

    def test_decode_token_success(self, jwt_service: JWTService) -> None:
        """토큰 디코드 성공 테스트"""
        # Given
        user_id = "test-user-123"
        email = "test@example.com"
        roles = ["user"]
        token = jwt_service.create_access_token(
            user_id=user_id,
            email=email,
            roles=roles,
        )

        # When
        token_data = jwt_service.decode_token(token)

        # Then
        assert token_data is not None
        assert token_data.user_id == user_id
        assert token_data.email == email
        assert token_data.roles == roles
        assert token_data.token_type == "access"

    def test_decode_invalid_token(self, jwt_service: JWTService) -> None:
        """잘못된 토큰 디코드 테스트"""
        # Given
        invalid_token = "invalid.token.here"

        # When
        token_data = jwt_service.decode_token(invalid_token)

        # Then
        assert token_data is None

    def test_decode_expired_token(self, jwt_service: JWTService) -> None:
        """만료된 토큰 디코드 테스트"""
        # Given
        payload = {
            "sub": "test-user-123",
            "email": "test@example.com",
            "roles": ["user"],
            "type": "access",
            "exp": datetime.now(UTC) - timedelta(hours=1),  # 1시간 전 만료
            "iat": datetime.now(UTC) - timedelta(hours=2),
        }
        expired_token = jwt.encode(
            payload,
            jwt_service.secret_key,
            algorithm=jwt_service.algorithm,
        )

        # When
        token_data = jwt_service.decode_token(expired_token)

        # Then
        assert token_data is None

    def test_verify_token_success(self, jwt_service: JWTService) -> None:
        """토큰 검증 성공 테스트"""
        # Given
        token = jwt_service.create_access_token(
            user_id="test-user-123",
            email="test@example.com",
            roles=["user"],
        )

        # When
        is_valid = jwt_service.verify_token(token)

        # Then
        assert is_valid is True

    def test_verify_invalid_token(self, jwt_service: JWTService) -> None:
        """잘못된 토큰 검증 테스트"""
        # Given
        invalid_token = "invalid.token.here"

        # When
        is_valid = jwt_service.verify_token(invalid_token)

        # Then
        assert is_valid is False

    def test_verify_token_with_wrong_type(self, jwt_service: JWTService) -> None:
        """잘못된 타입의 토큰 검증 테스트"""
        # Given
        refresh_token = jwt_service.create_refresh_token(user_id="test-user-123")

        # When - 액세스 토큰으로 검증하려고 시도
        is_valid = jwt_service.verify_token(refresh_token, token_type="access")

        # Then
        assert is_valid is False

    def test_refresh_access_token(self, jwt_service: JWTService) -> None:
        """액세스 토큰 갱신 테스트"""
        # Given
        user_id = "test-user-123"
        email = "test@example.com"
        roles = ["user", "admin"]
        
        # 먼저 리프레시 토큰 생성
        refresh_token = jwt_service.create_refresh_token(user_id=user_id)
        
        # When
        new_access_token = jwt_service.refresh_access_token(
            refresh_token=refresh_token,
            email=email,
            roles=roles,
        )

        # Then
        assert new_access_token is not None
        
        # 새 액세스 토큰 검증
        token_data = jwt_service.decode_token(new_access_token)
        assert token_data is not None
        assert token_data.user_id == user_id
        assert token_data.email == email
        assert token_data.roles == roles
        assert token_data.token_type == "access"

    def test_refresh_with_invalid_token(self, jwt_service: JWTService) -> None:
        """잘못된 리프레시 토큰으로 갱신 시도 테스트"""
        # Given
        invalid_token = "invalid.refresh.token"

        # When
        new_access_token = jwt_service.refresh_access_token(
            refresh_token=invalid_token,
            email="test@example.com",
            roles=["user"],
        )

        # Then
        assert new_access_token is None

    def test_refresh_with_access_token(self, jwt_service: JWTService) -> None:
        """액세스 토큰으로 갱신 시도 테스트"""
        # Given
        access_token = jwt_service.create_access_token(
            user_id="test-user-123",
            email="test@example.com",
            roles=["user"],
        )

        # When - 액세스 토큰을 리프레시 토큰으로 사용 시도
        new_access_token = jwt_service.refresh_access_token(
            refresh_token=access_token,
            email="test@example.com",
            roles=["user"],
        )

        # Then
        assert new_access_token is None

    def test_custom_claims_in_token(self, jwt_service: JWTService) -> None:
        """토큰에 커스텀 클레임 추가 테스트"""
        # Given
        user_id = "test-user-123"
        email = "test@example.com"
        roles = ["user"]
        custom_claims = {
            "department": "engineering",
            "team": "backend",
        }

        # When
        token = jwt_service.create_access_token(
            user_id=user_id,
            email=email,
            roles=roles,
            additional_claims=custom_claims,
        )

        # Then
        decoded = jwt.decode(
            token,
            jwt_service.secret_key,
            algorithms=[jwt_service.algorithm],
        )
        assert decoded["department"] == "engineering"
        assert decoded["team"] == "backend"