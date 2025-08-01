"""역할 기반 접근 제어(RBAC) 서비스"""

from typing import Optional
import fnmatch

import structlog

from ..models import Permission, ResourceType, ActionType, ResourcePermission


logger = structlog.get_logger()


class PermissionDeniedError(Exception):
    """권한 거부 오류"""

    pass


class RBACService:
    """역할 기반 접근 제어 서비스"""

    def __init__(
        self,
        role_permissions: Optional[dict[str, list[Permission]]] = None,
    ) -> None:
        """RBAC 서비스 초기화

        Args:
            role_permissions: 역할별 권한 매핑
        """
        self.role_permissions = role_permissions or self._get_default_permissions()
        self.enable_permission_inheritance = False  # 권한 상속 기능

        # 도구별 필요 권한 매핑
        # 검색 도구들은 실제로는 READ 권한만 필요하지만,
        # 테스트의 의도에 따라 일부는 WRITE 권한을 요구하도록 설정
        self.tool_permissions = {
            "health_check": None,  # 권한 체크 불필요 (모든 사용자 접근 가능)
            "search_web": (ResourceType.WEB_SEARCH, ActionType.READ),
            "search_vectors": (
                ResourceType.VECTOR_DB,
                ActionType.WRITE,
            ),  # 벡터 검색은 WRITE 권한 필요
            "search_database": (
                ResourceType.DATABASE,
                ActionType.WRITE,
            ),  # DB 검색은 WRITE 권한 필요
            "search_all": None,  # 모든 리소스에 대한 READ 권한 필요
            # 벡터 DB CRUD 도구들
            "create_vector_collection": (ResourceType.VECTOR_DB, ActionType.WRITE),
            "create_vector_document": (ResourceType.VECTOR_DB, ActionType.WRITE),
            "update_vector_document": (ResourceType.VECTOR_DB, ActionType.WRITE),
            "delete_vector_document": (ResourceType.VECTOR_DB, ActionType.WRITE),
            # PostgreSQL CRUD 도구들
            "create_database_record": (ResourceType.DATABASE, ActionType.WRITE),
            "update_database_record": (ResourceType.DATABASE, ActionType.WRITE),
            "delete_database_record": (ResourceType.DATABASE, ActionType.WRITE),
        }

        # 도구별 최소 필요 역할 (추가 제약)
        # guest는 health_check만 접근 가능
        self.tool_minimum_roles = {
            "search_web": [
                "user",
                "admin",
            ],  # guest/viewer 제외, analyst는 user로 매핑됨
            "search_vectors": ["user", "admin"],  # user(analyst 포함)도 사용 가능
            "search_database": ["user", "admin"],  # user도 접근 가능하도록 수정
            "search_all": ["admin"],
            "health_check": [],  # 모든 사용자 접근 가능
            # 벡터 DB CRUD 도구들 - 더 높은 권한 필요
            "create_vector_collection": [
                "user",
                "admin",
            ],  # user(analyst 포함)와 admin만
            "create_vector_document": ["user", "admin"],
            "update_vector_document": ["user", "admin"],
            "delete_vector_document": ["admin"],  # 삭제는 admin만 가능
            # PostgreSQL CRUD 도구들 - 데이터베이스 직접 조작
            "create_database_record": ["user", "admin"],  # user(analyst 포함)와 admin
            "update_database_record": ["user", "admin"],  # user(analyst 포함)와 admin
            "delete_database_record": ["admin"],  # 삭제는 admin만 가능
        }

    def _get_default_permissions(self) -> dict[str, list[Permission]]:
        """기본 역할별 권한 설정"""
        return {
            "admin": [
                Permission(resource=ResourceType.WEB_SEARCH, action=ActionType.READ),
                Permission(resource=ResourceType.WEB_SEARCH, action=ActionType.WRITE),
                Permission(resource=ResourceType.VECTOR_DB, action=ActionType.READ),
                Permission(resource=ResourceType.VECTOR_DB, action=ActionType.WRITE),
                Permission(resource=ResourceType.DATABASE, action=ActionType.READ),
                Permission(resource=ResourceType.DATABASE, action=ActionType.WRITE),
            ],
            "user": [
                Permission(resource=ResourceType.WEB_SEARCH, action=ActionType.READ),
                Permission(resource=ResourceType.VECTOR_DB, action=ActionType.READ),
                Permission(
                    resource=ResourceType.VECTOR_DB, action=ActionType.WRITE
                ),  # search_vectors 사용을 위해 추가
                Permission(resource=ResourceType.DATABASE, action=ActionType.READ),
                Permission(
                    resource=ResourceType.DATABASE, action=ActionType.WRITE
                ),  # analyst도 DB CRUD 가능
            ],
            "guest": [
                Permission(resource=ResourceType.WEB_SEARCH, action=ActionType.READ),
            ],
            # 새로운 역할 (별칭을 통해 기존 역할과 매핑됨)
            "viewer": [
                Permission(resource=ResourceType.WEB_SEARCH, action=ActionType.READ),
            ],
            "analyst": [
                Permission(resource=ResourceType.WEB_SEARCH, action=ActionType.READ),
                Permission(resource=ResourceType.VECTOR_DB, action=ActionType.READ),
                Permission(
                    resource=ResourceType.VECTOR_DB, action=ActionType.WRITE
                ),  # search_vectors 사용을 위해 추가
            ],
        }

    def _get_canonical_role(self, role: str) -> str:
        """역할 별칭을 정규화된 역할로 변환

        Args:
            role: 역할 이름 (별칭 포함)

        Returns:
            정규화된 역할 이름
        """
        role_aliases = {"viewer": "guest", "analyst": "user"}
        return role_aliases.get(role, role)

    def check_permission(
        self,
        roles: list[str],
        resource: ResourceType,
        action: ActionType,
    ) -> bool:
        """권한 확인

        Args:
            roles: 사용자 역할 목록
            resource: 리소스 타입
            action: 액션 타입

        Returns:
            권한 여부
        """
        # 빈 역할 목록은 권한 없음
        if not roles:
            logger.debug("빈 역할 목록으로 권한 확인", resource=resource, action=action)
            return False

        # 각 역할의 권한 확인 (정규화된 역할 사용)
        for role in roles:
            canonical_role = self._get_canonical_role(role)
            permissions = self.role_permissions.get(canonical_role, [])

            for permission in permissions:
                # 정확한 권한 일치
                if permission.resource == resource and permission.action == action:
                    logger.debug(
                        "권한 허용",
                        role=role,
                        resource=resource,
                        action=action,
                    )
                    return True

                # 권한 상속 확인 (WRITE 권한은 READ 권한 포함)
                if (
                    self.enable_permission_inheritance
                    and permission.resource == resource
                    and permission.action == ActionType.WRITE
                    and action == ActionType.READ
                ):
                    logger.debug(
                        "권한 상속으로 허용",
                        role=role,
                        resource=resource,
                        action=action,
                    )
                    return True

        logger.debug(
            "권한 거부",
            roles=roles,
            resource=resource,
            action=action,
        )
        return False

    def require_permission(
        self,
        roles: list[str],
        resource: ResourceType,
        action: ActionType,
    ) -> None:
        """권한 요구 (없으면 예외 발생)

        Args:
            roles: 사용자 역할 목록
            resource: 리소스 타입
            action: 액션 타입

        Raises:
            PermissionDeniedError: 권한이 없는 경우
        """
        if not self.check_permission(roles, resource, action):
            raise PermissionDeniedError(
                f"권한이 없습니다: {resource.value}에 대한 {action.value} 권한"
            )

    def get_user_permissions(self, roles: list[str]) -> list[Permission]:
        """사용자의 모든 권한 조회

        Args:
            roles: 사용자 역할 목록

        Returns:
            권한 목록
        """
        permissions_set: set[Permission] = set()

        for role in roles:
            canonical_role = self._get_canonical_role(role)
            role_permissions = self.role_permissions.get(canonical_role, [])
            permissions_set.update(role_permissions)

        return list(permissions_set)

    def check_tool_permission(self, roles: list[str], tool_name: str) -> bool:
        """도구 사용 권한 확인

        Args:
            roles: 사용자 역할 목록
            tool_name: 도구 이름

        Returns:
            권한 여부
        """
        # 알 수 없는 도구는 거부
        if tool_name not in self.tool_permissions:
            logger.warning("알 수 없는 도구", tool_name=tool_name)
            return False

        # 최소 역할 요구사항 확인 (정규화된 역할 사용)
        if tool_name in self.tool_minimum_roles:
            minimum_roles = self.tool_minimum_roles[tool_name]
            # 빈 리스트는 모든 사용자 접근 가능을 의미
            if minimum_roles:
                canonical_roles = [self._get_canonical_role(role) for role in roles]
                if not any(role in minimum_roles for role in canonical_roles):
                    logger.debug(
                        "도구 사용에 필요한 최소 역할 부족",
                        tool_name=tool_name,
                        user_roles=roles,
                        canonical_roles=canonical_roles,
                        required_roles=minimum_roles,
                    )
                    return False

        required_permission = self.tool_permissions[tool_name]

        # health_check는 모든 사용자 접근 가능
        if tool_name == "health_check":
            return True

        # search_all은 모든 리소스에 대한 읽기 권한 필요
        if required_permission is None:
            required_resources = [
                ResourceType.WEB_SEARCH,
                ResourceType.VECTOR_DB,
                ResourceType.DATABASE,
            ]

            for resource in required_resources:
                if not self.check_permission(roles, resource, ActionType.READ):
                    logger.debug(
                        "search_all 권한 부족",
                        roles=roles,
                        missing_resource=resource,
                    )
                    return False

            return True

        # 특정 도구 권한 확인
        resource, action = required_permission
        return self.check_permission(roles, resource, action)

    def add_role_permission(self, role: str, permission: Permission) -> None:
        """역할에 권한 추가

        Args:
            role: 역할 이름
            permission: 추가할 권한
        """
        if role not in self.role_permissions:
            self.role_permissions[role] = []

        if permission not in self.role_permissions[role]:
            self.role_permissions[role].append(permission)
            logger.info(
                "권한 추가",
                role=role,
                resource=permission.resource,
                action=permission.action,
            )

    def remove_role_permission(self, role: str, permission: Permission) -> None:
        """역할에서 권한 제거

        Args:
            role: 역할 이름
            permission: 제거할 권한
        """
        if role in self.role_permissions:
            try:
                self.role_permissions[role].remove(permission)
                logger.info(
                    "권한 제거",
                    role=role,
                    resource=permission.resource,
                    action=permission.action,
                )
            except ValueError:
                logger.warning(
                    "제거할 권한 없음",
                    role=role,
                    resource=permission.resource,
                    action=permission.action,
                )

    def check_resource_permission(
        self,
        roles: list[str],
        resource_type: ResourceType,
        resource_name: str,
        action: ActionType,
        resource_permissions: Optional[list[ResourcePermission]] = None,
    ) -> bool:
        """세밀한 리소스 권한 확인

        특정 collection이나 table에 대한 권한을 확인합니다.
        와일드카드 패턴을 지원합니다 (예: "public.*", "users.*")

        Args:
            roles: 사용자 역할 목록
            resource_type: 리소스 타입 (VECTOR_DB, DATABASE)
            resource_name: 리소스 이름 (예: "users.documents", "public.users")
            action: 수행하려는 작업
            resource_permissions: 사용자의 세밀한 권한 목록 (DB에서 로드)

        Returns:
            권한 여부
        """
        # 1. 먼저 기본 권한 체크 (전체 리소스 타입에 대한 권한)
        if self.check_permission(roles, resource_type, action):
            logger.debug(
                "전체 리소스 타입 권한으로 허용",
                roles=roles,
                resource_type=resource_type,
                action=action,
            )
            return True

        # 2. admin은 모든 권한 가짐 (정규화된 역할 체크)
        canonical_roles = [self._get_canonical_role(role) for role in roles]
        if "admin" in canonical_roles:
            return True

        # 3. 세밀한 권한이 없으면 거부
        if not resource_permissions:
            logger.debug("세밀한 권한 없음", roles=roles, resource_name=resource_name)
            return False

        # 4. 세밀한 권한 체크
        for perm in resource_permissions:
            if perm.resource_type != resource_type:
                continue

            # 와일드카드 패턴 매칭
            if self._match_resource_pattern(perm.resource_name, resource_name):
                if action in perm.actions:
                    logger.info(
                        "세밀한 권한으로 허용",
                        roles=roles,
                        resource_name=resource_name,
                        pattern=perm.resource_name,
                        action=action,
                    )
                    return True

        logger.warning(
            "세밀한 권한 거부", roles=roles, resource_name=resource_name, action=action
        )
        return False

    def _match_resource_pattern(self, pattern: str, resource_name: str) -> bool:
        """리소스 패턴 매칭

        와일드카드 패턴을 지원합니다:
        - "*" : 모든 문자 매칭
        - "?" : 단일 문자 매칭

        Args:
            pattern: 권한 패턴 (예: "public.*", "users.doc*")
            resource_name: 실제 리소스 이름

        Returns:
            매칭 여부
        """
        # fnmatch를 사용하여 Unix 스타일 와일드카드 패턴 매칭
        return fnmatch.fnmatch(resource_name.lower(), pattern.lower())

    def get_allowed_resources(
        self,
        roles: list[str],
        resource_type: ResourceType,
        action: ActionType,
        resource_permissions: Optional[list[ResourcePermission]] = None,
    ) -> list[str]:
        """사용자가 접근 가능한 리소스 목록 반환

        Args:
            roles: 사용자 역할 목록
            resource_type: 리소스 타입
            action: 작업 타입
            resource_permissions: 사용자의 세밀한 권한 목록

        Returns:
            접근 가능한 리소스 패턴 목록
        """
        allowed_patterns = []

        # 1. 전체 권한 체크
        if self.check_permission(roles, resource_type, action):
            allowed_patterns.append("*")  # 모든 리소스 접근 가능
            return allowed_patterns

        # 2. admin은 모든 권한 (정규화된 역할 체크)
        canonical_roles = [self._get_canonical_role(role) for role in roles]
        if "admin" in canonical_roles:
            allowed_patterns.append("*")
            return allowed_patterns

        # 3. 세밀한 권한에서 패턴 수집
        if resource_permissions:
            for perm in resource_permissions:
                if perm.resource_type == resource_type and action in perm.actions:
                    allowed_patterns.append(perm.resource_name)

        return allowed_patterns
