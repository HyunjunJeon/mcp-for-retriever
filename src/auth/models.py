"""
인증 관련 모델 정의

이 모듈은 사용자 인증, 권한 관리, 토큰 등과 관련된
Pydantic 모델들을 정의합니다.

주요 모델:
    - UserCreate: 사용자 생성 요청 모델
    - UserLogin: 로그인 요청 모델  
    - UserResponse: 사용자 정보 응답 모델
    - AuthTokens: JWT 토큰 응답 모델
    - Permission: 개별 권한 모델 (리소스 + 작업)
    - Role: 역할 모델 (권한 그룹)

작성일: 2024-01-30
"""

from typing import Optional, Any
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, EmailStr, field_validator, Field


class ResourceType(str, Enum):
    """
    보호되는 리소스 타입
    
    시스템에서 권한 관리가 필요한 리소스들을 정의합니다.
    """
    
    WEB_SEARCH = "web_search"
    VECTOR_DB = "vector_db"
    DATABASE = "database"


class ActionType(str, Enum):
    """
    리소스에 대한 작업 타입
    
    각 리소스에 대해 수행할 수 있는 작업들을 정의합니다.
    """
    
    READ = "read"
    WRITE = "write"
    DELETE = "delete"


class Permission(BaseModel):
    """
    개별 권한 모델
    
    하나의 권한은 리소스와 작업의 조합으로 이루어집니다.
    예: "web_search:read" = 웹 검색 읽기 권한
    
    Attributes:
        resource (ResourceType): 보호되는 리소스 타입
        action (ActionType): 허용되는 작업 타입
    """
    
    resource: ResourceType
    action: ActionType
    
    def __hash__(self) -> int:
        """
        권한을 해시 가능하게 만들어 Set에서 사용 가능
        
        중복 권한을 방지하기 위해 Set을 사용할 때 필요합니다.
        
        Returns:
            int: resource와 action의 조합으로 만든 해시값
        """
        return hash((self.resource, self.action))


class ResourcePermission(BaseModel):
    """
    세밀한 리소스 권한 모델
    
    특정 collection이나 table에 대한 세밀한 권한을 정의합니다.
    
    Attributes:
        resource_type: 리소스 타입 (VECTOR_DB, DATABASE)
        resource_name: 리소스 이름 (예: "users.documents", "public.users")
        actions: 허용된 작업 목록
        conditions: 추가 조건 (선택사항)
    """
    
    resource_type: ResourceType
    resource_name: str = Field(..., description="Collection or table name with optional schema/namespace")
    actions: list[ActionType]
    conditions: Optional[dict[str, Any]] = None
    
    @field_validator('resource_name')
    @classmethod
    def validate_resource_name(cls, v: str) -> str:
        """리소스 이름 검증"""
        if not v or len(v) > 255:
            raise ValueError("리소스 이름은 1-255자 사이여야 합니다")
        
        # SQL Injection 방지를 위한 기본 검증
        if any(char in v for char in [';', '--', '/*', '*/', '\0']):
            raise ValueError("리소스 이름에 허용되지 않는 문자가 포함되어 있습니다")
        
        return v


class Role(BaseModel):
    """
    역할 모델 (RBAC - Role-Based Access Control)
    
    여러 권한을 그룹화한 역할을 정의합니다.
    사용자는 하나 이상의 역할을 가질 수 있고, 
    각 역할의 모든 권한을 상속받습니다.
    
    Attributes:
        name (str): 역할 이름 (예: "admin", "user", "viewer")
        permissions (list[Permission]): 이 역할이 가진 권한 목록
        description (Optional[str]): 역할에 대한 설명 (선택사항)
    """
    
    name: str
    permissions: list[Permission]
    description: Optional[str] = None


class User(BaseModel):
    """
    사용자 정보 모델
    
    시스템에 저장된 사용자의 전체 정보를 나타냅니다.
    비밀번호는 해시된 형태로만 저장됩니다.
    
    Attributes:
        id (int): 사용자 고유 ID
        email (EmailStr): 이메일 주소 (로그인 ID로 사용)
        username (Optional[str]): 사용자명 (표시용)
        hashed_password (str): bcrypt로 해시된 비밀번호
        is_active (bool): 계정 활성화 여부
        is_verified (bool): 이메일 인증 여부
        roles (list[str]): 사용자가 가진 역할 목록
        created_at (datetime): 계정 생성 시각
        updated_at (datetime): 정보 수정 시각
    """
    
    id: int
    email: EmailStr
    username: Optional[str] = None
    hashed_password: str
    is_active: bool = True
    is_verified: bool = False
    roles: list[str] = Field(default_factory=lambda: ["user"])
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    """
    사용자 생성 요청 모델
    
    회원가입 시 클라이언트가 제공해야 하는 정보입니다.
    
    Attributes:
        email (EmailStr): 이메일 주소 (중복 불가)
        password (str): 평문 비밀번호 (최소 8자, 대소문자/숫자 포함)
        username (Optional[str]): 사용자명 (선택사항)
        roles (Optional[list[str]]): 초기 역할 (관리자만 설정 가능)
    """
    
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    roles: Optional[list[str]] = None
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        """
        비밀번호 복잡도 검증
        
        - 최소 8자 이상
        - 대문자 포함
        - 소문자 포함
        - 숫자 포함
        
        Args:
            v: 검증할 비밀번호
            
        Returns:
            str: 검증된 비밀번호
            
        Raises:
            ValueError: 비밀번호가 요구사항을 충족하지 않을 때
        """
        if not any(char.isupper() for char in v):
            raise ValueError('비밀번호는 대문자를 포함해야 합니다')
        if not any(char.islower() for char in v):
            raise ValueError('비밀번호는 소문자를 포함해야 합니다')
        if not any(char.isdigit() for char in v):
            raise ValueError('비밀번호는 숫자를 포함해야 합니다')
        return v


