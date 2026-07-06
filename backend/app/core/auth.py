"""
FastAPI-Users 认证配置
替代 Supabase Auth，实现本地用户认证和 Google OAuth
"""
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, AsyncGenerator, Dict, Any

from fastapi import Depends, Request, Response
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID
from httpx_oauth.clients.google import GoogleOAuth2
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import (
    User, Profile, UserQuota, OAuthAccount,
    get_db_config, DatabaseConfig
)
from app.core.config import settings
from app.core.logging import logger


# ============================================
# 配置常量
# ============================================
# 统一使用 config.settings 的 JWT_SECRET（env 未设时为进程级随机值），不再内置公开常量默认值
JWT_SECRET = settings.JWT_SECRET
JWT_LIFETIME_SECONDS = 3600 * 24 * 7  # 7 天
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")


# ============================================
# Google OAuth 客户端
# ============================================
google_oauth_client = GoogleOAuth2(
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
) if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET else None


# ============================================
# 数据库适配器
# ============================================
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """获取异步数据库会话"""
    db = get_db_config()
    async with db.async_session_maker() as session:
        yield session


async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    """获取用户数据库适配器"""
    yield SQLAlchemyUserDatabase(session, User, OAuthAccount)


# ============================================
# 用户管理器
# ============================================
class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    """
    自定义用户管理器
    处理用户注册、登录后的钩子逻辑
    """
    
    reset_password_token_secret = JWT_SECRET
    verification_token_secret = JWT_SECRET
    
    async def on_after_register(
        self, 
        user: User, 
        request: Optional[Request] = None
    ):
        """用户注册后回调：创建 Profile 和 UserQuota"""
        logger.info(f"✅ 新用户注册: {user.email} (ID: {user.id})")
        
        try:
            # 创建用户资料
            profile = Profile(
                id=user.id,
                email=user.email,
                username=None,
                subscription_tier='free',
                language='zh-CN',
                theme='system',
            )
            self.user_db.session.add(profile)
            
            # 创建用户配额
            quota = UserQuota(
                user_id=user.id,
                monthly_video_limit=10,
                monthly_videos_used=0,
                total_storage_mb=1000,
                used_storage_mb=0,
                reset_date=datetime.now(timezone.utc) + timedelta(days=30),
                max_channel_subscriptions=3,
                max_video_duration_seconds=600,
            )
            self.user_db.session.add(quota)
            
            await self.user_db.session.commit()
            logger.info(f"✅ 创建用户资料和配额: {user.email}")
            
        except Exception as e:
            logger.error(f"❌ 创建用户资料失败: {e}")
            await self.user_db.session.rollback()
            raise
    
    async def on_after_login(
        self,
        user: User,
        request: Optional[Request] = None,
        response: Optional[Response] = None,
    ):
        """用户登录后回调"""
        logger.info(f"✅ 用户登录: {user.email}")
    
    async def on_after_forgot_password(
        self, 
        user: User, 
        token: str, 
        request: Optional[Request] = None
    ):
        """忘记密码回调：发送重置邮件"""
        logger.info(f"📧 密码重置请求: {user.email}")
        # TODO: 实现邮件发送
    
    async def on_after_request_verify(
        self, 
        user: User, 
        token: str, 
        request: Optional[Request] = None
    ):
        """请求验证邮件回调"""
        logger.info(f"📧 邮箱验证请求: {user.email}")
        # TODO: 实现邮件发送
    
    async def on_after_verify(
        self, 
        user: User, 
        request: Optional[Request] = None
    ):
        """用户验证完成回调"""
        logger.info(f"✅ 邮箱已验证: {user.email}")


async def get_user_manager(user_db=Depends(get_user_db)):
    """获取用户管理器"""
    yield UserManager(user_db)


# ============================================
# JWT 认证策略
# ============================================
bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")


def get_jwt_strategy() -> JWTStrategy:
    """获取 JWT 策略"""
    return JWTStrategy(
        secret=JWT_SECRET,
        lifetime_seconds=JWT_LIFETIME_SECONDS,
    )


# ============================================
# 认证后端
# ============================================
auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)


