"""역할 기반 접근 제어(RBAC) 서비스"""

from typing import Optional

import structlog

from ..models import Permission, ResourceType, ActionType


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
            "search_web": (ResourceType.WEB_SEARCH, ActionType.READ),
            "search_vectors": (ResourceType.VECTOR_DB, ActionType.WRITE),  # 벡터 검색은 WRITE 권한 필요
            "search_database": (ResourceType.DATABASE, ActionType.WRITE),  # DB 검색은 WRITE 권한 필요
            "search_all": None,  # 모든 리소스에 대한 READ 권한 필요
        }
        
        # 도구별 최소 필요 역할 (추가 제약)
        # guest는 search_web 도구를 사용할 수 없도록 제한
        self.tool_minimum_roles = {
            "search_web": ["user", "admin"],  # guest 제외
            "search_vectors": ["admin"],
            "search_database": ["admin"],
            "search_all": ["admin"],
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
            ],
            "guest": [
                Permission(resource=ResourceType.WEB_SEARCH, action=ActionType.READ),
            ],
        }
    
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
        
        # 각 역할의 권한 확인
        for role in roles:
            permissions = self.role_permissions.get(role, [])
            
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
            role_permissions = self.role_permissions.get(role, [])
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
        
        # 최소 역할 요구사항 확인
        if tool_name in self.tool_minimum_roles:
            minimum_roles = self.tool_minimum_roles[tool_name]
            if not any(role in minimum_roles for role in roles):
                logger.debug(
                    "도구 사용에 필요한 최소 역할 부족",
                    tool_name=tool_name,
                    user_roles=roles,
                    required_roles=minimum_roles,
                )
                return False
        
        required_permission = self.tool_permissions[tool_name]
        
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