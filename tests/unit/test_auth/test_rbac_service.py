"""역할 기반 접근 제어(RBAC) 서비스 테스트"""

import pytest

from src.auth.models import Permission, ResourceType, ActionType
from src.auth.services.rbac_service import RBACService, PermissionDeniedError


class TestRBACService:
    """RBAC 서비스 테스트"""

    @pytest.fixture
    def rbac_service(self) -> RBACService:
        """RBAC 서비스 픽스처"""
        # 기본 역할과 권한 설정
        permissions = {
            # Admin은 모든 권한
            "admin": [
                Permission(resource=ResourceType.WEB_SEARCH, action=ActionType.READ),
                Permission(resource=ResourceType.WEB_SEARCH, action=ActionType.WRITE),
                Permission(resource=ResourceType.VECTOR_DB, action=ActionType.READ),
                Permission(resource=ResourceType.VECTOR_DB, action=ActionType.WRITE),
                Permission(resource=ResourceType.DATABASE, action=ActionType.READ),
                Permission(resource=ResourceType.DATABASE, action=ActionType.WRITE),
            ],
            # User는 읽기 권한만
            "user": [
                Permission(resource=ResourceType.WEB_SEARCH, action=ActionType.READ),
                Permission(resource=ResourceType.VECTOR_DB, action=ActionType.READ),
            ],
            # Guest는 웹 검색 읽기만
            "guest": [
                Permission(resource=ResourceType.WEB_SEARCH, action=ActionType.READ),
            ],
        }

        return RBACService(role_permissions=permissions)

    def test_check_permission_allowed(self, rbac_service: RBACService) -> None:
        """권한 허용 테스트"""
        # Given
        roles = ["user"]
        resource = ResourceType.WEB_SEARCH
        action = ActionType.READ

        # When
        is_allowed = rbac_service.check_permission(roles, resource, action)

        # Then
        assert is_allowed is True

    def test_check_permission_denied(self, rbac_service: RBACService) -> None:
        """권한 거부 테스트"""
        # Given
        roles = ["user"]
        resource = ResourceType.DATABASE
        action = ActionType.WRITE

        # When
        is_allowed = rbac_service.check_permission(roles, resource, action)

        # Then
        assert is_allowed is False

    def test_check_permission_multiple_roles(self, rbac_service: RBACService) -> None:
        """다중 역할 권한 확인 테스트"""
        # Given - guest 역할만으로는 DATABASE 읽기 불가, admin 역할 추가로 가능
        roles = ["guest", "admin"]
        resource = ResourceType.DATABASE
        action = ActionType.READ

        # When
        is_allowed = rbac_service.check_permission(roles, resource, action)

        # Then
        assert is_allowed is True

    def test_check_permission_unknown_role(self, rbac_service: RBACService) -> None:
        """알 수 없는 역할 권한 확인 테스트"""
        # Given
        roles = ["unknown_role"]
        resource = ResourceType.WEB_SEARCH
        action = ActionType.READ

        # When
        is_allowed = rbac_service.check_permission(roles, resource, action)

        # Then
        assert is_allowed is False

    def test_check_permission_empty_roles(self, rbac_service: RBACService) -> None:
        """빈 역할 목록 권한 확인 테스트"""
        # Given
        roles: list[str] = []
        resource = ResourceType.WEB_SEARCH
        action = ActionType.READ

        # When
        is_allowed = rbac_service.check_permission(roles, resource, action)

        # Then
        assert is_allowed is False

    def test_require_permission_success(self, rbac_service: RBACService) -> None:
        """권한 요구 성공 테스트"""
        # Given
        roles = ["admin"]
        resource = ResourceType.DATABASE
        action = ActionType.WRITE

        # When & Then - 예외가 발생하지 않아야 함
        rbac_service.require_permission(roles, resource, action)

    def test_require_permission_denied(self, rbac_service: RBACService) -> None:
        """권한 요구 실패 테스트"""
        # Given
        roles = ["guest"]
        resource = ResourceType.DATABASE
        action = ActionType.WRITE

        # When & Then
        with pytest.raises(PermissionDeniedError) as exc_info:
            rbac_service.require_permission(roles, resource, action)

        assert resource.value in str(exc_info.value)
        assert action.value in str(exc_info.value)

    def test_get_user_permissions(self, rbac_service: RBACService) -> None:
        """사용자 권한 목록 조회 테스트"""
        # Given
        roles = ["user"]

        # When
        permissions = rbac_service.get_user_permissions(roles)

        # Then
        assert len(permissions) == 2
        assert all(p.action == ActionType.READ for p in permissions)
        assert any(p.resource == ResourceType.WEB_SEARCH for p in permissions)
        assert any(p.resource == ResourceType.VECTOR_DB for p in permissions)

    def test_get_user_permissions_multiple_roles(
        self, rbac_service: RBACService
    ) -> None:
        """다중 역할의 권한 목록 조회 테스트"""
        # Given
        roles = ["user", "guest"]

        # When
        permissions = rbac_service.get_user_permissions(roles)

        # Then - 중복 제거되어야 함
        assert len(permissions) == 2  # user의 2개 권한 (guest는 user의 부분집합)

    def test_check_tool_permission_web_search(self, rbac_service: RBACService) -> None:
        """웹 검색 도구 권한 확인 테스트"""
        # Given
        roles_allowed = ["user", "admin"]
        roles_denied = [
            "guest"
        ]  # guest는 읽기만 가능하지만 도구 실행은 WRITE 권한 필요

        # When & Then
        assert rbac_service.check_tool_permission(roles_allowed, "search_web") is True
        assert rbac_service.check_tool_permission(roles_denied, "search_web") is False

    def test_check_tool_permission_vector_search(
        self, rbac_service: RBACService
    ) -> None:
        """벡터 검색 도구 권한 확인 테스트"""
        # Given
        roles_allowed = ["admin"]
        roles_denied = ["user", "guest"]

        # When & Then
        assert (
            rbac_service.check_tool_permission(roles_allowed, "search_vectors") is True
        )
        assert (
            rbac_service.check_tool_permission(roles_denied, "search_vectors") is False
        )

    def test_check_tool_permission_database_search(
        self, rbac_service: RBACService
    ) -> None:
        """데이터베이스 검색 도구 권한 확인 테스트"""
        # Given
        roles_allowed = ["admin"]
        roles_denied = ["user", "guest"]

        # When & Then
        assert (
            rbac_service.check_tool_permission(roles_allowed, "search_database") is True
        )
        assert (
            rbac_service.check_tool_permission(roles_denied, "search_database") is False
        )

    def test_check_tool_permission_search_all(self, rbac_service: RBACService) -> None:
        """전체 검색 도구 권한 확인 테스트"""
        # Given - search_all은 모든 리소스에 대한 권한 필요
        roles_allowed = ["admin"]
        roles_denied = ["user", "guest"]

        # When & Then
        assert rbac_service.check_tool_permission(roles_allowed, "search_all") is True
        assert rbac_service.check_tool_permission(roles_denied, "search_all") is False

    def test_check_tool_permission_unknown_tool(
        self, rbac_service: RBACService
    ) -> None:
        """알 수 없는 도구 권한 확인 테스트"""
        # Given
        roles = ["admin"]
        unknown_tool = "unknown_tool"

        # When
        is_allowed = rbac_service.check_tool_permission(roles, unknown_tool)

        # Then - 알 수 없는 도구는 거부
        assert is_allowed is False

    def test_add_role_permission(self, rbac_service: RBACService) -> None:
        """역할에 권한 추가 테스트"""
        # Given
        new_role = "developer"
        new_permission = Permission(
            resource=ResourceType.VECTOR_DB,
            action=ActionType.WRITE,
        )

        # When
        rbac_service.add_role_permission(new_role, new_permission)

        # Then
        is_allowed = rbac_service.check_permission(
            [new_role],
            ResourceType.VECTOR_DB,
            ActionType.WRITE,
        )
        assert is_allowed is True

    def test_remove_role_permission(self, rbac_service: RBACService) -> None:
        """역할에서 권한 제거 테스트"""
        # Given
        permission_to_remove = Permission(
            resource=ResourceType.WEB_SEARCH,
            action=ActionType.READ,
        )

        # When
        rbac_service.remove_role_permission("user", permission_to_remove)

        # Then
        is_allowed = rbac_service.check_permission(
            ["user"],
            ResourceType.WEB_SEARCH,
            ActionType.READ,
        )
        assert is_allowed is False

    def test_permission_inheritance(self, rbac_service: RBACService) -> None:
        """권한 상속 테스트 (상위 권한이 하위 권한 포함)"""
        # Given - WRITE 권한은 READ 권한을 암시적으로 포함
        rbac_service.enable_permission_inheritance = True

        # 새 역할에 WRITE 권한만 부여
        editor_role = "editor"
        rbac_service.add_role_permission(
            editor_role,
            Permission(resource=ResourceType.WEB_SEARCH, action=ActionType.WRITE),
        )

        # When - READ 권한 확인
        can_read = rbac_service.check_permission(
            [editor_role],
            ResourceType.WEB_SEARCH,
            ActionType.READ,
        )
        can_write = rbac_service.check_permission(
            [editor_role],
            ResourceType.WEB_SEARCH,
            ActionType.WRITE,
        )

        # Then
        assert can_read is True  # WRITE 권한이 READ를 포함
        assert can_write is True
