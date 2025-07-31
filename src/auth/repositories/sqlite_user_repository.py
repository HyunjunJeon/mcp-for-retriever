"""
SQLite 기반 사용자 Repository 구현

이 모듈은 SQLAlchemy를 사용하여 SQLite 데이터베이스에 사용자 정보를 
영구적으로 저장하는 Repository 구현체를 제공합니다.

특징:
    - 비동기 I/O 지원 (aiosqlite)
    - 트랜잭션 보장
    - 자동 타임스탬프 관리
    - 역할 정보 JSON 저장
    - 데이터 무결성 보장

작성일: 2024-01-30
"""

from datetime import datetime, UTC
from typing import Optional, List
import uuid
import json

from sqlalchemy import select, update, delete, func, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
import structlog

from ..models import User
from ..database import User as UserDB
from .user_repository import UserRepository


logger = structlog.get_logger(__name__)


class SQLiteUserRepository(UserRepository):
    """
    SQLite 데이터베이스 기반 사용자 Repository 구현체
    
    SQLAlchemy ORM을 사용하여 사용자 데이터를 SQLite 파일에 영구 저장합니다.
    비동기 작업을 지원하며, 트랜잭션 안전성을 보장합니다.
    
    특징:
        - 영구 저장소: 서버 재시작 후에도 데이터 유지
        - 트랜잭션 지원: 데이터 일관성 보장
        - 인덱싱: 이메일 기반 빠른 검색
        - JSON 필드: 유연한 역할 정보 저장
        
    사용 예:
        ```python
        async with get_db() as session:
            repo = SQLiteUserRepository(session)
            user = await repo.create({
                "email": "user@example.com",
                "password_hash": "hashed_password",
                "roles": ["user"]
            })
        ```
    """
    
    def __init__(self, session: AsyncSession):
        """
        SQLite Repository 초기화
        
        Args:
            session (AsyncSession): SQLAlchemy 비동기 세션
        """
        self.session = session
        
    async def create(self, user_data: dict) -> User:
        """
        새 사용자 생성
        
        Args:
            user_data (dict): 사용자 생성 정보
                - email (str): 이메일 주소 (고유해야 함)
                - password_hash (str): 해시된 비밀번호
                - username (Optional[str]): 사용자명
                - roles (list[str]): 사용자 역할 목록
                - is_active (bool): 활성화 상태 (기본값: True)
                - is_verified (bool): 이메일 인증 상태 (기본값: False)
                
        Returns:
            User: 생성된 사용자 모델
            
        Raises:
            ValueError: 이메일 중복이나 필수 필드 누락 시
        """
        try:
            # 새 사용자 DB 객체 생성
            db_user = UserDB(
                id=str(uuid.uuid4()),
                email=user_data["email"],
                username=user_data.get("username"),
                password_hash=user_data["password_hash"],
                is_active=user_data.get("is_active", True),
                is_verified=user_data.get("is_verified", False),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC)
            )
            
            # 세션에 추가하고 커밋
            self.session.add(db_user)
            await self.session.commit()
            await self.session.refresh(db_user)
            
            # 역할 정보 추가 (user_roles 테이블)
            roles = user_data.get("roles", ["user"])
            for role in roles:
                await self.session.execute(
                    text("INSERT INTO user_roles (user_id, role) VALUES (:user_id, :role)"),
                    {"user_id": db_user.id, "role": role}
                )
            await self.session.commit()
            
            # User 모델로 변환하여 반환
            return self._db_to_model(db_user, roles)
            
        except IntegrityError as e:
            await self.session.rollback()
            if "email" in str(e.orig):
                raise ValueError(f"이미 등록된 이메일입니다: {user_data['email']}")
            raise ValueError(f"데이터베이스 오류: {str(e)}")
            
        except Exception as e:
            await self.session.rollback()
            logger.error("사용자 생성 실패", error=str(e), email=user_data.get("email"))
            raise
    
    async def get_by_id(self, user_id: str) -> Optional[User]:
        """
        사용자 ID로 조회
        
        Args:
            user_id (str): 사용자 고유 식별자
            
        Returns:
            Optional[User]: 사용자 모델 또는 None (미존재시)
        """
        try:
            # 사용자 조회
            result = await self.session.execute(
                select(UserDB).where(UserDB.id == user_id)
            )
            db_user = result.scalar_one_or_none()
            
            if not db_user:
                return None
                
            # 역할 정보 조회
            roles_result = await self.session.execute(
                text("SELECT role FROM user_roles WHERE user_id = :user_id"),
                {"user_id": user_id}
            )
            roles = [row[0] for row in roles_result]
            
            return self._db_to_model(db_user, roles or ["user"])
            
        except Exception as e:
            logger.error("사용자 조회 실패", error=str(e), user_id=user_id)
            return None
    
    async def get_by_email(self, email: str) -> Optional[User]:
        """
        이메일로 사용자 조회
        
        Args:
            email (str): 이메일 주소
            
        Returns:
            Optional[User]: 사용자 모델 또는 None (미존재시)
        """
        try:
            # 이메일로 사용자 조회
            result = await self.session.execute(
                select(UserDB).where(UserDB.email == email)
            )
            db_user = result.scalar_one_or_none()
            
            if not db_user:
                return None
                
            # 역할 정보 조회
            roles_result = await self.session.execute(
                text("SELECT role FROM user_roles WHERE user_id = :user_id"),
                {"user_id": db_user.id}
            )
            roles = [row[0] for row in roles_result]
            
            return self._db_to_model(db_user, roles or ["user"])
            
        except Exception as e:
            logger.error("이메일로 사용자 조회 실패", error=str(e), email=email)
            return None
    
    async def update(self, user_id: str, update_data: dict) -> Optional[User]:
        """
        사용자 정보 수정
        
        Args:
            user_id (str): 사용자 ID
            update_data (dict): 수정할 필드와 값
                - password_hash: 새로운 해시된 비밀번호
                - is_active: 계정 활성화 상태
                - is_verified: 이메일 인증 상태
                - roles: 새로운 역할 목록
                
        Returns:
            Optional[User]: 수정된 사용자 모델 또는 None (미존재시)
        """
        try:
            # 사용자 존재 확인
            db_user = await self.session.get(UserDB, user_id)
            if not db_user:
                return None
            
            # 필드 업데이트
            if "password_hash" in update_data:
                db_user.password_hash = update_data["password_hash"]
            if "is_active" in update_data:
                db_user.is_active = update_data["is_active"]
            if "is_verified" in update_data:
                db_user.is_verified = update_data["is_verified"]
            if "username" in update_data:
                db_user.username = update_data["username"]
                
            db_user.updated_at = datetime.now(UTC)
            
            # 역할 업데이트
            if "roles" in update_data:
                # 기존 역할 삭제
                await self.session.execute(
                    text("DELETE FROM user_roles WHERE user_id = :user_id"),
                    {"user_id": user_id}
                )
                
                # 새 역할 추가
                for role in update_data["roles"]:
                    await self.session.execute(
                        text("INSERT INTO user_roles (user_id, role) VALUES (:user_id, :role)"),
                        {"user_id": user_id, "role": role}
                    )
            
            await self.session.commit()
            await self.session.refresh(db_user)
            
            # 최종 역할 정보 조회
            roles_result = await self.session.execute(
                text("SELECT role FROM user_roles WHERE user_id = :user_id"),
                {"user_id": user_id}
            )
            roles = [row[0] for row in roles_result]
            
            return self._db_to_model(db_user, roles or ["user"])
            
        except Exception as e:
            await self.session.rollback()
            logger.error("사용자 수정 실패", error=str(e), user_id=user_id)
            return None
    
    async def delete(self, user_id: str) -> bool:
        """
        사용자 삭제
        
        Args:
            user_id (str): 사용자 ID
            
        Returns:
            bool: 삭제 성공 여부
        """
        try:
            # 사용자 역할 먼저 삭제
            await self.session.execute(
                text("DELETE FROM user_roles WHERE user_id = :user_id"),
                {"user_id": user_id}
            )
            
            # 사용자 권한 삭제
            await self.session.execute(
                text("DELETE FROM user_permissions WHERE user_id = :user_id"),
                {"user_id": user_id}
            )
            
            # 사용자 삭제
            result = await self.session.execute(
                delete(UserDB).where(UserDB.id == user_id)
            )
            
            await self.session.commit()
            return result.rowcount > 0
            
        except Exception as e:
            await self.session.rollback()
            logger.error("사용자 삭제 실패", error=str(e), user_id=user_id)
            return False
    
    async def list_all(self, skip: int = 0, limit: int = 100) -> list[User]:
        """
        모든 사용자 목록 조회 (페이지네이션)
        
        Args:
            skip (int): 건너뛸 레코드 수
            limit (int): 최대 반환 레코드 수
            
        Returns:
            list[User]: 사용자 모델 리스트
        """
        try:
            # 사용자 목록 조회
            result = await self.session.execute(
                select(UserDB)
                .order_by(UserDB.created_at.desc())
                .offset(skip)
                .limit(limit)
            )
            db_users = result.scalars().all()
            
            users = []
            for db_user in db_users:
                # 각 사용자의 역할 조회
                roles_result = await self.session.execute(
                    "SELECT role FROM user_roles WHERE user_id = :user_id",
                    {"user_id": db_user.id}
                )
                roles = [row[0] for row in roles_result]
                users.append(self._db_to_model(db_user, roles or ["user"]))
            
            return users
            
        except Exception as e:
            logger.error("사용자 목록 조회 실패", error=str(e))
            return []
    
    async def search_by_email(self, email_pattern: str) -> list[User]:
        """
        이메일 패턴으로 사용자 검색
        
        Args:
            email_pattern (str): 검색할 이메일 패턴 (부분 일치)
            
        Returns:
            list[User]: 일치하는 사용자 목록
        """
        try:
            # LIKE 검색
            result = await self.session.execute(
                select(UserDB)
                .where(UserDB.email.like(f"%{email_pattern}%"))
                .order_by(UserDB.email)
            )
            db_users = result.scalars().all()
            
            users = []
            for db_user in db_users:
                # 각 사용자의 역할 조회
                roles_result = await self.session.execute(
                    "SELECT role FROM user_roles WHERE user_id = :user_id",
                    {"user_id": db_user.id}
                )
                roles = [row[0] for row in roles_result]
                users.append(self._db_to_model(db_user, roles or ["user"]))
            
            return users
            
        except Exception as e:
            logger.error("이메일 검색 실패", error=str(e), pattern=email_pattern)
            return []
    
    async def get_recent_users(self, days: int = 7, limit: int = 10) -> list[User]:
        """
        최근 가입한 사용자 조회
        
        Args:
            days (int): 최근 N일 이내
            limit (int): 최대 반환 수
            
        Returns:
            list[User]: 최근 가입 사용자 목록
        """
        try:
            # 날짜 계산
            cutoff_date = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            cutoff_date = cutoff_date.replace(day=cutoff_date.day - days)
            
            # 최근 사용자 조회
            result = await self.session.execute(
                select(UserDB)
                .where(UserDB.created_at >= cutoff_date)
                .order_by(UserDB.created_at.desc())
                .limit(limit)
            )
            db_users = result.scalars().all()
            
            users = []
            for db_user in db_users:
                # 각 사용자의 역할 조회
                roles_result = await self.session.execute(
                    "SELECT role FROM user_roles WHERE user_id = :user_id",
                    {"user_id": db_user.id}
                )
                roles = [row[0] for row in roles_result]
                users.append(self._db_to_model(db_user, roles or ["user"]))
            
            return users
            
        except Exception as e:
            logger.error("최근 사용자 조회 실패", error=str(e))
            return []
    
    async def get_user_count(self) -> int:
        """
        전체 사용자 수 조회
        
        Returns:
            int: 전체 사용자 수
        """
        try:
            result = await self.session.execute(
                select(func.count(UserDB.id))
            )
            return result.scalar() or 0
        except Exception as e:
            logger.error("사용자 수 조회 실패", error=str(e))
            return 0
    
    async def get_user_stats(self) -> dict:
        """
        사용자 통계 정보 조회
        
        Returns:
            dict: 통계 정보
                - total_users: 전체 사용자 수
                - active_users: 활성 사용자 수
                - verified_users: 인증된 사용자 수
                - users_by_role: 역할별 사용자 수
        """
        try:
            # 전체 사용자 수
            total_result = await self.session.execute(
                select(func.count(UserDB.id))
            )
            total_users = total_result.scalar() or 0
            
            # 활성 사용자 수
            active_result = await self.session.execute(
                select(func.count(UserDB.id)).where(UserDB.is_active == True)
            )
            active_users = active_result.scalar() or 0
            
            # 인증된 사용자 수
            verified_result = await self.session.execute(
                select(func.count(UserDB.id)).where(UserDB.is_verified == True)
            )
            verified_users = verified_result.scalar() or 0
            
            # 역할별 사용자 수
            roles_result = await self.session.execute(
                text("SELECT role, COUNT(DISTINCT user_id) FROM user_roles GROUP BY role")
            )
            users_by_role = {row[0]: row[1] for row in roles_result}
            
            return {
                "total_users": total_users,
                "active_users": active_users,
                "verified_users": verified_users,
                "users_by_role": users_by_role
            }
            
        except Exception as e:
            logger.error("사용자 통계 조회 실패", error=str(e))
            return {
                "total_users": 0,
                "active_users": 0,
                "verified_users": 0,
                "users_by_role": {}
            }
    
    def _db_to_model(self, db_user: UserDB, roles: List[str]) -> User:
        """
        데이터베이스 모델을 도메인 모델로 변환
        
        Args:
            db_user (UserDB): SQLAlchemy 모델
            roles (List[str]): 사용자 역할 목록
            
        Returns:
            User: 도메인 모델
        """
        return User(
            id=db_user.id,
            email=db_user.email,
            username=db_user.username,
            password_hash=db_user.password_hash,
            roles=roles,
            is_active=db_user.is_active,
            is_verified=db_user.is_verified,
            created_at=db_user.created_at,
            updated_at=db_user.updated_at
        )