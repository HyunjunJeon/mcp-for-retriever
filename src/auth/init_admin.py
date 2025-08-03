#!/usr/bin/env python
"""
초기 관리자 계정 자동 생성 모듈

Docker 컨테이너 시작 시 환경 변수로 설정된 관리자 계정을 자동으로 생성합니다.
기존 계정이 있으면 권한을 업데이트하고, 없으면 새로 생성합니다.

환경 변수:
    AUTO_CREATE_ADMIN: admin 계정 자동 생성 여부 (기본값: true)
    ADMIN_EMAIL: 관리자 이메일 (기본값: admin@example.com)
    ADMIN_PASSWORD: 관리자 비밀번호 (기본값: Admin123!)
    ADMIN_USERNAME: 관리자 이름 (기본값: System Admin)
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional
import structlog

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.auth.database import init_db, async_session_maker, User
from src.auth.services.auth_service_sqlite import SQLiteAuthService
from src.auth.services.jwt_service import JWTService
from sqlalchemy import select, text
import uuid

logger = structlog.get_logger(__name__)


class AdminInitializer:
    """관리자 계정 초기화 클래스"""

    def __init__(self):
        self.auto_create = self._get_bool_env("AUTO_CREATE_ADMIN", True)
        self.admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com")
        self.admin_password = os.getenv("ADMIN_PASSWORD", "Admin123!")
        self.admin_username = os.getenv("ADMIN_USERNAME", "System Admin")
        
        # JWT 서비스 초기화 (비밀번호 해싱용)
        jwt_secret = os.getenv("JWT_SECRET_KEY", "temp-key-for-init")
        self.auth_service = SQLiteAuthService(
            JWTService(secret_key=jwt_secret, algorithm="HS256", access_token_expire_minutes=30)
        )

    def _get_bool_env(self, key: str, default: bool) -> bool:
        """환경 변수를 boolean으로 변환"""
        value = os.getenv(key, str(default)).lower()
        return value in ("true", "1", "yes", "on")

    async def ensure_admin_account(self) -> bool:
        """
        관리자 계정 존재 확인 및 생성
        
        Returns:
            bool: 계정이 생성되거나 업데이트되었으면 True
        """
        if not self.auto_create:
            logger.info("AUTO_CREATE_ADMIN=false로 설정되어 관리자 계정 자동 생성을 건너뜁니다")
            return False

        logger.info(
            "관리자 계정 초기화 시작",
            email=self.admin_email,
            username=self.admin_username
        )

        async with async_session_maker() as session:
            try:
                # 기존 계정 확인
                stmt = select(User).where(User.email == self.admin_email)
                result = await session.execute(stmt)
                existing_user = result.scalar_one_or_none()

                if existing_user:
                    # 기존 계정이 있으면 admin 권한 확인/추가
                    return await self._ensure_admin_role(session, existing_user)
                else:
                    # 새 계정 생성
                    return await self._create_admin_account(session)

            except Exception as e:
                logger.error("관리자 계정 초기화 실패", error=str(e))
                await session.rollback()
                return False

    async def _create_admin_account(self, session, user_id: Optional[str] = None) -> bool:
        """새 관리자 계정 생성"""
        try:
            user_id = user_id or str(uuid.uuid4())
            password_hash = self.auth_service.hash_password(self.admin_password)

            # 사용자 생성
            new_user = User(
                id=user_id,
                email=self.admin_email,
                username=self.admin_username,
                password_hash=password_hash,
                is_verified=True,
                is_active=True,
            )

            session.add(new_user)
            await session.commit()

            # admin 역할 추가
            await session.execute(
                text("INSERT INTO user_roles (user_id, role) VALUES (:user_id, :role)"),
                {"user_id": user_id, "role": "admin"}
            )
            await session.commit()

            logger.info(
                "✅ 새 관리자 계정 생성 완료",
                user_id=user_id,
                email=self.admin_email,
                username=self.admin_username
            )
            return True

        except Exception as e:
            logger.error("관리자 계정 생성 실패", error=str(e))
            await session.rollback()
            return False

    async def _ensure_admin_role(self, session, user: User) -> bool:
        """기존 사용자에게 admin 역할 확인/추가"""
        try:
            # 현재 역할 확인
            result = await session.execute(
                text("SELECT role FROM user_roles WHERE user_id = :user_id"),
                {"user_id": user.id}
            )
            current_roles = {row[0] for row in result.fetchall()}

            if "admin" in current_roles:
                logger.info(
                    "관리자 계정이 이미 admin 권한을 가지고 있습니다",
                    email=self.admin_email,
                    current_roles=list(current_roles)
                )
                return False

            # admin 역할 추가
            await session.execute(
                text("INSERT INTO user_roles (user_id, role) VALUES (:user_id, :role)"),
                {"user_id": user.id, "role": "admin"}
            )
            await session.commit()

            logger.info(
                "✅ 기존 계정에 admin 권한 추가 완료",
                email=self.admin_email,
                user_id=user.id,
                previous_roles=list(current_roles)
            )
            return True

        except Exception as e:
            logger.error("admin 권한 추가 실패", error=str(e))
            await session.rollback()
            return False

    async def list_admin_accounts(self) -> list[dict]:
        """현재 admin 권한을 가진 모든 계정 조회"""
        async with async_session_maker() as session:
            try:
                result = await session.execute(
                    text("""
                        SELECT u.id, u.email, u.username, u.is_active, u.created_at
                        FROM users u 
                        JOIN user_roles ur ON u.id = ur.user_id 
                        WHERE ur.role = 'admin'
                        ORDER BY u.created_at
                    """)
                )
                
                admin_accounts = []
                for row in result.fetchall():
                    admin_accounts.append({
                        "id": row[0],
                        "email": row[1],
                        "username": row[2],
                        "is_active": row[3],
                        "created_at": row[4]
                    })
                
                return admin_accounts

            except Exception as e:
                logger.error("admin 계정 조회 실패", error=str(e))
                return []


async def init_admin_on_startup() -> bool:
    """
    서버 시작 시 호출되는 admin 초기화 함수
    
    Returns:
        bool: 초기화 성공 여부
    """
    try:
        # 데이터베이스 초기화 (테이블이 없는 경우에만)
        await init_db()
        
        # 관리자 계정 초기화
        initializer = AdminInitializer()
        result = await initializer.ensure_admin_account()
        
        # 현재 admin 계정들 출력
        admin_accounts = await initializer.list_admin_accounts()
        if admin_accounts:
            logger.info(
                "현재 admin 계정 목록",
                count=len(admin_accounts),
                accounts=[{"email": acc["email"], "username": acc["username"]} for acc in admin_accounts]
            )
        
        return result

    except Exception as e:
        logger.error("Admin 초기화 중 오류 발생", error=str(e))
        return False


async def main():
    """명령줄에서 직접 실행하는 경우"""
    success = await init_admin_on_startup()
    if success:
        print("✅ 관리자 계정 초기화가 완료되었습니다.")
    else:
        print("❌ 관리자 계정 초기화가 실패했습니다.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())