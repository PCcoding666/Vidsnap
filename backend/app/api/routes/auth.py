"""
Authentication routes - 用户注册、登录、Token 验证
使用 FastAPI-Users 本地认证系统
"""
import logging
from typing import Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import RedirectResponse

from app.models.auth import (
    SignUpRequest, 
    SignInRequest, 
    AuthResponse, 
    UserResponse,
    OAuthURLResponse,
    OAuthCallbackRequest
)
from app.core.auth import (
    fastapi_users, 
    auth_backend, 
    get_auth_router,
    verify_jwt_token,
    get_user_manager,
    get_jwt_strategy,
    google_oauth_client,
    JWT_SECRET,
    UserRead,
    UserCreate,
)
from app.services.database_service import database_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["认证"])
security = HTTPBearer()


# ============================================
# 包含 FastAPI-Users 路由
# ============================================
router.include_router(get_auth_router())


# ============================================
# 兼容旧 API 的路由
# ============================================

@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def sign_up(request: SignUpRequest):
    """
    用户注册
    
    - **email**: 用户邮箱
    - **password**: 密码(最少 6 位字符)
    - **username**: 用户名(可选)
    """
    # 密码强度验证
    if len(request.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码长度至少为 6 位字符"
        )
    
    try:
        from app.models.database import User, Profile, UserQuota, get_db_config
        from passlib.hash import bcrypt
        from sqlalchemy import select
        import uuid
        from datetime import datetime, timezone, timedelta
        
        db_config = get_db_config()
        async with db_config.async_session_maker() as session:
            # 检查邮箱是否已存在
            result = await session.execute(
                select(User).where(User.email == request.email)
            )
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="该邮箱已被注册"
                )
            
            # 创建用户
            user = User(
                id=uuid.uuid4(),
                email=request.email,
                hashed_password=bcrypt.hash(request.password),
                is_active=True,
                is_superuser=False,
                is_verified=False,
            )
            session.add(user)
            await session.flush()
            
            # 创建用户资料
            profile = Profile(
                id=user.id,
                email=request.email,
                username=request.username,
                subscription_tier='free',
            )
            session.add(profile)
            
            # 创建用户配额
            quota = UserQuota(
                user_id=user.id,
                monthly_video_limit=10,
                monthly_videos_used=0,
                total_storage_mb=1000,
                used_storage_mb=0,
                reset_date=datetime.now(timezone.utc) + timedelta(days=30),
            )
            session.add(quota)
            
            await session.commit()
        
        # 生成 JWT Token
        strategy = get_jwt_strategy()
        token = await strategy.write_token(user)
        
        return AuthResponse(
            user=UserResponse(
                id=str(user.id),
                email=user.email,
                username=request.username,
                subscription_tier="free"
            ),
            access_token=token,
            refresh_token=""
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"注册失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"注册失败: {str(e)}"
        )


