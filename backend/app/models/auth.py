"""
Authentication related data models
"""
from pydantic import BaseModel, EmailStr
from typing import Optional


class SignUpRequest(BaseModel):
    """用户注册请求"""
    email: EmailStr
    password: str
    username: Optional[str] = None


class SignInRequest(BaseModel):
    """用户登录请求"""
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """用户信息响应"""
    id: str
    email: str
    username: Optional[str] = None
    subscription_tier: str = "free"


class AuthResponse(BaseModel):
    """认证响应(包含 Token)"""
    user: UserResponse
    access_token: str
    refresh_token: str


class OAuthCallbackRequest(BaseModel):
    """OAuth 回调请求"""
    code: str
    state: Optional[str] = None


class OAuthURLResponse(BaseModel):
    """OAuth URL 响应"""
    url: str
    provider: str


class QuotaResponse(BaseModel):
    """用户配额响应"""
    monthly_video_limit: int
    monthly_videos_used: int
    total_storage_mb: int
    used_storage_mb: int
    videos_remaining: int
    storage_remaining_mb: int