# ============================================
# FastAPI-Users 实例
# ============================================
fastapi_users = FastAPIUsers[User, uuid.UUID](
    get_user_manager,
    [auth_backend],
)

# 常用依赖
current_active_user = fastapi_users.current_user(active=True)
current_superuser = fastapi_users.current_user(active=True, superuser=True)
optional_current_user = fastapi_users.current_user(active=True, optional=True)


# ============================================
# 辅助函数
# ============================================
async def get_current_user_dict(
    user: User = Depends(current_active_user)
) -> Dict[str, Any]:
    """
    获取当前用户字典（兼容原有 API）
    
    返回格式与原 Supabase 兼容：
    {"id": "uuid", "email": "xxx@example.com"}
    """
    return {
        "id": str(user.id),
        "email": user.email,
        "is_verified": user.is_verified,
        "is_superuser": user.is_superuser,
    }


def get_auth_router():
    """
    获取认证路由
    
    包含：
    - /auth/jwt/login - JWT 登录
    - /auth/jwt/logout - JWT 登出
    - /auth/register - 注册
    - /auth/forgot-password - 忘记密码
    - /auth/reset-password - 重置密码
    - /auth/verify - 邮箱验证
    - /auth/google/authorize - Google OAuth 授权
    - /auth/google/callback - Google OAuth 回调
    """
    from fastapi import APIRouter
    
    router = APIRouter()
    
    # JWT 认证路由
    router.include_router(
        fastapi_users.get_auth_router(auth_backend),
        prefix="/jwt",
        tags=["auth"],
    )
    
    # 注册路由
    router.include_router(
        fastapi_users.get_register_router(UserRead, UserCreate),
        tags=["auth"],
    )
    
    # 密码重置路由
    router.include_router(
        fastapi_users.get_reset_password_router(),
        tags=["auth"],
    )
    
    # 邮箱验证路由
    router.include_router(
        fastapi_users.get_verify_router(UserRead),
        tags=["auth"],
    )
    
    # Google OAuth 路由
    if google_oauth_client:
        router.include_router(
            fastapi_users.get_oauth_router(
                google_oauth_client,
                auth_backend,
                JWT_SECRET,
                associate_by_email=True,
                is_verified_by_default=True,  # Google 用户默认已验证
            ),
            prefix="/google",
            tags=["auth"],
        )
    
    return router


# ============================================
# Pydantic Schemas
# ============================================
from pydantic import BaseModel, EmailStr
from typing import Optional
import uuid


class UserRead(BaseModel):
    """用户读取 Schema"""
    id: uuid.UUID
    email: EmailStr
    is_active: bool = True
    is_superuser: bool = False
    is_verified: bool = False
    
    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    """用户创建 Schema"""
    email: EmailStr
    password: str
    
    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    """用户更新 Schema"""
    password: Optional[str] = None
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    is_verified: Optional[bool] = None
    
    class Config:
        from_attributes = True


# ============================================
# 手动 Token 验证（兼容原有代码）
# ============================================
from jose import jwt, JWTError


def verify_jwt_token(token: str) -> Optional[Dict[str, Any]]:
    """
    手动验证 JWT Token（用于兼容原有代码）
    
    Args:
        token: JWT Token 字符串
        
    Returns:
        解码后的用户信息字典，验证失败返回 None
    """
    try:
        # 注意: jose.jwt.decode 的 audience 参数需要是字符串
        # 但 FastAPI-Users 生成的 token 的 aud 是数组，所以我们不验证 audience
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},  # 跳过 audience 验证
        )
        
        # 手动验证 audience
        aud = payload.get("aud", [])
        if isinstance(aud, list):
            if "fastapi-users:auth" not in aud:
                logger.warning(f"Invalid audience: {aud}")
                return None
        elif aud != "fastapi-users:auth":
            logger.warning(f"Invalid audience: {aud}")
            return None
            
        user_id = payload.get("sub")
        if user_id is None:
            return None
        return {
            "id": user_id,
            "email": payload.get("email"),
            "aud": payload.get("aud"),
        }
    except JWTError as e:
        logger.warning(f"JWT 验证失败: {e}")
        return None

