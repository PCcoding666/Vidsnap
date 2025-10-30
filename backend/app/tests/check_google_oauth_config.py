#!/usr/bin/env python3
"""
检查 Google OAuth 配置状态
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "backend"))

from app.services.supabase_service import supabase_service


def check_google_oauth_config():
    """检查 Google OAuth 配置"""
    print("\n" + "="*70)
    print("  Google OAuth 配置检查")
    print("="*70 + "\n")
    
    if not supabase_service.is_available():
        print("❌ Supabase 服务不可用")
        return
    
    print("✅ Supabase 服务可用\n")
    
    # 生成测试 URL
    print("🔍 测试 Google OAuth URL 生成...\n")
    
    try:
        oauth_url = supabase_service.get_google_oauth_url("http://localhost:5173/auth/callback")
        
        print(f"生成的 OAuth URL:")
        print(f"{oauth_url}\n")
        
        # 分析 URL
        if "provider=google" in oauth_url:
            print("✅ URL 包含 provider=google 参数")
        else:
            print("❌ URL 缺少 provider=google 参数")
        
        if "supabase.co/auth/v1/authorize" in oauth_url:
            print("✅ URL 指向 Supabase 授权端点")
        else:
            print("⚠️  URL 格式异常")
        
        # 检查 URL 是否会重定向到 Google
        print("\n" + "="*70)
        print("  重要说明")
        print("="*70)
        print("\n如果您在浏览器中打开上述 URL 后:")
        print("\n✅ 应该看到:")
        print("   - 自动跳转到 Google 登录页面")
        print("   - 显示 'Sign in with Google' 页面")
        print("   - 可以选择 Google 账户并授权")
        print("\n❌ 如果看到:")
        print("   - 直接跳转回 localhost:5173 且带有 UUID code")
        print("   - 错误页面或配置错误提示")
        print("\n💡 这说明:")
        print("   → Supabase 中的 Google Provider 可能未正确配置")
        print("   → 需要在 Supabase Dashboard 中配置 Google Client ID 和 Secret")
        
        print("\n" + "="*70)
        print("  配置步骤（如果未配置）")
        print("="*70)
        print("\n1. 访问 Supabase Dashboard:")
        print("   https://app.supabase.com/")
        
        print("\n2. 选择您的项目并进入:")
        print("   Authentication → Providers → Google")
        
        print("\n3. 检查状态:")
        print("   - 'Enabled' 开关是否打开?")
        print("   - 'Client ID' 是否已填写?")
        print("   - 'Client Secret' 是否已填写?")
        
        print("\n4. 如果未配置，参考文档:")
        print("   backend/GOOGLE_OAUTH_SETUP_GUIDE.md")
        print("   特别是 '步骤 3: 创建 OAuth 客户端凭据'")
        print("   和 '步骤 4: 在 Supabase 中配置 Google OAuth'")
        
        print("\n" + "="*70 + "\n")
        
    except Exception as e:
        print(f"❌ 生成 OAuth URL 失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    check_google_oauth_config()
