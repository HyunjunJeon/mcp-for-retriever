"""
인증 및 권한 관리 모델 정의

이 모듈은 MCP 서버의 인증/인가 시스템에서 사용하는 모든 데이터 모델을 정의합니다.
Pydantic을 사용하여 타입 안전성과 자동 검증을 보장합니다.

주요 구성요소:
    - ResourceType: 보호되는 리소스 타입 열거형
    - ActionType: 리소스에 대한 작업 타입 열거형
    - Permission: 개별 권한을 나타내는 모델
    - Role: 권한의 집합인 역할 모델
    - User: 사용자 정보 모델
    - Token 관련 모델들: JWT 토큰 처리를 위한 모델들

작성일: 2024-01-30
"""

from datetime import datetime, UTC
from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, SecretStr, field_validator


class ResourceType(str, Enum):
    """
    보호되는 리소스 타입 열거형
    
    각 리트리버를 리소스로 정의하여 각각에 대한 접근 권한을 관리합니다.
    새로운 리트리버가 추가될 때마다 여기에 타입을 추가해야 합니다.
    """
    
    WEB_SEARCH = "web_search"   # 웹 검색 리트리버 (Tavily)
    VECTOR_DB = "vector_db"     # 벡터 DB 리트리버 (Qdrant)
    DATABASE = "database"       # 관계형 DB 리트리버 (PostgreSQL)


class ActionType(str, Enum):
    """
    리소스에 대한 작업 타입 열거형
    
    각 리소스에 대해 수행할 수 있는 작업을 정의합니다.
    CRUD 작업 중 CRD만 지원하며, Update는 Write로 통합됩니다.
    """
    
    READ = "read"       # 조회 권한 (검색, 읽기)
    WRITE = "write"     # 수정 권한 (생성, 업데이트)
    DELETE = "delete"   # 삭제 권한


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
    
    시스템에 등록된 사용자의 전체 정보를 담는 모델입니다.
    비밀번호는 해시화된 형태로만 저장됩니다.
    
    Attributes:
        id (str): 사용자 고유 식별자 (UUID)
        email (EmailStr): 사용자 이메일 (로그인 ID로 사용)
        hashed_password (str): 해시화된 비밀번호 (bcrypt)
        is_active (bool): 계정 활성화 상태 (기본값: True)
        roles (list[str]): 사용자가 가진 역할 이름 목록 (기본값: ["user"])
        created_at (datetime): 계정 생성 시각 (UTC)
        updated_at (Optional[datetime]): 마지막 수정 시각 (UTC)
    """
    
    id: str
    email: EmailStr
    hashed_password: str
    is_active: bool = True
    roles: list[str] = Field(default_factory=lambda: ["user"])
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: Optional[datetime] = None


class UserCreate(BaseModel):
    """
    사용자 생성 요청 모델
    
    새로운 사용자를 등록할 때 필요한 정보를 정의합니다.
    비밀번호는 SecretStr로 처리하여 로그에 노출되지 않도록 합니다.
    
    Attributes:
        email (EmailStr): 사용자 이메일 (유효한 이메일 형식이어야 함)
        password (SecretStr): 비밀번호 (최소 8자 이상)
        roles (list[str]): 부여할 역할 목록 (기본값: ["user"])
    """
    
    email: EmailStr
    password: SecretStr = Field(..., min_length=8)
    roles: list[str] = Field(default_factory=lambda: ["user"])
    
    @field_validator("password")
    @classmethod
    def validate_password(cls, v: SecretStr) -> SecretStr:
        """
        비밀번호 복잡도 검증
        
        보안을 위해 비밀번호가 최소 요구사항을 충족하는지 확인합니다.
        
        요구사항:
        - 최소 8자 이상
        - 대문자 포함
        - 소문자 포함
        - 숫자 포함
        
        Args:
            v (SecretStr): 검증할 비밀번호
            
        Returns:
            SecretStr: 검증을 통과한 비밀번호
            
        Raises:
            ValueError: 비밀번호가 요구사항을 충족하지 않을 때
        """
        password = v.get_secret_value()
        
        # 최소 길이 확인 (Field 검증과 중복이지만 명확성을 위해 유지)
        if len(password) < 8:
            raise ValueError("비밀번호는 최소 8자 이상이어야 합니다")
        
        # 대문자, 소문자, 숫자 포함 확인
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        
        if not (has_upper and has_lower and has_digit):
            raise ValueError(
                "비밀번호는 대문자, 소문자, 숫자를 포함해야 합니다"
            )
        
        return v


class UserLogin(BaseModel):
    """
    사용자 로그인 요청 모델
    
    로그인 시 필요한 인증 정보를 정의합니다.
    
    Attributes:
        email (EmailStr): 로그인할 사용자의 이메일
        password (SecretStr): 비밀번호
    """
    
    email: EmailStr
    password: SecretStr


class UserResponse(BaseModel):
    """
    사용자 정보 응답 모델
    
    API 응답으로 사용자 정보를 반환할 때 사용하는 모델입니다.
    보안상 비밀번호 해시는 포함하지 않습니다.
    
    Attributes:
        id (str): 사용자 고유 식별자
        email (EmailStr): 사용자 이메일
        is_active (bool): 계정 활성화 상태
        roles (list[str]): 사용자가 가진 역할 목록
        created_at (datetime): 계정 생성 시각
        updated_at (Optional[datetime]): 마지막 수정 시각
    """
    
    id: str
    email: EmailStr
    is_active: bool
    roles: list[str]
    created_at: datetime
    updated_at: Optional[datetime] = None


class TokenData(BaseModel):
    """
    JWT 토큰 페이로드 데이터 모델
    
    JWT 토큰의 페이로드에 포함되는 사용자 정보를 정의합니다.
    이 정보는 토큰에서 추출하거나 토큰을 생성할 때 사용됩니다.
    
    Attributes:
        user_id (str): 사용자 고유 식별자 (필수)
        email (Optional[EmailStr]): 사용자 이메일 (선택사항)
        roles (list[str]): 사용자 역할 목록 (기본값: 빈 리스트)
        token_type (str): 토큰 타입 ("access" 또는 "refresh", 기본값: "access")
        exp (Optional[datetime]): 토큰 만료 시각 (expiration)
        iat (Optional[datetime]): 토큰 발급 시각 (issued at)
    """
    
    user_id: str
    email: Optional[EmailStr] = None
    roles: list[str] = Field(default_factory=list)
    token_type: str = "access"
    exp: Optional[datetime] = None
    iat: Optional[datetime] = None


class AuthTokens(BaseModel):
    """
    인증 토큰 쌍 응답 모델
    
    로그인 성공 시 반환되는 액세스 토큰과 리프레시 토큰을 포함합니다.
    
    Attributes:
        access_token (str): API 요청에 사용하는 액세스 토큰 (짧은 수명)
        refresh_token (str): 액세스 토큰 갱신에 사용하는 리프레시 토큰 (긴 수명)
        token_type (str): 토큰 인증 방식 (고정값: "Bearer")
    """
    
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"


class TokenResponse(BaseModel):
    """
    단일 토큰 응답 모델
    
    토큰 갱신 시 또는 액세스 토큰만 필요한 경우 사용하는 모델입니다.
    OAuth2 표준을 따릅니다.
    
    Attributes:
        access_token (str): API 요청에 사용하는 액세스 토큰
        token_type (str): 토큰 인증 방식 (고정값: "Bearer")
    """
    
    access_token: str
    token_type: str = "Bearer"