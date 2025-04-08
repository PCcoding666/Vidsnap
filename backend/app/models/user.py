from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
import uuid

class UserBase(BaseModel):
    """用户基本信息"""
    email: EmailStr
    username: str

class UserCreate(UserBase):
    """创建用户时的信息"""
    password: str

class UserLogin(BaseModel):
    """用户登录信息"""
    email: EmailStr
    password: str

class UserInDB(UserBase):
    """存储在数据库(JSON文件)中的用户信息"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    hashed_password: str
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    subscription_plan: str = "free"  # 默认为免费计划
    usage: dict = Field(default_factory=lambda: {"videos_processed": 0, "last_reset": datetime.utcnow().isoformat()})

class User(UserBase):
    """API返回的用户信息"""
    id: str
    is_active: bool
    created_at: datetime
    subscription_plan: str
    usage: dict

class Token(BaseModel):
    """JWT令牌"""
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    """JWT令牌数据"""
    user_id: Optional[str] = None 