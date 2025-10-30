"""
Google OAuth API 测试
测试 Google OAuth 登录功能的 API 端点
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.services.supabase_service import supabase_service


def test_supabase_availability():
    """测试 Supabase 服务是否可用"""
    print("\n" + "="*60)
    print("测试 1: Supabase 服务可用性检查")
    print("="*60)
    
    if supabase_service.is_available():
        print("✅ Supabase 服务可用")
        return True
    else:
        print("❌ Supabase 服务不可用")
        print("提示: 请检查 .env 文件中的以下配置:")
        print("  - SUPABASE_URL")
        print("  - SUPABASE_ANON_KEY")
        print("  - SUPABASE_SERVICE_KEY")
        return False


def test_oauth_url_generation():
    """测试 OAuth URL 生成"""
    print("\n" + "="*60)
    print("测试 2: Google OAuth URL 生成")
    print("="*60)
    
    if not supabase_service.is_available():
        print("⏭️  跳过(Supabase 不可用)")
        return False
    
    try:
        redirect_url = "http://localhost:5173/auth/callback"
        oauth_url = supabase_service.get_google_oauth_url(redirect_url)
        
        # 验证 URL 格式
        # Supabase 返回的是 Supabase 授权端点,不是直接的 Google URL
        # Supabase 会自动重定向到 Google
        if oauth_url and ("supabase.co/auth/v1/authorize" in oauth_url and "provider=google" in oauth_url):
            print(f"✅ OAuth URL 生成成功")
            print(f"\nOAuth URL:")
            print(f"{oauth_url}")
            print(f"\n重定向地址: {redirect_url}")
            print("\n说明: Supabase 会自动重定向到 Google 登录页面")
            return True
        else:
            print(f"❌ OAuth URL 格式不正确: {oauth_url}")
            return False
    except Exception as e:
        print(f"❌ OAuth URL 生成失败: {e}")
        return False


def test_oauth_code_exchange_mock():
    """测试授权码交换(模拟)"""
    print("\n" + "="*60)
    print("测试 3: OAuth 授权码交换(模拟)")
    print("="*60)
    
    print("⚠️  此测试需要真实的授权码")
    print("提示: 运行以下步骤获取授权码:")
    print("  1. 运行 test_oauth_url_generation() 获取 OAuth URL")
    print("  2. 在浏览器中打开 URL 并授权")
    print("  3. 从回调 URL 中复制 code 参数")
    print("  4. 手动调用 supabase_service.exchange_oauth_code(code)")
    
    return None


def test_oauth_endpoints_exist():
    """测试 OAuth API 端点是否存在"""
    print("\n" + "="*60)
    print("测试 4: 检查 OAuth API 端点")
    print("="*60)
    
    try:
        from app.api.routes.auth import router
        
        # 检查路由
        routes = [route.path for route in router.routes]
        
        expected_routes = [
            "/oauth/google",
            "/oauth/callback"
        ]
        
        all_exist = True
        for route in expected_routes:
            full_path = f"/auth{route}"
            if route in str(routes):
                print(f"✅ 端点存在: {full_path}")
            else:
                print(f"❌ 端点缺失: {full_path}")
                all_exist = False
        
        return all_exist
    except Exception as e:
        print(f"❌ 检查端点失败: {e}")
        return False


def test_oauth_models():
    """测试 OAuth 数据模型"""
    print("\n" + "="*60)
    print("测试 5: OAuth 数据模型")
    print("="*60)
    
    try:
        from app.models.auth import OAuthCallbackRequest, OAuthURLResponse
        
        # 测试 OAuthCallbackRequest
        callback_req = OAuthCallbackRequest(code="test_code_123", state="test_state")
        assert callback_req.code == "test_code_123"
        assert callback_req.state == "test_state"
        print("✅ OAuthCallbackRequest 模型正常")
        
        # 测试 OAuthURLResponse
        oauth_resp = OAuthURLResponse(
            url="https://accounts.google.com/oauth",
            provider="google"
        )
        assert oauth_resp.url == "https://accounts.google.com/oauth"
        assert oauth_resp.provider == "google"
        print("✅ OAuthURLResponse 模型正常")
        
        return True
    except Exception as e:
        print(f"❌ 数据模型测试失败: {e}")
        return False


def main():
    """运行所有测试"""
    print("\n" + "🔍 "*30)
    print("  Google OAuth 登录功能测试套件")
    print("🔍 "*30)
    
    results = []
    
    # 运行测试
    results.append(("Supabase 可用性", test_supabase_availability()))
    results.append(("OAuth URL 生成", test_oauth_url_generation()))
    results.append(("OAuth 授权码交换", test_oauth_code_exchange_mock()))
    results.append(("API 端点检查", test_oauth_endpoints_exist()))
    results.append(("数据模型测试", test_oauth_models()))
    
    # 汇总结果
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    
    passed = sum(1 for _, result in results if result is True)
    failed = sum(1 for _, result in results if result is False)
    skipped = sum(1 for _, result in results if result is None)
    
    for name, result in results:
        if result is True:
            print(f"✅ {name}")
        elif result is False:
            print(f"❌ {name}")
        else:
            print(f"⏭️  {name} (跳过)")
    
    print(f"\n总计: {passed} 通过, {failed} 失败, {skipped} 跳过")
    
    # 输出下一步操作
    print("\n" + "="*60)
    print("下一步操作")
    print("="*60)
    print("1. 配置 Google Cloud Console OAuth 凭据")
    print("   参考: backend/GOOGLE_OAUTH_SETUP_GUIDE.md")
    print("\n2. 在 Supabase Dashboard 启用 Google Provider")
    print("   参考: backend/GOOGLE_OAUTH_QUICKREF.md")
    print("\n3. 运行完整测试:")
    print("   bash app/tests/test_google_oauth.sh")
    print("\n4. 启动后端测试 API:")
    print("   cd backend && uvicorn app.main:app --reload")
    print("   访问: http://localhost:8000/docs")
    print("\n" + "="*60 + "\n")
    
    # 返回退出码
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
