"""
인증 관련 요청 모델

Clean Code Architecture에 따라 요청/응답 모델을 명확히 분리합니다.
"""

from pydantic import BaseModel, EmailStr, Field


class RefreshTokenRequest(BaseModel):
    """토큰 갱신 요청 모델"""

    refresh_token: str = Field(
        ...,
        description="갱신을 위한 리프레시 토큰",
        example="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    )

    class Config:
        json_schema_extra = {
            "example": {"refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."}
        }


class LoginRequest(BaseModel):
    """로그인 요청 모델"""

    email: EmailStr = Field(..., description="사용자 이메일")
    password: str = Field(..., min_length=8, description="사용자 비밀번호")

    class Config:
        json_schema_extra = {
            "example": {"email": "user@example.com", "password": "SecurePassword123!"}
        }
