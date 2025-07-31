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

    def test_create_token_with_scopes(self, jwt_service: JWTService) -> None:
        """스코프가 포함된 토큰 생성 테스트"""
        # Given
        user_id = "test-user-123"
        email = "test@example.com"
        roles = ["user"]
        scopes = ["read:vectors", "write:database", "admin:users"]

        # When
        token = jwt_service.create_access_token(
            user_id=user_id,
            email=email,
            roles=roles,
            scopes=scopes,
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
        assert decoded["scopes"] == scopes
        assert decoded["type"] == "access"

    def test_create_token_with_resource_permissions(self, jwt_service: JWTService) -> None:
        """리소스 권한이 포함된 토큰 생성 테스트"""
        # Given
        user_id = "test-user-123"
        email = "test@example.com"
        roles = ["user"]
        resource_permissions = {
            "collection1": ["read", "write"],
            "table1": ["read"],
            "collection2": ["read", "write", "delete"]
        }

        # When
        token = jwt_service.create_access_token(
            user_id=user_id,
            email=email,
            roles=roles,
            resource_permissions=resource_permissions,
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
        assert decoded["resource_permissions"] == resource_permissions
        assert decoded["type"] == "access"

    def test_create_token_with_all_new_fields(self, jwt_service: JWTService) -> None:
        """모든 새로운 필드가 포함된 토큰 생성 테스트"""
        # Given
        user_id = "test-user-123"
        email = "test@example.com"
        roles = ["user", "admin"]
        scopes = ["read:vectors", "write:database"]
        resource_permissions = {
            "collection1": ["read", "write"],
            "table1": ["read"]
        }

        # When
        token = jwt_service.create_access_token(
            user_id=user_id,
            email=email,
            roles=roles,
            scopes=scopes,
            resource_permissions=resource_permissions,
        )

        # Then
        decoded = jwt.decode(
            token,
            jwt_service.secret_key,
            algorithms=[jwt_service.algorithm],
        )
        assert decoded["scopes"] == scopes
        assert decoded["resource_permissions"] == resource_permissions

    def test_decode_token_with_scopes(self, jwt_service: JWTService) -> None:
        """스코프가 포함된 토큰 디코드 테스트"""
        # Given
        user_id = "test-user-123"
        email = "test@example.com"
        roles = ["user"]
        scopes = ["read:vectors", "write:database"]
        token = jwt_service.create_access_token(
            user_id=user_id,
            email=email,
            roles=roles,
            scopes=scopes,
        )

        # When
        token_data = jwt_service.decode_token(token)

        # Then
        assert token_data is not None
        assert token_data.user_id == user_id
        assert token_data.email == email
        assert token_data.roles == roles
        assert token_data.scopes == scopes
        assert token_data.resource_permissions is None  # 포함되지 않음

    def test_decode_token_with_resource_permissions(self, jwt_service: JWTService) -> None:
        """리소스 권한이 포함된 토큰 디코드 테스트"""
        # Given
        user_id = "test-user-123"
        email = "test@example.com"
        roles = ["user"]
        resource_permissions = {"collection1": ["read", "write"]}
        token = jwt_service.create_access_token(
            user_id=user_id,
            email=email,
            roles=roles,
            resource_permissions=resource_permissions,
        )

        # When
        token_data = jwt_service.decode_token(token)

        # Then
        assert token_data is not None
        assert token_data.user_id == user_id
        assert token_data.email == email
        assert token_data.roles == roles
        assert token_data.scopes is None  # 포함되지 않음
        assert token_data.resource_permissions == resource_permissions

    def test_backward_compatibility_legacy_token(self, jwt_service: JWTService) -> None:
        """기존 토큰 (새 필드 없음) 하위 호환성 테스트"""
        # Given - 기존 방식으로 생성된 토큰 (새 필드 없음)
        user_id = "test-user-123"
        email = "test@example.com"
        roles = ["user"]
        
        # 기존 방식으로 토큰 생성 (scopes, resource_permissions 없음)
        legacy_token = jwt_service.create_access_token(
            user_id=user_id,
            email=email,
            roles=roles,
        )

        # When
        token_data = jwt_service.decode_token(legacy_token)

        # Then - 기존 필드들은 정상적으로 디코드되고, 새 필드들은 None
        assert token_data is not None
        assert token_data.user_id == user_id
        assert token_data.email == email
        assert token_data.roles == roles
        assert token_data.token_type == "access"
        assert token_data.scopes is None  # 새 필드는 None으로 기본값
        assert token_data.resource_permissions is None  # 새 필드는 None으로 기본값

    def test_backward_compatibility_manual_legacy_token(self, jwt_service: JWTService) -> None:
        """수동으로 생성한 기존 토큰 형식 호환성 테스트"""
        # Given - 기존 토큰 형식을 수동으로 생성 (실제 기존 시스템에서 발급된 토큰 시뮬레이션)
        payload = {
            "sub": "legacy-user-456",
            "email": "legacy@example.com",
            "roles": ["user", "admin"],
            "type": "access",
            "exp": datetime.now(UTC) + timedelta(minutes=30),
            "iat": datetime.now(UTC),
            # scopes, resource_permissions 필드 없음 (기존 토큰)
        }
        legacy_token = jwt.encode(
            payload,
            jwt_service.secret_key,
            algorithm=jwt_service.algorithm,
        )

        # When
        token_data = jwt_service.decode_token(legacy_token)

        # Then - 기존 필드들은 정상 디코드, 새 필드들은 안전하게 None 처리
        assert token_data is not None
        assert token_data.user_id == "legacy-user-456"
        assert token_data.email == "legacy@example.com"
        assert token_data.roles == ["user", "admin"]
        assert token_data.token_type == "access"
        assert token_data.scopes is None
        assert token_data.resource_permissions is None

    def test_mixed_tokens_compatibility(self, jwt_service: JWTService) -> None:
        """기존 토큰과 새 토큰이 혼재된 상황 테스트"""
        # Given
        user_id = "test-user-789"
        email = "mixed@example.com"
        roles = ["user"]

        # 기존 토큰 생성
        legacy_token = jwt_service.create_access_token(
            user_id=user_id,
            email=email,
            roles=roles,
        )

        # 새로운 토큰 생성 (스코프 포함)
        new_token = jwt_service.create_access_token(
            user_id=user_id,
            email=email,
            roles=roles,
            scopes=["read:vectors"],
            resource_permissions={"collection1": ["read"]},
        )

        # When - 두 토큰 모두 디코드
        legacy_data = jwt_service.decode_token(legacy_token)
        new_data = jwt_service.decode_token(new_token)

        # Then - 두 토큰 모두 정상 디코드, 기본 필드들은 동일
        assert legacy_data is not None
        assert new_data is not None
        
        # 공통 필드 검증
        assert legacy_data.user_id == new_data.user_id == user_id
        assert legacy_data.email == new_data.email == email
        assert legacy_data.roles == new_data.roles == roles
        
        # 새 필드 차이 검증
        assert legacy_data.scopes is None
        assert legacy_data.resource_permissions is None
        assert new_data.scopes == ["read:vectors"]
        assert new_data.resource_permissions == {"collection1": ["read"]}

    def test_empty_scopes_and_permissions(self, jwt_service: JWTService) -> None:
        """빈 스코프와 권한으로 토큰 생성 테스트"""
        # Given
        user_id = "test-user-empty"
        email = "empty@example.com"
        roles = ["user"]
        scopes = []  # 빈 리스트
        resource_permissions = {}  # 빈 딕셔너리

        # When
        token = jwt_service.create_access_token(
            user_id=user_id,
            email=email,
            roles=roles,
            scopes=scopes,
            resource_permissions=resource_permissions,
        )

        # Then
        token_data = jwt_service.decode_token(token)
        assert token_data is not None
        assert token_data.scopes == []
        assert token_data.resource_permissions == {}

    def test_none_vs_empty_fields_handling(self, jwt_service: JWTService) -> None:
        """None과 빈 값 처리 차이 테스트"""
        # Given
        user_id = "test-user-none-empty"
        email = "test@example.com"
        roles = ["user"]

        # None으로 설정한 토큰
        token_none = jwt_service.create_access_token(
            user_id=user_id,
            email=email,
            roles=roles,
            scopes=None,
            resource_permissions=None,
        )

        # 빈 값으로 설정한 토큰
        token_empty = jwt_service.create_access_token(
            user_id=user_id,
            email=email,
            roles=roles,
            scopes=[],
            resource_permissions={},
        )

        # When
        data_none = jwt_service.decode_token(token_none)
        data_empty = jwt_service.decode_token(token_empty)

        # Then
        assert data_none is not None
        assert data_empty is not None
        
        # None인 경우 필드가 토큰에 포함되지 않음
        assert data_none.scopes is None
        assert data_none.resource_permissions is None
        
        # 빈 값인 경우 빈 컨테이너로 포함됨
        assert data_empty.scopes == []
        assert data_empty.resource_permissions == {}