class UserLogin(BaseModel):
    """
    로그인 요청 모델
    
    사용자가 로그인할 때 제공해야 하는 정보입니다.
    
    Attributes:
        email (EmailStr): 이메일 주소
        password (str): 평문 비밀번호
    """
    
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """
    사용자 정보 응답 모델
    
    API 응답으로 반환되는 사용자 정보입니다.
    민감한 정보(비밀번호 등)는 제외됩니다.
    
    Attributes:
        id (int): 사용자 고유 ID
        email (EmailStr): 이메일 주소
        username (Optional[str]): 사용자명
        is_active (bool): 계정 활성화 여부
        is_verified (bool): 이메일 인증 여부
        roles (list[str]): 사용자가 가진 역할 목록
        created_at (datetime): 계정 생성 시각
    """
    
    id: int
    email: EmailStr
    username: Optional[str] = None
    is_active: bool
    is_verified: bool
    roles: list[str]
    created_at: datetime
    
    class Config:
        """Pydantic 설정"""
        from_attributes = True  # ORM 모델에서 직접 변환 가능


class UserUpdate(BaseModel):
    """
    사용자 정보 수정 요청 모델
    
    사용자가 자신의 정보를 수정할 때 사용합니다.
    모든 필드는 선택사항입니다.
    
    Attributes:
        username (Optional[str]): 새 사용자명
        password (Optional[str]): 새 비밀번호
    """
    
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    password: Optional[str] = Field(None, min_length=8, max_length=128)
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v: Optional[str]) -> Optional[str]:
        """비밀번호 복잡도 검증 (UserCreate와 동일)"""
        if v is None:
            return v
            
        if not any(char.isupper() for char in v):
            raise ValueError('비밀번호는 대문자를 포함해야 합니다')
        if not any(char.islower() for char in v):
            raise ValueError('비밀번호는 소문자를 포함해야 합니다')
        if not any(char.isdigit() for char in v):
            raise ValueError('비밀번호는 숫자를 포함해야 합니다')
        return v


class AuthTokens(BaseModel):
    """
    JWT 토큰 응답 모델
    
    로그인 성공 시 반환되는 토큰 정보입니다.
    
    Attributes:
        access_token (str): API 접근용 토큰 (단기 유효)
        refresh_token (str): 토큰 갱신용 토큰 (장기 유효)
        token_type (str): 토큰 타입 (항상 "bearer")
        expires_in (int): 액세스 토큰 만료 시간 (초)
    """
    
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenData(BaseModel):
    """
    JWT 토큰 페이로드 데이터 모델
    
    JWT 토큰의 페이로드에 포함된 사용자 정보를 나타냅니다.
    
    Attributes:
        user_id (str): 사용자 고유 ID
        email (Optional[str]): 사용자 이메일
        roles (list[str]): 사용자 역할 목록
        token_type (str): 토큰 타입 (access/refresh)
        exp (Optional[datetime]): 토큰 만료 시간
        iat (Optional[datetime]): 토큰 발급 시간
    """
    
    user_id: str
    email: Optional[str] = None
    roles: list[str] = Field(default_factory=list)
    token_type: str
    exp: Optional[datetime] = None
    iat: Optional[datetime] = None


class TokenRefresh(BaseModel):
    """
    토큰 갱신 요청 모델
    
    만료된 액세스 토큰을 갱신할 때 사용합니다.
    
    Attributes:
        refresh_token (str): 유효한 리프레시 토큰
    """
    
    refresh_token: str


class PasswordReset(BaseModel):
    """
    비밀번호 재설정 요청 모델
    
    비밀번호를 잊어버린 경우 재설정을 요청합니다.
    
    Attributes:
        email (EmailStr): 계정 이메일 주소
    """
    
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """
    비밀번호 재설정 확인 모델
    
    이메일로 받은 토큰으로 새 비밀번호를 설정합니다.
    
    Attributes:
        token (str): 이메일로 받은 재설정 토큰
        new_password (str): 새 비밀번호
    """
    
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)
    
    @field_validator('new_password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        """비밀번호 복잡도 검증 (UserCreate와 동일)"""
        if not any(char.isupper() for char in v):
            raise ValueError('비밀번호는 대문자를 포함해야 합니다')
        if not any(char.islower() for char in v):
            raise ValueError('비밀번호는 소문자를 포함해야 합니다')
        if not any(char.isdigit() for char in v):
            raise ValueError('비밀번호는 숫자를 포함해야 합니다')
        return v


__all__ = [
    # 열거형
    "ResourceType",
    "ActionType",
    
    # 권한 모델
    "Permission",
    "ResourcePermission",
    "Role",
    
    # 사용자 모델
    "User",
    "UserCreate",
    "UserLogin",
    "UserResponse",
    "UserUpdate",
    
    # 토큰 모델
    "AuthTokens",
    "TokenData",
    "TokenRefresh",
    
    # 비밀번호 재설정
    "PasswordReset",
    "PasswordResetConfirm",
]