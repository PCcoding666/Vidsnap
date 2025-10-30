# Google OAuth 登录功能

为 Supabase 后端添加 Google OAuth 社交登录支持。

---

## ✨ 功能特性

- ✅ **Google OAuth 2.0 登录** - 用户可使用 Google 账号一键登录
- ✅ **自动账号创建** - OAuth 用户首次登录自动创建账号和配额
- ✅ **统一认证体系** - 与邮箱密码登录共享同一套 Token 机制
- ✅ **安全可靠** - 客户端密钥由 Supabase 托管,不暴露给前端
- ✅ **向后兼容** - 不影响现有的邮箱密码登录功能

---

## 📚 文档索引

### 快速开始
- **[快速参考](./GOOGLE_OAUTH_QUICKREF.md)** - 5 分钟快速配置和 API 使用

### 详细配置
- **[完整配置指南](./GOOGLE_OAUTH_SETUP_GUIDE.md)** - 详细的 Google Cloud 和 Supabase 配置步骤

### 技术文档
- **[实现总结](../app/tests/docs/google_oauth_implementation.md)** - 技术实现细节和架构设计

---

## 🚀 快速开始

### 1. 前置条件

确保已完成 Supabase 基础配置:
```bash
# .env 文件
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=eyJhbGc...
SUPABASE_SERVICE_KEY=eyJhbGc...
```

### 2. Configure Google OAuth (External Configuration Required)

#### Step A: Google Cloud Console
1. Visit [Google Cloud Console](https://console.cloud.google.com/)
2. Create an OAuth Client ID
3. Add Redirect URI: `https://<your-supabase-ref>.supabase.co/auth/v1/callback`
4. Save Client ID and Secret

#### Step B: Supabase Dashboard
1. Visit [Supabase Dashboard](https://app.supabase.com/)
2. Authentication → Providers → Google
3. Paste Google Client ID and Secret
4. Save

> 📖 For detailed step-by-step instructions, see [Complete Configuration Guide](./GOOGLE_OAUTH_SETUP_GUIDE.md)

### 3. Test Functionality

```bash
# Run automated tests
python backend/app/tests/test_google_oauth_api.py

# Or run interactive tests
./app/tests/test_google_oauth.sh
```

---

## 📡 API Usage

### Get OAuth Login URL

```bash
GET /auth/oauth/google?redirect_url={frontend-callback-url}
```

**Example:**
```bash
curl "http://localhost:8000/auth/oauth/google?redirect_url=http://localhost:5173/auth/callback"
```

**Response:**
```json
{
  "url": "https://your-project.supabase.co/auth/v1/authorize?...",
  "provider": "google"
}
```

### Handle OAuth Callback

```bash
POST /auth/oauth/callback
Content-Type: application/json

{
  "code": "Authorization code (from callback URL)"
}
```

**Response:**
```json
{
  "user": {
    "id": "uuid",
    "email": "user@gmail.com",
    "username": "user",
    "subscription_tier": "free"
  },
  "access_token": "eyJhbGc...",
  "refresh_token": "v1.MRTY..."
}
```

---

## 🌐 Frontend Integration Example

```typescript
// Step 1: Get OAuth URL and redirect
async function loginWithGoogle() {
  const redirectUrl = `${window.location.origin}/auth/callback`;
  const res = await fetch(
    `http://localhost:8000/auth/oauth/google?redirect_url=${encodeURIComponent(redirectUrl)}`
  );
  const { url } = await res.json();
  
  // Redirect to Google login
  window.location.href = url;
}

// Step 2: Handle authorization code in callback page
useEffect(() => {
  const code = new URLSearchParams(window.location.search).get('code');
  
  if (code) {
    fetch('http://localhost:8000/auth/oauth/callback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code })
    })
      .then(res => res.json())
      .then(({ access_token, user }) => {
        // Save Token
        localStorage.setItem('access_token', access_token);
        
        // Redirect to homepage
        window.location.href = '/dashboard';
      });
  }
}, []);
```

---

## 🔄 OAuth Flow Diagram

```
┌──────────┐        ┌──────────┐        ┌──────────┐        ┌──────────┐
│   User   │        │ Frontend │        │ Backend  │        │  Google  │
└────┬─────┘        └────┬─────┘        └────┬─────┘        └────┬─────┘
     │                   │                   │                   │
     │ 1. Click login    │                   │                   │
     │──────────────────>│                   │                   │
     │                   │                   │                   │
     │                   │ 2. GET /oauth/google                 │
     │                   │──────────────────>│                   │
     │                   │                   │                   │
     │                   │ 3. Return OAuth URL                  │
     │                   │<──────────────────│                   │
     │                   │                   │                   │
     │ 4. Redirect to Google                 │                   │
     │──────────────────────────────────────────────────────────>│
     │                   │                   │                   │
     │ 5. Authorize and return code          │                   │
     │<──────────────────────────────────────────────────────────│
     │                   │                   │                   │
     │ 6. Redirect to callback page          │                   │
     │──────────────────>│                   │                   │
     │                   │                   │                   │
     │                   │ 7. POST /oauth/callback              │
     │                   │──────────────────>│                   │
     │                   │     (code)        │                   │
     │                   │                   │                   │
     │                   │ 8. Verify and create session         │
     │                   │                   │                   │
     │                   │ 9. Return Token   │                   │
     │                   │<──────────────────│                   │
     │                   │                   │                   │
     │ 10. Login success  │                   │                   │
     │<──────────────────│                   │                   │
     │                   │                   │                   │
