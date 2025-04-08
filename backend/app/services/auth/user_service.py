from typing import Optional, List
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import EmailStr

from app.core.config import settings
from app.core.security import verify_password, get_password_hash, create_access_token
from app.models.user import UserCreate, UserInDB, User, TokenData
from app.services.storage.json_storage import JSONStorage

# 创建OAuth2密码认证方案
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")

# 创建用户存储服务
user_storage = JSONStorage[UserInDB](settings.USERS_DATA_FILE, UserInDB)

def get_user_by_email(email: EmailStr) -> Optional[UserInDB]:
    """根据邮箱获取用户"""
    users = user_storage.get_by_field("email", email)
    return users[0] if users else None

def get_user_by_id(user_id: str) -> Optional[UserInDB]:
    """根据ID获取用户"""
    return user_storage.get_by_id(user_id)

def create_user(user_create: UserCreate) -> User:
    """创建新用户"""
    # 检查邮箱是否已存在
    if get_user_by_email(user_create.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该邮箱已被注册"
        )
    
    # 创建新用户
    hashed_password = get_password_hash(user_create.password)
    user_in_db = UserInDB(
        email=user_create.email,
        username=user_create.username,
        hashed_password=hashed_password
    )
    
    # 保存用户
    created_user = user_storage.create(user_in_db)
    
    # 返回用户信息（不包含密码）
    return User(
        id=created_user.id,
        email=created_user.email,
        username=created_user.username,
        is_active=created_user.is_active,
        created_at=created_user.created_at,
        subscription_plan=created_user.subscription_plan,
        usage=created_user.usage
    )

def authenticate_user(email: EmailStr, password: str) -> Optional[UserInDB]:
    """验证用户"""
    user = get_user_by_email(email)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user

def get_current_user(token: str = Depends(oauth2_scheme)) -> UserInDB:
    """获取当前用户（依赖项）"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的认证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # 解码JWT令牌
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        token_data = TokenData(user_id=user_id)
    except JWTError:
        raise credentials_exception
    
    # 获取用户信息
    user = get_user_by_id(token_data.user_id)
    if user is None:
        raise credentials_exception
    
    # 检查用户是否激活
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户已被禁用"
        )
    
    return user

def update_user_usage(user_id: str) -> bool:
    """更新用户使用情况"""
    user = get_user_by_id(user_id)
    if not user:
        return False
    
    # 检查是否需要重置用户使用情况
    last_reset = datetime.fromisoformat(user.usage.get('last_reset'))
    current_time = datetime.utcnow()
    
    # 如果超过一个月，重置使用情况
    if current_time - last_reset > timedelta(days=30):
        user.usage = {
            "videos_processed": 1,  # 当前这次也算一次
            "last_reset": current_time.isoformat()
        }
    else:
        # 增加处理视频的次数
        user.usage["videos_processed"] += 1
    
    # 更新用户
    user_storage.update(user_id, user)
    return True

def check_user_quota(user: UserInDB) -> bool:
    """检查用户配额"""
    # 获取用户的订阅计划
    plan = user.subscription_plan
    
    # 获取计划的视频处理配额
    plan_quota = settings.SUBSCRIPTION_PLANS.get(plan, {}).get("videos_per_month", 0)
    
    # 获取用户当前使用情况
    videos_processed = user.usage.get("videos_processed", 0)
    
    # 检查是否超过配额
    return videos_processed < plan_quota 