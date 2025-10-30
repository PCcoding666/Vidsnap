# Google OAuth 快速参考

本文档提供 Google OAuth 登录功能的快速配置和使用指南。

---

## 🚀 Quick Setup (5 minutes)

### 1. Google Cloud Console Configuration

```bash
# Access Google Cloud Console
https://console.cloud.google.com/

# Create OAuth Client
1. Go to "APIs & Services" → "Credentials"
2. Create "OAuth Client ID" → "Web Application"
3. Add Redirect URI:
   https://<your-supabase-ref>.supabase.co/auth/v1/callback
4. Save Client ID and Secret
```

### 2. Supabase Dashboard Configuration

```bash
# Access Supabase Dashboard
https://app.supabase.com/

# Enable Google Provider
1. Authentication → Providers → Google
2. Paste Google Client ID and Secret
3. Save
```

### 3. Done! No code changes needed

---

## 📡 API 端点

### 获取 Google OAuth URL

```bash
GET /auth/oauth/google?redirect_url={前端回调地址}

# 示例
curl "http://localhost:8000/auth/oauth/google?redirect_url=http://localhost:5173/auth/callback"

# 响应
{
  "url": "https://accounts.google.com/o/oauth2/v2/auth?...",
  "provider": "google"
}
```

### 交换授权码获取 Token

```bash
POST /auth/oauth/callback
Content-Type: application/json

{
  "code": "4/0AY0e-g7..."  # 从回调 URL 获取
}

# 响应
{
  "user": {
    "id": "abc-123",
    "email": "user@gmail.com",
    "username": "user",
    "subscription_tier": "free"
  },
  "access_token": "eyJhbGc...",
  "refresh_token": "v1.MRTY..."
}
```

---

## 🌐 前端集成

### React/Vue/Svelte 通用代码

```typescript
// 1. 点击 "Google 登录" 按钮
async function loginWithGoogle() {
  const redirectUrl = `${window.location.origin}/auth/callback`;
  const res = await fetch(
    `http://localhost:8000/auth/oauth/google?redirect_url=${encodeURIComponent(redirectUrl)}`
  );
  const { url } = await res.json();
  
  // 重定向到 Google 登录
  window.location.href = url;
}

// 2. 在回调页面 (/auth/callback) 处理授权码
useEffect(() => {
  const code = new URLSearchParams(window.location.search).get('code');
  
  if (code) {
    fetch('http://localhost:8000/auth/oauth/callback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code })
    })
      .then(res => res.json())
      .then(({ access_token, refresh_token, user }) => {
        // 保存 Token
        localStorage.setItem('access_token', access_token);
        localStorage.setItem('user', JSON.stringify(user));
        
        // 跳转到首页
        window.location.href = '/dashboard';
      });
  }
}, []);
```

---

## 🧪 测试

### 方法 1: 运行测试脚本

```bash
cd /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer
./app/tests/test_google_oauth.sh
```

### 方法 2: 手动测试

```bash
# 1. 启动后端
cd backend
uvicorn app.main:app --reload

# 2. 访问 API 文档
http://localhost:8000/docs

# 3. 测试 GET /auth/oauth/google
# 4. 在浏览器中打开返回的 URL
# 5. 授权后复制回调 URL 中的 code 参数
# 6. 测试 POST /auth/oauth/callback
```

---

## 🔍 OAuth 流程图

```
用户               前端              后端              Google            Supabase
 |                  |                |                  |                 |
 |-- 点击登录 -----> |                |                  |                 |
 |                  |-- GET /oauth/google ------------> |                 |
 |                  |                |-- sign_in_with_oauth -----------> |
 |                  |<-- OAuth URL --|<-- OAuth URL ----+                 |
 |<-- 重定向 --------|                |                  |                 |
 |                  |                |                  |                 |
 |======= 重定向到 Google 登录页面 =======> |                 |
 |                  |                |                  |                 |
 |-- 授权 ---------> |                |                  |                 |
 |<-- code ---------|                |                  |                 |
 |                  |                |                  |                 |
 |======= 重定向回前端 callback 页面 ======>|                 |
 |                  |                |                  |                 |
 |                  |-- POST /oauth/callback ---------> |                 |
 |                  |                |-- exchange_code_for_session -----> |
 |                  |                |<-- session ------+<-- session -----|
 |                  |<-- Token ------+                  |                 |
 |<-- 登录成功 ------|                |                  |                 |
```

---

## ⚙️ 环境变量

**后端需要:**
```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=eyJhbGc...
SUPABASE_SERVICE_KEY=eyJhbGc...  # 仅后端使用
```

**Google OAuth 凭据在 Supabase 中配置,无需在代码中配置**

---

## 🐛 常见错误

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| `redirect_uri_mismatch` | 重定向 URI 不匹配 | 检查 Google Cloud Console 中的重定向 URI 配置 |
| `access_denied` | 用户取消授权或不在测试用户列表 | 添加到测试用户列表或发布应用 |
| `Invalid OAuth code` | 授权码过期或已使用 | 重新发起 OAuth 流程 |
| `503 Service Unavailable` | Supabase 未配置 | 检查 `.env` 中的 `SUPABASE_*` 变量 |

---

## 📊 支持的登录方式

当前系统支持:

✅ **邮箱密码注册/登录**
- `POST /auth/signup` - 注册
- `POST /auth/signin` - 登录

✅ **Google OAuth 登录**
- `GET /auth/oauth/google` - 获取 OAuth URL
- `POST /auth/oauth/callback` - 处理回调

✅ **Token 验证**
- `GET /auth/me` - 获取当前用户信息

---

## 🔐 安全提示

1. ⚠️ **客户端密钥**仅在 Supabase 中配置,切勿暴露给前端
2. ⚠️ **SUPABASE_SERVICE_KEY** 仅后端使用,禁止提交到 Git
3. ✅ 生产环境使用 HTTPS
4. ✅ 使用 `state` 参数防止 CSRF 攻击(可选)

---

## 📚 详细文档

- [完整配置指南](./GOOGLE_OAUTH_SETUP_GUIDE.md)
- [Supabase 快速入门](./SUPABASE_QUICKSTART.md)
- [API 文档](http://localhost:8000/docs)

---

**最后更新**: 2025-10-29
