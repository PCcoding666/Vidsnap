"""
用户中心API路由
提供用户资料、设置和配额管理
"""
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Literal
from pydantic import BaseModel, Field
from datetime import date
import logging
import jwt

from ...services.supabase_service import supabase_service
from ...services.database_service import database_service
from ...core.config import settings

router = APIRouter(prefix="/user", tags=["user"])
security = HTTPBearer()
logger = logging.getLogger(__name__)


# ========================================================================
# Pydantic Models
# ========================================================================

class UserProfile(BaseModel):
    """用户资料"""
    id: str
    email: str
    username: Optional[str]
    full_name: Optional[str]
    avatar_url: Optional[str]
    subscription_tier: str
    created_at: str


class UserProfileUpdate(BaseModel):
    """用户资料更新请求"""
    display_name: Optional[str] = Field(None, min_length=1, max_length=50, description="显示名称")
    gender: Optional[Literal["male", "female", "other", "prefer_not_to_say"]] = Field(None, description="性别")
    birthday: Optional[date] = Field(None, description="生日")


class UserSettings(BaseModel):
    """用户设置"""
    language: str = "zh-CN"
    theme: Literal["system", "light", "dark"] = "system"


class UserSettingsUpdate(BaseModel):
    """用户设置更新请求"""
    language: Optional[str] = Field(None, description="语言偏好")
    theme: Optional[Literal["system", "light", "dark"]] = Field(None, description="主题")


# ========================================================================
# Helper Functions
# ========================================================================

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """验证用户身份并返回用户信息（本地 JWT 验证）"""
    token = credentials.credentials
    
    try:
        # 使用本地 JWT 验证（跳过 audience 验证，手动检查）
        payload = jwt.decode(
            token, 
            settings.JWT_SECRET, 
            algorithms=["HS256"],
            options={"verify_aud": False}  # 跳过 audience 验证
        )
        
        # 手动验证 audience
        aud = payload.get("aud", [])
        if isinstance(aud, list):
            if "fastapi-users:auth" not in aud:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="无效的访问令牌"
                )
        elif aud != "fastapi-users:auth":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的访问令牌"
            )
        
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的访问令牌"
            )
        
        return {
            "id": user_id,
            "email": payload.get("email"),
        }
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="访问令牌已过期"
        )
    except jwt.InvalidTokenError as e:
        logger.error(f"JWT 验证失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的访问令牌"
        )


# ========================================================================
# User Profile Routes
# ========================================================================

