"""
API dependencies and middleware.
本地 PostgreSQL 认证模式
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging
from typing import Dict, Any, Optional

from ..core.logging import logger
from ..core.config import settings

# 安全方案
security = HTTPBearer()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """
    验证 JWT Token 并返回当前用户信息
    使用本地 FastAPI-Users JWT 认证
    
    Args:
        credentials: HTTP Authorization 凭证
        
    Returns:
        用户信息 {"id": "...", "email": "..."}
        
    Raises:
        HTTPException: Token 无效或过期
    """
    token = credentials.credentials
    
    # 使用本地 FastAPI-Users JWT 认证
    from ..core.auth import verify_jwt_token
    user = verify_jwt_token(token)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    logger.debug(f"✅ 用户认证成功: {user.get('email')}")
    return user


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> Optional[Dict[str, Any]]:
    """
    可选的用户认证
    如果提供了 Token 则验证，否则返回 None
    """
    if credentials is None:
        return None
    
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


async def check_quota(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """
    检查用户配额是否充足
    使用本地数据库服务
    
    Args:
        current_user: 当前用户信息
        
    Returns:
        用户信息(配额充足时)
        
    Raises:
        HTTPException: 配额已达上限
    """
    user_id = current_user.get("id")
    if user_id == "anonymous" or not user_id:
        return current_user  # 匿名用户或无效 ID 不限制
    
    # 使用本地数据库服务检查配额
    from ..services.database_service import database_service
    
    if not database_service.is_available():
        return current_user
    
    quota_ok = await database_service.check_user_quota(str(user_id))
    
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