```

---

## 🧪 Testing

### Automated Test

```bash
# Python unit test
cd backend
python app/tests/test_google_oauth_api.py

# Expected output:
# ✅ Supabase availability
# ✅ OAuth URL generation
# ✅ API endpoint check
# ✅ Data model test
```

### Interactive Test

```bash
# Bash interactive test script
./app/tests/test_google_oauth.sh

# Features:
# - Automatically check service status
# - Generate OAuth URL
# - Open URL in browser
# - Interactive test authorization code exchange
# - Verify Token
```

### Manual Test

```bash
# 1. Start backend
cd backend
uvicorn app.main:app --reload

# 2. Access API documentation
http://localhost:8000/docs

# 3. Test endpoints
# - GET /auth/oauth/google
# - POST /auth/oauth/callback
```

---

## 📊 已实现的功能

### 后端实现

- ✅ **数据模型**
  - `OAuthCallbackRequest` - OAuth 回调请求
  - `OAuthURLResponse` - OAuth URL 响应

- ✅ **服务层**
  - `get_google_oauth_url()` - 生成 OAuth URL
  - `exchange_oauth_code()` - 交换授权码
  - 自动创建用户 profile 和配额

- ✅ **API 端点**
  - `GET /auth/oauth/google` - 获取 OAuth URL
  - `POST /auth/oauth/callback` - 处理 OAuth 回调

### 文档

- ✅ [完整配置指南](./GOOGLE_OAUTH_SETUP_GUIDE.md)
- ✅ [快速参考](./GOOGLE_OAUTH_QUICKREF.md)
- ✅ [实现总结](../app/tests/docs/google_oauth_implementation.md)
- ✅ 本 README

### 测试

- ✅ Python 自动化测试脚本
- ✅ Bash 交互式测试脚本
- ✅ 前端集成示例

---

## 🔐 安全说明

### 敏感信息保护

1. **Google 客户端密钥**
   - ❌ 不要写入代码
   - ❌ 不要提交到 Git
   - ✅ 仅在 Supabase Dashboard 配置

2. **SUPABASE_SERVICE_KEY**
   - ❌ 禁止暴露给前端
   - ❌ 禁止硬编码到代码
   - ✅ 通过环境变量注入

3. **生产环境**
   - ✅ 必须使用 HTTPS
   - ✅ 配置正确的重定向 URI
   - ✅ 定期轮换密钥

---

## 🐛 故障排除

| 问题 | 解决方案 |
|------|----------|
| `redirect_uri_mismatch` | 检查 Google Cloud Console 中的重定向 URI 配置 |
| `access_denied` | 用户取消授权或不在测试用户列表 |
| `Invalid OAuth code` | 授权码已过期,重新发起流程 |
| `503 Service Unavailable` | 检查 Supabase 环境变量配置 |

更多问题请参考 [完整配置指南](./GOOGLE_OAUTH_SETUP_GUIDE.md) 的常见问题部分。

---

## 🚀 下一步

### 已完成 ✅
- [x] Google OAuth 登录功能
- [x] API 端点实现
- [x] 测试脚本
- [x] 文档完善

### 可扩展功能
- [ ] 支持更多 OAuth Provider(GitHub, Facebook 等)
- [ ] OAuth 账号关联功能
- [ ] 自定义 OAuth 回调处理
- [ ] OAuth 用户数据同步

---

## 📞 支持

- 📖 [完整配置指南](./GOOGLE_OAUTH_SETUP_GUIDE.md)
- 📖 [快速参考](./GOOGLE_OAUTH_QUICKREF.md)
- 📖 [Supabase 官方文档](https://supabase.com/docs/guides/auth/social-login/auth-google)
- 📖 [Google OAuth 文档](https://developers.google.com/identity/protocols/oauth2)

---

**版本**: 1.0.0  
**最后更新**: 2025-10-29  
**状态**: ✅ 生产就绪
