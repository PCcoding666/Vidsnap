#!/usr/bin/env python3
"""
Google OAuth 错误诊断工具

帮助诊断 OAuth 认证过程中的问题
"""
import sys
import os
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "backend"))

from app.services.supabase_service import supabase_service
from app.core.config import settings


def print_section(title):
    """打印章节标题"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def diagnose_config():
    """诊断配置"""
    print_section("1. 诊断 Supabase 配置")
    
    # 检查环境变量
    print("环境变量检查:")
    
    if settings.SUPABASE_URL:
        print(f"✅ SUPABASE_URL: {settings.SUPABASE_URL[:50]}...")
    else:
        print("❌ SUPABASE_URL: 未设置")
    
    if settings.SUPABASE_ANON_KEY:
        print(f"✅ SUPABASE_ANON_KEY: {settings.SUPABASE_ANON_KEY[:40]}...")
    else:
        print("❌ SUPABASE_ANON_KEY: 未设置")
    
    if settings.SUPABASE_SERVICE_KEY:
        print(f"✅ SUPABASE_SERVICE_KEY: {settings.SUPABASE_SERVICE_KEY[:40]}...")
    else:
        print("❌ SUPABASE_SERVICE_KEY: 未设置")
    
    print(f"\nSupabase 可用性: {supabase_service.is_available()}")


def diagnose_oauth_flow():
    """诊断 OAuth 流程"""
    print_section("2. OAuth 流程诊断")
    
    if not supabase_service.is_available():
        print("❌ Supabase 服务不可用，无法测试 OAuth")
        return
    
    print("🔍 正在生成 Google OAuth URL...")
    
    try:
        redirect_url = "http://localhost:5173/auth/callback"
        oauth_url = supabase_service.get_google_oauth_url(redirect_url)
        
        print(f"\n✅ OAuth URL 生成成功")
        print(f"\n完整 URL:")
        print(f"{oauth_url}\n")
        
        print("📋 接下来的步骤:")
        print("  1. 复制上面的 URL")
        print("  2. 在浏览器中打开该 URL")
        print("  3. 使用 Google 账户登录并授权")
        print("  4. 浏览器会重定向到:")
        print(f"     {redirect_url}?code=<authorization_code>")
        print("  5. 从 URL 中复制 code 参数的值")
        print("  6. 使用该 code 调用下一步测试\n")
        
        return oauth_url
    except Exception as e:
        print(f"❌ OAuth URL 生成失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_code_exchange(code: str):
    """测试授权码交换"""
    print_section("3. 测试授权码交换")
    
    if not supabase_service.is_available():
        print("❌ Supabase 服务不可用")
        return
    
    if not code:
        print("❌ 请提供授权码")
        print("\n使用方法:")
        print("  python diagnose_oauth_error.py --code <your_authorization_code>")
        return
    
    print(f"📋 授权码: {code[:50]}...")
    print(f"📋 授权码长度: {len(code)} 字符")
    print(f"📋 授权码类型: {type(code)}\n")
    
    # 检查授权码格式
    if len(code) < 20:
        print("⚠️  警告: 授权码长度异常短")
        print("   Google OAuth 授权码通常在 50-200 字符之间")
        print("   请确认这是从 Google OAuth 回调 URL 中获取的 code 参数\n")
    
    # 检查是否是 UUID
    import re
    uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    if re.match(uuid_pattern, code, re.IGNORECASE):
        print("❌ 错误: 这看起来像是一个 UUID，而不是 OAuth 授权码！")
        print("\n正确的 OAuth 授权码格式示例:")
        print("  4/0AY0e-g7xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
        print("\nUUID 格式示例:")
        print("  a55be990-b30e-41f5-9fae-ed0c5fe8ac24 (这是错误的!)")
        print("\n请确保从浏览器回调 URL 的 'code' 参数获取授权码\n")
        return
    
    print("🔍 正在交换授权码...")
    
    try:
        result = supabase_service.exchange_oauth_code(code)
        
        print("\n✅ 授权码交换成功!\n")
        print("用户信息:")
        print(f"  ID: {result['user']['id']}")
        print(f"  Email: {result['user']['email']}")
        print(f"  Username: {result['user']['username']}")
        print(f"  Tier: {result['user']['subscription_tier']}")
        
        print(f"\nAccess Token: {result['access_token'][:50]}...")
        print(f"Refresh Token: {result['refresh_token'][:50]}...\n")
        
    except Exception as e:
        print(f"\n❌ 授权码交换失败: {e}\n")
        
        # 详细错误诊断
        error_msg = str(e)
        
        if "'str' object has no attribute 'get'" in error_msg:
            print("🔍 错误分析:")
            print("  这个错误通常由以下原因引起:")
            print("  1. 授权码格式不正确")
            print("  2. 授权码已过期(有效期约 10 分钟)")
            print("  3. 授权码已被使用(只能使用一次)")
            print("  4. Supabase OAuth 配置有问题\n")
            
            print("💡 建议:")
            print("  1. 重新获取授权码(重新完成 OAuth 流程)")
            print("  2. 确认授权码是从 'code' 参数获取的，不是其他参数")
            print("  3. 检查 Supabase Dashboard 中的 Google Provider 配置\n")
        
        elif "Invalid" in error_msg or "expired" in error_msg.lower():
            print("🔍 错误分析:")
            print("  授权码无效或已过期\n")
            
            print("💡 解决方案:")
            print("  1. 重新运行步骤 2 获取新的 OAuth URL")
            print("  2. 在浏览器中完成授权流程")
            print("  3. 立即使用新的授权码(不要等待太久)\n")
        
        import traceback
        print("\n完整错误堆栈:")
        traceback.print_exc()


def explain_oauth_flow():
    """解释 OAuth 流程"""
    print_section("Google OAuth 流程说明")
    
    print("""