@router.post("/signin", response_model=AuthResponse)
async def sign_in(request: SignInRequest):
    """
    用户登录
    
    - **email**: 用户邮箱
    - **password**: 密码
    """
    try:
        from app.models.database import User, get_db_config
        from passlib.hash import bcrypt
        from sqlalchemy import select
        
        db_config = get_db_config()
        async with db_config.async_session_maker() as session:
            # 查找用户
            result = await session.execute(
                select(User).where(User.email == request.email)
            )
            user = result.scalar_one_or_none()
            
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="邮箱或密码错误",
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            # 验证密码
            if not bcrypt.verify(request.password, user.hashed_password):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="邮箱或密码错误",
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="账户已被禁用",
                    headers={"WWW-Authenticate": "Bearer"}
                )
        
        # 生成 JWT Token
        strategy = get_jwt_strategy()
        token = await strategy.write_token(user)
        
        # 获取用户资料
        profile = await database_service.get_user_profile(str(user.id))
        subscription_tier = profile.get("subscription_tier", "free") if profile else "free"
        
        return AuthResponse(
            user=UserResponse(
                id=str(user.id),
                email=user.email,
                username=profile.get("username") if profile else None,
                subscription_tier=subscription_tier
            ),
            access_token=token,
            refresh_token=""
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"登录失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
            headers={"WWW-Authenticate": "Bearer"}
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    获取当前用户信息
    
    需要在 Header 中提供 Authorization: Bearer {token}
    """
    token = credentials.credentials
    user_data = verify_jwt_token(token)
    
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # 获取完整用户资料
    profile = await database_service.get_user_profile(user_data["id"])
    if not profile:
        # 如果 profile 不存在，返回基本信息
        return UserResponse(
            id=user_data["id"],
            email=user_data.get("email", ""),
            username=None,
            subscription_tier="free"
        )
    
    return UserResponse(
        id=profile["id"],
        email=profile["email"],
        username=profile.get("username"),
        subscription_tier=profile.get("subscription_tier", "free")
    )


@router.get("/oauth/google", response_model=OAuthURLResponse)
async def get_google_oauth_url(redirect_url: str):
    """
    获取 Google OAuth 登录 URL
    
    - **redirect_url**: OAuth 回调地址(前端处理回调的页面 URL)
    
    返回一个 Google OAuth 登录链接,前端应将用户重定向到该 URL
    """
    if not google_oauth_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth 未配置"
        )
    
    try:
        # 使用 httpx-oauth 生成授权 URL
        authorization_url = await google_oauth_client.get_authorization_url(
            redirect_uri=redirect_url,
            scope=["openid", "email", "profile"],
        )
        return OAuthURLResponse(url=authorization_url, provider="google")
    except Exception as e:
        logger.error(f"Google OAuth 初始化失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OAuth 初始化失败: {str(e)}"
        )


@router.post("/oauth/callback", response_model=AuthResponse)
async def oauth_callback(
    request: OAuthCallbackRequest, 
    user_manager=Depends(get_user_manager)
):
    """
    处理 OAuth 回调授权码
    
    - **code**: OAuth 授权码(从回调 URL 参数获取)
    - **redirect_uri**: 回调 URI（必须与获取授权码时使用的一致）
    
    返回用户信息和访问令牌
    """
    if not google_oauth_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth 未配置"
        )
    
    try:
        # 使用授权码获取 access token
        redirect_uri = getattr(request, 'redirect_uri', None) or "http://localhost:8080/auth/callback"
        
        oauth2_token = await google_oauth_client.get_access_token(
            code=request.code,
            redirect_uri=redirect_uri,
        )
        
        # 获取用户信息
        async with google_oauth_client.get_httpx_client() as client:
            response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {oauth2_token['access_token']}"},
            )
            google_user = response.json()
        
        email = google_user.get("email")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无法获取 Google 用户邮箱"
            )
        
        # 查找或创建用户
        from app.models.database import User, OAuthAccount, get_db_config
        from sqlalchemy import select
        
        db_config = get_db_config()
        async with db_config.async_session_maker() as session:
            # 先通过 OAuth account 查找
            result = await session.execute(
                select(User).join(OAuthAccount).where(
                    OAuthAccount.oauth_name == "google",
                    OAuthAccount.account_id == google_user.get("id")
                )
            )
            user = result.scalar_one_or_none()
            
            if not user:
                # 通过邮箱查找
                result = await session.execute(
                    select(User).where(User.email == email)
                )
                user = result.scalar_one_or_none()
                
                if user:
                    # 关联 OAuth 账户
                    oauth_account = OAuthAccount(
                        oauth_name="google",
                        account_id=google_user.get("id"),
                        account_email=email,
                        access_token=oauth2_token['access_token'],
                        user_id=user.id,
                    )
                    session.add(oauth_account)
                    await session.commit()
                else:
                    # 创建新用户 - 直接使用 SQLAlchemy 而不是 user_manager
                    import uuid
                    from passlib.hash import bcrypt
                    
                    new_user = User(
                        id=uuid.uuid4(),
                        email=email,
                        hashed_password=bcrypt.hash(uuid.uuid4().hex),  # 随机密码
                        is_active=True,
                        is_superuser=False,
                        is_verified=True,  # Google 用户默认已验证
                    )
                    session.add(new_user)
                    await session.flush()
                    
                    # 创建 OAuth 账户关联
                    oauth_account = OAuthAccount(
                        oauth_name="google",
                        account_id=google_user.get("id"),
                        account_email=email,
                        access_token=oauth2_token['access_token'],
                        user_id=new_user.id,
                    )
                    session.add(oauth_account)
                    
                    # 创建用户资料
                    from app.models.database import Profile, UserQuota
                    from datetime import datetime, timezone, timedelta
                    
                    profile = Profile(
                        id=new_user.id,
                        email=email,
                        username=google_user.get("name"),
                        full_name=google_user.get("name"),
                        avatar_url=google_user.get("picture"),
                        subscription_tier='free',
                    )
                    session.add(profile)
                    
                    # 创建用户配额
                    quota = UserQuota(
                        user_id=new_user.id,
                        monthly_video_limit=10,
                        monthly_videos_used=0,
                        total_storage_mb=1000,
                        used_storage_mb=0,
                        reset_date=datetime.now(timezone.utc) + timedelta(days=30),
                    )
                    session.add(quota)
                    
                    await session.commit()
                    user = new_user
        
        # 生成 JWT Token
        strategy = get_jwt_strategy()
        token = await strategy.write_token(user)
        
        # 获取用户资料
        profile = await database_service.get_user_profile(str(user.id))
        
        return AuthResponse(
            user=UserResponse(
                id=str(user.id),
                email=user.email,
                username=google_user.get("name"),
                subscription_tier=profile.get("subscription_tier", "free") if profile else "free"
            ),
            access_token=token,
            refresh_token=""
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth 回调处理失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"OAuth 认证失败: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"}
        )
