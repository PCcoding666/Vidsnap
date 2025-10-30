"""
Authentication routes - 用户注册、登录、Token 验证
"""
import logging
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.models.auth import (
    SignUpRequest, 
    SignInRequest, 
    AuthResponse, 
    UserResponse,
    OAuthURLResponse,
    OAuthCallbackRequest
)
from app.services.supabase_service import supabase_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["认证"])
security = HTTPBearer()


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def sign_up(request: SignUpRequest):
    """
    用户注册
    
    - **email**: 用户邮箱
    - **password**: 密码(最少 6 位字符)
    - **username**: 用户名(可选)
    """
    if not supabase_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="认证服务暂时不可用"
        )
    
    # 密码强度验证
    if len(request.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码长度至少为 6 位字符"
        )
    
    try:
        result = supabase_service.sign_up_user(
            email=request.email,
            password=request.password,
            username=request.username
        )
        
        return AuthResponse(
            user=UserResponse(**result["user"]),
            access_token=result["access_token"],
            refresh_token=result["refresh_token"]
        )
    except Exception as e:
        error_msg = str(e)
        if "已被注册" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="该邮箱已被注册"
            )
        logger.error(f"注册失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="注册失败,请稍后重试"
        )


@router.post("/signin", response_model=AuthResponse)
async def sign_in(request: SignInRequest):
    """
    用户登录
    
    - **email**: 用户邮箱
    - **password**: 密码
    """
    if not supabase_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="认证服务暂时不可用"
        )
    
    try:
        result = supabase_service.sign_in_user(
            email=request.email,
            password=request.password
        )
        
        return AuthResponse(
            user=UserResponse(**result["user"]),
            access_token=result["access_token"],
            refresh_token=result["refresh_token"]
        )
    except Exception as e:
        logger.error(f"登录失败: {e}")
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
    if not supabase_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="认证服务暂时不可用"
        )
    
    token = credentials.credentials
    user = supabase_service.verify_token(token)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # 获取完整用户资料
    profile = supabase_service.get_user_profile(user["id"])
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户资料不存在"
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
    if not supabase_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="认证服务暂时不可用"
        )
    
    try:
        oauth_url = supabase_service.get_google_oauth_url(redirect_url)
        return OAuthURLResponse(url=oauth_url, provider="google")
    except Exception as e:
        logger.error(f"Google OAuth 初始化失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OAuth 初始化失败: {str(e)}"
        )


@router.post("/oauth/callback", response_model=AuthResponse)
async def oauth_callback(request: OAuthCallbackRequest):
    """
    处理 OAuth 回调授权码
    
    - **code**: OAuth 授权码(从回调 URL 参数获取)
    - **state**: OAuth state 参数(可选,用于 CSRF 保护)
    
    返回用户信息和访问令牌
    """
    if not supabase_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="认证服务暂时不可用"
        )
    
    try:
        result = supabase_service.exchange_oauth_code(request.code)
        
        return AuthResponse(
            user=UserResponse(**result["user"]),
            access_token=result["access_token"],
            refresh_token=result["refresh_token"]
        )
    except Exception as e:
        logger.error(f"OAuth 回调处理失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"OAuth 认证失败: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"}
        )