┌─────────────────────────────────────────────────────────────────┐
│                    正确的 OAuth 2.0 流程                         │
└─────────────────────────────────────────────────────────────────┘

步骤 1: 获取 OAuth URL
  → python diagnose_oauth_error.py --step 1
  → 或者 curl "http://localhost:8000/auth/oauth/google?redirect_url=..."

步骤 2: 用户在浏览器中打开 URL
  → 浏览器会跳转到 Google 登录页面
  → 用户登录并授权应用

步骤 3: Google 重定向回应用
  → 重定向 URL 格式: http://localhost:5173/auth/callback?code=<授权码>
  → 从 URL 中复制完整的 code 参数值

步骤 4: 使用授权码换取 Token
  → python diagnose_oauth_error.py --code <授权码>
  → 或者 curl -X POST "http://localhost:8000/auth/oauth/callback" \\
       -H "Content-Type: application/json" \\
       -d '{"code": "<授权码>"}'

⚠️  常见错误:
  ❌ 使用 UUID 而不是授权码
  ❌ 使用过期的授权码(超过 10 分钟)
  ❌ 重复使用同一个授权码(只能用一次)
  ❌ 使用错误的参数名(应该是 'code' 不是其他)

✅ 正确的授权码格式:
  4/0AY0e-g7xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
  (通常 50-200 字符，包含数字、字母、特殊字符)

❌ 错误的格式(UUID):
  a55be990-b30e-41f5-9fae-ed0c5fe8ac24
  (这不是 OAuth 授权码!)
""")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Google OAuth 错误诊断工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 检查配置和生成 OAuth URL
  python diagnose_oauth_error.py --step 1
  
  # 测试授权码交换
  python diagnose_oauth_error.py --code 4/0AY0e-g7...
  
  # 查看 OAuth 流程说明
  python diagnose_oauth_error.py --explain
        """
    )
    
    parser.add_argument("--step", type=int, choices=[1, 2], help="运行特定步骤")
    parser.add_argument("--code", type=str, help="OAuth 授权码")
    parser.add_argument("--explain", action="store_true", help="显示 OAuth 流程说明")
    
    args = parser.parse_args()
    
    print("\n" + "🔍 "*35)
    print("  Google OAuth 错误诊断工具")
    print("🔍 "*35)
    
    if args.explain:
        explain_oauth_flow()
        return
    
    # 始终运行配置诊断
    diagnose_config()
    
    if args.step == 1 or (not args.code and not args.step):
        # 步骤 1: 生成 OAuth URL
        diagnose_oauth_flow()
    
    if args.code:
        # 测试授权码交换
        test_code_exchange(args.code)
    elif args.step == 2:
        print_section("步骤 2: 授权码交换")
        print("请提供授权码:")
        print("  python diagnose_oauth_error.py --code <your_code>\n")
    
    if not args.code and not args.step:
        explain_oauth_flow()


if __name__ == "__main__":
    main()
