from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from typing import Any

from app.core.config import settings
from app.core.security import create_access_token
from app.models.user import UserCreate, User, Token
from app.services.auth.user_service import create_user, authenticate_user, get_current_user

router = APIRouter()

@router.post("/register", response_model=User)
def register(*, user_in: UserCreate) -> Any:
    """
    用户注册
    """
    user = create_user(user_in)
    return user

@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()) -> Any:
    """
    用户登录，获取访问令牌
    """
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 生成访问令牌
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(user.id, expires_delta=access_token_expires)
    
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.get("/me", response_model=User)
def get_me(current_user = Depends(get_current_user)) -> Any:
    """
    获取当前用户信息
    """
    # 转换为User模型（排除密码和其他敏感信息）
    return User(
        id=current_user.id,
        email=current_user.email,
        username=current_user.username,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
        subscription_plan=current_user.subscription_plan,
        usage=current_user.usage
    ) 