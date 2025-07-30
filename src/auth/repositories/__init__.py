"""인증 레포지토리 모듈"""

from .user_repository import UserRepository, InMemoryUserRepository

__all__ = [
    "UserRepository",
    "InMemoryUserRepository",
]