#!/usr/bin/env python
"""
Auth 데이터베이스 초기화 스크립트

SQLite 데이터베이스를 초기화하고 기본 관리자 계정을 생성합니다.
"""

import asyncio
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.auth.database import init_db, async_session_maker, User
from src.auth.services.auth_service_sqlite import SQLiteAuthService
from src.auth.services.jwt_service import JWTService
import uuid
import structlog

logger = structlog.get_logger(__name__)


async def create_default_users():
    """기본 사용자 생성"""
    # JWT 서비스 초기화 (실제로는 사용하지 않지만 AuthService 초기화에 필요)
    jwt_service = JWTService(
        secret_key="temp-key-for-init",
        algorithm="HS256",
        access_token_expire_minutes=30,
    )
    auth_service = SQLiteAuthService(jwt_service)

    default_users = [
        {
            "email": "admin@example.com",
            "password": "Admin123!",
            "username": "Default Admin",
            "roles": ["admin"],
        },
        {
            "email": "super@admin.com",
            "password": "SuperAdmin123!",
            "username": "Super Admin",
            "roles": ["admin", "super_admin"],
        },
    ]

    async with async_session_maker() as session:
        for user_data in default_users:
            try:
                # 사용자가 이미 존재하는지 확인
                from sqlalchemy import select

                stmt = select(User).where(User.email == user_data["email"])
                result = await session.execute(stmt)
                existing_user = result.scalar_one_or_none()

                if existing_user:
                    logger.info(f"사용자 이미 존재: {user_data['email']}")
                    continue

                # 새 사용자 생성
                user_id = str(uuid.uuid4())
                hashed_password = auth_service.hash_password(user_data["password"])

                new_user = User(
                    id=user_id,
                    email=user_data["email"],
                    username=user_data["username"],
                    password_hash=hashed_password,
                    is_verified=True,
                    is_active=True,
                )

                session.add(new_user)
                await session.commit()

                # 역할 추가 (user_roles 테이블에 직접 삽입)
                from sqlalchemy import text

                for role in user_data["roles"]:
                    await session.execute(
                        text(
                            "INSERT INTO user_roles (user_id, role) VALUES (:user_id, :role)"
                        ),
                        {"user_id": user_id, "role": role},
                    )
                await session.commit()

                logger.info(
                    f"✅ 사용자 생성 완료: {user_data['email']} (역할: {user_data['roles']})"
                )

            except Exception as e:
                logger.error(f"사용자 생성 실패 {user_data['email']}: {e}")
                await session.rollback()


async def main():
    """메인 실행 함수"""
    logger.info("🚀 Auth 데이터베이스 초기화 시작")

    # 1. 데이터베이스 테이블 생성
    logger.info("📊 데이터베이스 테이블 생성 중...")
    await init_db()
    logger.info("✅ 테이블 생성 완료")

    # 2. 기본 사용자 생성
    logger.info("👤 기본 사용자 생성 중...")
    await create_default_users()

    logger.info("🎉 Auth 데이터베이스 초기화 완료!")


if __name__ == "__main__":
    asyncio.run(main())
