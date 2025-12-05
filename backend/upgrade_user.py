#!/usr/bin/env python3
"""
用户订阅升级脚本
用于将指定用户升级到 Pro 或 Enterprise 订阅等级
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))

from app.services.supabase_service import SupabaseService

def upgrade_user(email: str, tier: str = "enterprise"):
    """
    升级用户订阅等级
    
    Args:
        email: 用户邮箱
        tier: 订阅等级 (free/pro/enterprise)
    """
    service = SupabaseService()
    
    if not service.is_available():
        print("❌ Supabase 服务不可用")
        return False
    
    try:
        # 1. 根据邮箱查找用户
        print(f"🔍 查找用户: {email}")
        user_response = service.admin_client.table("profiles")\
            .select("*")\
            .eq("email", email)\
            .execute()
        
        if not user_response.data:
            print(f"❌ 未找到用户: {email}")
            return False
        
        user = user_response.data[0]
        user_id = user["id"]
        current_tier = user.get("subscription_tier", "free")
        
        print(f"✅ 找到用户:")
        print(f"   - ID: {user_id}")
        print(f"   - 邮箱: {email}")
        print(f"   - 当前等级: {current_tier}")
        print(f"   - 用户名: {user.get('username', 'N/A')}")
        
        # 2. 更新订阅等级
        print(f"\n🔄 升级到: {tier.upper()}")
        service.admin_client.table("profiles")\
            .update({"subscription_tier": tier})\
            .eq("id", user_id)\
            .execute()
        
        # 3. 更新配额限制
        quota_limits = {
            "free": {
                "monthly_video_limit": 10,
                "total_storage_mb": 100
            },
            "pro": {
                "monthly_video_limit": 100,
                "total_storage_mb": 5000
            },
            "enterprise": {
                "monthly_video_limit": 99999,  # 无限制
                "total_storage_mb": 99999999   # 无限制
            }
        }
        
        limits = quota_limits.get(tier, quota_limits["free"])
        
        print(f"🔄 更新配额限制...")
        service.admin_client.table("user_quotas")\
            .update({
                "monthly_video_limit": limits["monthly_video_limit"],
                "total_storage_mb": limits["total_storage_mb"]
            })\
            .eq("user_id", user_id)\
            .execute()
        
        print(f"\n✅ 升级成功!")
        print(f"   - 新等级: {tier.upper()}")
        print(f"   - 月度视频限制: {limits['monthly_video_limit']}")
        print(f"   - 存储空间: {limits['total_storage_mb']} MB")
        
        return True
        
    except Exception as e:
        print(f"❌ 升级失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # 从命令行参数获取邮箱和等级
    if len(sys.argv) < 2:
        print("用法: python upgrade_user.py <email> [tier]")
        print("tier 可选值: free, pro, enterprise (默认: enterprise)")
        sys.exit(1)
    
    email = sys.argv[1]
    tier = sys.argv[2] if len(sys.argv) > 2 else "enterprise"
    
    if tier not in ["free", "pro", "enterprise"]:
        print(f"❌ 无效的订阅等级: {tier}")
        print("可选值: free, pro, enterprise")
        sys.exit(1)
    
    success = upgrade_user(email, tier)
    sys.exit(0 if success else 1)
