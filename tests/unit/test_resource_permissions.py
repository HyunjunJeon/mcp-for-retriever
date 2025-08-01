"""
세밀한 리소스 권한 시스템 단위 테스트

리소스별 권한 검증 로직을 테스트합니다.
"""

import pytest
from src.auth.models import ResourceType, ActionType, ResourcePermission
from src.auth.services.rbac_service import RBACService
from src.auth.services.permission_service import PermissionService


@pytest.mark.asyncio
class TestResourcePermissions:
    """리소스 권한 단위 테스트"""

    def setup_method(self):
        """테스트 셋업"""
        self.rbac_service = RBACService()
        self.permission_service = PermissionService(db_conn=None)

    def test_wildcard_pattern_matching(self):
        """와일드카드 패턴 매칭 테스트"""
        # 다양한 패턴 테스트
        test_cases = [
            ("public.*", "public.users", True),
            ("public.*", "public.orders", True),
            ("public.*", "private.users", False),
            ("users.*", "users.documents", True),
            ("users.*", "users.profiles.v2", True),
            ("users.*", "user.data", False),
            ("*", "anything.goes", True),
            ("*.users", "public.users", True),
            ("*.users", "private.users", True),
            ("*.users", "users", False),
        ]

        for pattern, resource_name, expected in test_cases:
            result = self.rbac_service._match_resource_pattern(pattern, resource_name)
            assert result == expected, (
                f"Pattern {pattern} vs {resource_name}: expected {expected}, got {result}"
            )

    def test_basic_role_permissions(self):
        """기본 역할별 권한 테스트"""
        # User 역할: public.* 읽기 권한
        assert not self.rbac_service.check_permission(
            ["user"], ResourceType.DATABASE, ActionType.READ
        )  # 전체 DATABASE 권한은 없음

        # Admin 역할: 모든 권한
        assert self.rbac_service.check_permission(
            ["admin"], ResourceType.DATABASE, ActionType.WRITE
        )
        assert self.rbac_service.check_permission(
            ["admin"], ResourceType.VECTOR_DB, ActionType.WRITE
        )

    def test_resource_level_permissions(self):
        """리소스 레벨 권한 테스트"""
        # 기본 역할 권한 가져오기
        user_permissions = self.permission_service._get_default_role_permissions(
            ["user"]
        )

        # User는 public.* 읽기 권한 있음
        has_public_read = any(
            p.resource_type == ResourceType.DATABASE
            and p.resource_name == "public.*"
            and ActionType.READ in p.actions
            for p in user_permissions
        )
        assert has_public_read

        # User는 users.* collection 읽기 권한 있음
        has_users_read = any(
            p.resource_type == ResourceType.VECTOR_DB
            and p.resource_name == "users.*"
            and ActionType.READ in p.actions
            for p in user_permissions
        )
        assert has_users_read

    def test_check_resource_permission(self):
        """세밀한 리소스 권한 체크 테스트"""
        # 테스트용 권한 설정
        user_permissions = [
            ResourcePermission(
                resource_type=ResourceType.DATABASE,
                resource_name="public.*",
                actions=[ActionType.READ],
            ),
            ResourcePermission(
                resource_type=ResourceType.VECTOR_DB,
                resource_name="users.*",
                actions=[ActionType.READ],
            ),
        ]

        # public.users 테이블 읽기 - 성공해야 함
        assert self.rbac_service.check_resource_permission(
            ["user"],
            ResourceType.DATABASE,
            "public.users",
            ActionType.READ,
            user_permissions,
        )

        # private.users 테이블 읽기 - 실패해야 함
        assert not self.rbac_service.check_resource_permission(
            ["user"],
            ResourceType.DATABASE,
            "private.users",
            ActionType.READ,
            user_permissions,
        )

        # users.documents collection 읽기 - 성공해야 함
        assert self.rbac_service.check_resource_permission(
            ["user"],
            ResourceType.VECTOR_DB,
            "users.documents",
            ActionType.READ,
            user_permissions,
        )

        # admin.secrets collection 읽기 - 실패해야 함
        assert not self.rbac_service.check_resource_permission(
            ["user"],
            ResourceType.VECTOR_DB,
            "admin.secrets",
            ActionType.READ,
            user_permissions,
        )

    def test_admin_bypass(self):
        """Admin 역할의 모든 권한 우회 테스트"""
        # Admin은 권한 설정 없이도 모든 리소스 접근 가능
        assert self.rbac_service.check_resource_permission(
            ["admin"],
            ResourceType.DATABASE,
            "super.secret.table",
            ActionType.WRITE,
            [],  # 빈 권한 목록
        )

        assert self.rbac_service.check_resource_permission(
            ["admin"],
            ResourceType.VECTOR_DB,
            "classified.documents",
            ActionType.DELETE,
            [],  # 빈 권한 목록
        )

    def test_power_user_permissions(self):
        """Power user 권한 테스트"""
        power_permissions = self.permission_service._get_default_role_permissions(
            ["power_user"]
        )

        # 모든 벡터DB 읽기 가능
        has_vector_read = any(
            p.resource_type == ResourceType.VECTOR_DB
            and p.resource_name == "*"
            and ActionType.READ in p.actions
            for p in power_permissions
        )
        assert has_vector_read

        # analytics.* 스키마 읽기/쓰기 가능
        has_analytics_write = any(
            p.resource_type == ResourceType.DATABASE
            and p.resource_name == "analytics.*"
            and ActionType.WRITE in p.actions
            for p in power_permissions
        )
        assert has_analytics_write

    def test_get_allowed_resources(self):
        """접근 가능한 리소스 목록 조회 테스트"""
        # User의 접근 가능한 패턴
        user_permissions = [
            ResourcePermission(
                resource_type=ResourceType.DATABASE,
                resource_name="public.*",
                actions=[ActionType.READ],
            ),
            ResourcePermission(
                resource_type=ResourceType.VECTOR_DB,
                resource_name="users.*",
                actions=[ActionType.READ],
            ),
        ]

        # DATABASE 리소스 조회
        allowed_db = self.rbac_service.get_allowed_resources(
            ["user"], ResourceType.DATABASE, ActionType.READ, user_permissions
        )
        assert "public.*" in allowed_db

        # VECTOR_DB 리소스 조회
        allowed_vector = self.rbac_service.get_allowed_resources(
            ["user"], ResourceType.VECTOR_DB, ActionType.READ, user_permissions
        )
        assert "users.*" in allowed_vector

        # Admin은 모든 리소스 접근 가능
        admin_allowed = self.rbac_service.get_allowed_resources(
            ["admin"], ResourceType.DATABASE, ActionType.WRITE, []
        )
        assert "*" in admin_allowed
