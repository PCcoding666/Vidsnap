"""
API dependencies and middleware.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging
from typing import Dict, Any

from ..core.logging import logger
from ..services.supabase_service import supabase_service

# 安全方案
security = HTTPBearer()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """
    验证 JWT Token 并返回当前用户信息
    
    Args:
        credentials: HTTP Authorization 凭证
        
    Returns:
        用户信息 {"id": "...", "email": "..."}
        
    Raises:
        HTTPException: Token 无效或过期
    """
    if not supabase_service.is_available():
        # 如果 Supabase 不可用,跳过认证(降级模式)
        logger.warning("⚠️ Supabase 不可用,跳过认证")
        return {"id": "anonymous", "email": "anonymous@example.com"}
    
    token = credentials.credentials
    user = supabase_service.verify_token(token)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    logger.debug(f"✅ 用户认证成功: {user['email']}")
    return user


async def check_quota(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """
    检查用户配额是否充足
    
    Args:
        current_user: 当前用户信息
        
    Returns:
        用户信息(配额充足时)
        
    Raises:
        HTTPException: 配额已达上限
    """
    if not supabase_service.is_available():
        return current_user  # 服务不可用时不限制
    
    user_id = current_user.get("id")
    if user_id == "anonymous" or not user_id:
        return current_user  # 匿名用户或无效 ID 不限制
    
    quota_ok = supabase_service.check_user_quota(str(user_id))
    
    if not quota_ok:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="已达到本月视频处理上限或存储空间已满,请升级订阅或等待下月重置"
        )
    
    return current_user


# 保留旧的 verify_token 函数以保持向后兼容
async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Verify authentication token (deprecated, use get_current_user instead).
    
    Args:
        credentials: HTTP authorization credentials
        
    Returns:
        Verified token
    """
    token = credentials.credentials
    logger.debug(f"验证token: {token}")
    
    # 示例验证逻辑
    if token == "example-token":
        return token
    else:
        # 在实际应用中，您会验证JWT或其他类型的令牌
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )