"""
리소스 권한 관리 서비스

세밀한 리소스 권한을 관리하는 서비스입니다.
DB에서 권한을 로드하고 캐싱합니다.
"""

from typing import Optional
from asyncpg import Connection
import structlog

from ..models import ResourceType, ActionType, ResourcePermission


logger = structlog.get_logger()


class PermissionService:
    """리소스 권한 관리 서비스"""

    def __init__(self, db_conn: Optional[Connection] = None):
        """
        권한 서비스 초기화

        Args:
            db_conn: PostgreSQL 연결 (선택사항)
        """
        self.db_conn = db_conn
        self._permission_cache: dict[int, list[ResourcePermission]] = {}

    async def get_user_resource_permissions(
        self, user_id: Optional[int] = None, roles: Optional[list[str]] = None
    ) -> list[ResourcePermission]:
        """
        사용자의 세밀한 리소스 권한 조회

        사용자 ID 또는 역할 기반으로 권한을 조회합니다.

        Args:
            user_id: 사용자 ID
            roles: 역할 목록

        Returns:
            리소스 권한 목록
        """
        if not self.db_conn:
            # DB 연결이 없으면 기본 역할 기반 권한 반환
            return self._get_default_role_permissions(roles or [])

        permissions = []

        try:
            # 1. 사용자별 권한 조회
            if user_id:
                if user_id in self._permission_cache:
                    return self._permission_cache[user_id]

                user_perms = await self._fetch_user_permissions(user_id)
                permissions.extend(user_perms)

            # 2. 역할별 권한 조회
            if roles:
                role_perms = await self._fetch_role_permissions(roles)
                permissions.extend(role_perms)

            # 중복 제거 (동일한 리소스에 대한 권한은 합침)
            merged_permissions = self._merge_permissions(permissions)

            # 캐싱
            if user_id:
                self._permission_cache[user_id] = merged_permissions

            return merged_permissions

        except Exception as e:
            logger.error("권한 조회 실패", error=str(e))
            # 에러 시 기본 권한 반환
            return self._get_default_role_permissions(roles or [])

    async def _fetch_user_permissions(self, user_id: int) -> list[ResourcePermission]:
        """사용자별 권한 DB 조회"""
        query = """
            SELECT resource_type, resource_name, actions, conditions
            FROM resource_permissions
            WHERE user_id = $1 AND (expires_at IS NULL OR expires_at > NOW())
        """

        rows = await self.db_conn.fetch(query, user_id)

        permissions = []
        for row in rows:
            perm = ResourcePermission(
                resource_type=ResourceType(row["resource_type"]),
                resource_name=row["resource_name"],
                actions=[ActionType(a) for a in row["actions"]],
                conditions=row["conditions"],
            )
            permissions.append(perm)

        return permissions

    async def _fetch_role_permissions(
        self, roles: list[str]
    ) -> list[ResourcePermission]:
        """역할별 권한 DB 조회"""
        query = """
            SELECT DISTINCT resource_type, resource_name, actions, conditions
            FROM resource_permissions
            WHERE role_name = ANY($1::text[]) AND (expires_at IS NULL OR expires_at > NOW())
        """

        rows = await self.db_conn.fetch(query, roles)

        permissions = []
        for row in rows:
            perm = ResourcePermission(
                resource_type=ResourceType(row["resource_type"]),
                resource_name=row["resource_name"],
                actions=[ActionType(a) for a in row["actions"]],
                conditions=row["conditions"],
            )
            permissions.append(perm)

        return permissions

    def _merge_permissions(
        self, permissions: list[ResourcePermission]
    ) -> list[ResourcePermission]:
        """
        중복 권한 병합

        동일한 리소스에 대한 여러 권한을 하나로 합칩니다.
        """
        merged: dict[tuple[ResourceType, str], ResourcePermission] = {}

        for perm in permissions:
            key = (perm.resource_type, perm.resource_name)

            if key in merged:
                # 기존 권한에 액션 추가
                existing = merged[key]
                existing.actions = list(set(existing.actions + perm.actions))
            else:
                # 새 권한 추가
                merged[key] = ResourcePermission(
                    resource_type=perm.resource_type,
                    resource_name=perm.resource_name,
                    actions=perm.actions.copy(),
                    conditions=perm.conditions,
                )

        return list(merged.values())

    def _get_default_role_permissions(
        self, roles: list[str]
    ) -> list[ResourcePermission]:
        """
        기본 역할별 권한 (하드코딩)

        DB를 사용할 수 없을 때 사용합니다.
        """
        permissions = []

        if "user" in roles:
            # 기본 사용자: public.* 읽기, users.* 읽기
            permissions.extend(
                [
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
            )

        if "power_user" in roles:
            # 파워 유저: 모든 벡터DB 읽기, analytics.* 읽기/쓰기
            permissions.extend(
                [
                    ResourcePermission(
                        resource_type=ResourceType.VECTOR_DB,
                        resource_name="*",
                        actions=[ActionType.READ],
                    ),
                    ResourcePermission(
                        resource_type=ResourceType.DATABASE,
                        resource_name="analytics.*",
                        actions=[ActionType.READ, ActionType.WRITE],
                    ),
                ]
            )

        # admin은 RBAC 서비스에서 직접 처리 (모든 권한)

        return self._merge_permissions(permissions)

    def clear_cache(self, user_id: Optional[int] = None) -> None:
        """
        권한 캐시 클리어

        Args:
            user_id: 특정 사용자 캐시만 클리어 (None이면 전체)
        """
        if user_id:
            self._permission_cache.pop(user_id, None)
        else:
            self._permission_cache.clear()

    async def grant_permission(
        self,
        user_id: Optional[int],
        role_name: Optional[str],
        resource_type: ResourceType,
        resource_name: str,
        actions: list[ActionType],
        granted_by: int,
    ) -> None:
        """
        권한 부여

        사용자 또는 역할에 권한을 부여합니다.

        Args:
            user_id: 사용자 ID (역할 권한인 경우 None)
            role_name: 역할 이름 (사용자 권한인 경우 None)
            resource_type: 리소스 타입
            resource_name: 리소스 이름/패턴
            actions: 허용할 액션 목록
            granted_by: 권한을 부여한 사용자 ID
        """
        if not self.db_conn:
            raise RuntimeError("DB 연결이 필요합니다")

        if not user_id and not role_name:
            raise ValueError("user_id 또는 role_name 중 하나는 필수입니다")

        query = """
            INSERT INTO resource_permissions 
            (user_id, role_name, resource_type, resource_name, actions, granted_by)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (user_id, resource_type, resource_name) 
            DO UPDATE SET actions = $5, granted_by = $6, granted_at = NOW()
        """

        await self.db_conn.execute(
            query,
            user_id,
            role_name,
            resource_type.value,
            resource_name,
            [a.value for a in actions],
            granted_by,
        )

        # 캐시 클리어
        if user_id:
            self.clear_cache(user_id)

        logger.info(
            "권한 부여 완료",
            user_id=user_id,
            role_name=role_name,
            resource_type=resource_type,
            resource_name=resource_name,
            actions=actions,
        )

    async def revoke_permission(
        self,
        user_id: Optional[int],
        role_name: Optional[str],
        resource_type: ResourceType,
        resource_name: str,
    ) -> None:
        """
        권한 회수

        Args:
            user_id: 사용자 ID
            role_name: 역할 이름
            resource_type: 리소스 타입
            resource_name: 리소스 이름/패턴
        """
        if not self.db_conn:
            raise RuntimeError("DB 연결이 필요합니다")

        conditions = []
        params = []

        if user_id:
            conditions.append("user_id = $1")
            params.append(user_id)
        elif role_name:
            conditions.append("role_name = $1")
            params.append(role_name)
        else:
            raise ValueError("user_id 또는 role_name 중 하나는 필수입니다")

        conditions.append(f"resource_type = ${len(params) + 1}")
        params.append(resource_type.value)

        conditions.append(f"resource_name = ${len(params) + 1}")
        params.append(resource_name)

        query = f"""
            DELETE FROM resource_permissions
            WHERE {" AND ".join(conditions)}
        """

        await self.db_conn.execute(query, *params)

        # 캐시 클리어
        if user_id:
            self.clear_cache(user_id)

        logger.info(
            "권한 회수 완료",
            user_id=user_id,
            role_name=role_name,
            resource_type=resource_type,
            resource_name=resource_name,
        )