@router.get("/profile")
async def get_user_profile(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    获取当前用户资料
    
    Returns:
        用户资料信息
    """
    user = await get_current_user(credentials)
    user_id = user.get("id")
    
    try:
        # 使用本地数据库服务
        profile = await database_service.get_user_profile(user_id)
        
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户资料不存在"
            )
        
        return {
            "status": "success",
            "profile": {
                "id": profile.get("id"),
                "email": profile.get("email"),
                "username": profile.get("username"),
                "display_name": profile.get("display_name"),
                "full_name": profile.get("full_name"),
                "avatar_url": profile.get("avatar_url"),
                "gender": profile.get("gender"),
                "birthday": profile.get("birthday"),
                "subscription_tier": profile.get("subscription_tier", "free"),
                "created_at": profile.get("created_at")
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"获取用户资料失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取用户资料失败: {str(e)}"
        )


@router.put("/profile")
async def update_user_profile(
    request: UserProfileUpdate,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    更新用户资料
    
    Args:
        request: 更新请求（显示名称、性别、生日）
        
    Returns:
        更新后的用户资料
    """
    user = await get_current_user(credentials)
    user_id = user.get("id")
    
    try:
        # 构建更新数据
        update_data = {}
        if request.display_name is not None:
            update_data["display_name"] = request.display_name
        if request.gender is not None:
            update_data["gender"] = request.gender
        if request.birthday is not None:
            update_data["birthday"] = request.birthday.isoformat()
        
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="没有提供要更新的字段"
            )
        
        # 更新数据库
        response = supabase_service.admin_client.table("profiles").update(
            update_data
        ).eq("id", user_id).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户资料不存在"
            )
        
        updated_profile = response.data[0]
        
        return {
            "status": "success",
            "message": "资料更新成功",
            "profile": {
                "id": updated_profile.get("id"),
                "email": updated_profile.get("email"),
                "display_name": updated_profile.get("display_name"),
                "gender": updated_profile.get("gender"),
                "birthday": updated_profile.get("birthday"),
                "subscription_tier": updated_profile.get("subscription_tier", "free")
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"更新用户资料失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新用户资料失败: {str(e)}"
        )


@router.get("/settings")
async def get_user_settings(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    获取用户设置
    
    Returns:
        用户设置信息（语言、主题）
    """
    user = await get_current_user(credentials)
    user_id = user.get("id")
    
    try:
        # 使用本地数据库服务
        profile = await database_service.get_user_profile(user_id)
        
        if not profile:
            # 返回默认设置
            return {
                "status": "success",
                "settings": {
                    "language": "zh-CN",
                    "theme": "system"
                }
            }
        
        return {
            "status": "success",
            "settings": {
                "language": profile.get("language", "zh-CN"),
                "theme": profile.get("theme", "system")
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"获取用户设置失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取用户设置失败: {str(e)}"
        )


@router.put("/settings")
async def update_user_settings(
    request: UserSettingsUpdate,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    更新用户设置
    
    Args:
        request: 更新请求（语言、主题）
        
    Returns:
        更新后的设置
    """
    user = await get_current_user(credentials)
    user_id = user.get("id")
    
    try:
        # 构建更新数据
        update_data = {}
        if request.language is not None:
            update_data["language"] = request.language
        if request.theme is not None:
            update_data["theme"] = request.theme
        
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="没有提供要更新的字段"
            )
        
        # 使用本地数据库服务更新
        updated = await database_service.update_user_profile(user_id, update_data)
        
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户资料不存在"
            )
        
        return {
            "status": "success",
            "message": "设置更新成功",
            "settings": {
                "language": updated.get("language", "zh-CN"),
                "theme": updated.get("theme", "system")
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"更新用户设置失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新用户设置失败: {str(e)}"
        )


@router.get("/quota")
async def get_user_quota(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    获取用户配额信息
    
    Returns:
        配额使用情况
    """
    user = await get_current_user(credentials)
    user_id = user.get("id")
    
    try:
        # 使用本地数据库服务获取配额信息
        quota = await database_service.get_user_quota(user_id)
        
        if not quota:
            # 如果没有配额记录，返回默认值
            return {
                "status": "success",
                "quota": {
                    "monthly_video_limit": 10,
                    "monthly_videos_used": 0,
                    "total_storage_mb": 1000,
                    "used_storage_mb": 0,
                    "reset_date": None,
                    "videos_remaining": 10,
                    "storage_remaining_mb": 1000
                }
            }
        
        return {
            "status": "success",
            "quota": {
                "monthly_video_limit": quota.get("monthly_video_limit", 10),
                "monthly_videos_used": quota.get("monthly_videos_used", 0),
                "total_storage_mb": quota.get("total_storage_mb", 1000),
                "used_storage_mb": quota.get("used_storage_mb", 0),
                "reset_date": quota.get("reset_date"),
                # 计算剩余
                "videos_remaining": quota.get("monthly_video_limit", 10) - quota.get("monthly_videos_used", 0),
                "storage_remaining_mb": quota.get("total_storage_mb", 1000) - quota.get("used_storage_mb", 0)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"获取配额信息失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取配额信息失败: {str(e)}"
        )


@router.get("/stats")
async def get_user_stats(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    获取用户使用统计
    
    Returns:
        统计信息
    """
    user = await get_current_user(credentials)
    user_id = user.get("id")
    
    try:
        # 获取视频统计
        videos = supabase_service.get_user_videos(user_id, limit=1000)
        total_videos = len(videos)
        completed_videos = len([v for v in videos if v.get("processing_status") == "completed"])
        
        return {
            "status": "success",
            "stats": {
                "total_videos": total_videos,
                "completed_videos": completed_videos,
                "processing_videos": len([v for v in videos if v.get("processing_status") == "processing"]),
                "failed_videos": len([v for v in videos if v.get("processing_status") == "failed"])
            }
        }
        
    except Exception as e:
        logger.exception(f"获取用户统计失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取统计失败: {str(e)}"
        )
