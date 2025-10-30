# Google OAuth 问题排查和解决方案

## 📋 当前问题

您遇到了两个问题：

### 问题 1: 授权码是 UUID 格式（❌ 错误）
```
http://localhost:5173/auth/callback?code=78cd7c27-6991-4186-a004-bc850a903999
```

**原因分析：**
- 这个 UUID 是 Supabase 内部的 PKCE code_verifier，不是 Google OAuth 授权码
- 说明 Supabase 的 Google Provider **未正确配置**
- Google OAuth 客户端可能未在 Supabase Dashboard 中配置

### 问题 2: 前端服务未运行（❌ 错误）
```
ERR_CONNECTION_REFUSED - localhost:5173
```

---

## ✅ 解决方案

### 🔧 步骤 1: 配置 Google OAuth（必须完成）

#### 1.1 创建 Google OAuth 客户端

1. **访问 Google Cloud Console:**
   ```
   https://console.cloud.google.com/
   ```

2. **创建或选择项目**

3. **启用 OAuth 同意屏幕:**
   - 导航: `APIs & Services` → `OAuth consent screen`
   - 选择 `External` 用户类型
   - 填写应用名称: `My Youtube Summarizer`
   - 填写用户支持邮箱
   - 添加作用域: `userinfo.email` 和 `userinfo.profile`
   - 添加测试用户（您的 Google 账户邮箱）

4. **创建 OAuth 客户端 ID:**
   - 导航: `APIs & Services` → `Credentials`
   - 点击 `Create Credentials` → `OAuth Client ID`
   - 应用类型: `Web application`
   - 名称: `Supabase OAuth Client`
   
   - **重要：添加授权的重定向 URI:**
     ```
     https://ftnndslwweerkddhavrh.supabase.co/auth/v1/callback
     ```
   
   - 保存后会得到：
     - **Client ID**: `xxxx.apps.googleusercontent.com`
     - **Client Secret**: `GOCSPX-xxxx`
   
   - **复制并保存这两个值！**

#### 1.2 在 Supabase Dashboard 配置

1. **访问 Supabase Dashboard:**
   ```
   https://app.supabase.com/project/ftnndslwweerkddhavrh/auth/providers
   ```

2. **找到 Google Provider:**
   - 点击 `Google` 提供商

3. **启用并配置:**
   - ✅ 打开 `Enabled` 开关
   - 粘贴 **Client ID**
   - 粘贴 **Client Secret**
   - 点击 `Save`

4. **验证回调 URL:**
   - Supabase 会显示回调 URL，确认与 Google Cloud Console 中配置的一致
   - 应该是: `https://ftnndslwweerkddhavrh.supabase.co/auth/v1/callback`

---

### 🚀 步骤 2: 测试 OAuth 流程

#### 2.1 重新生成 OAuth URL

```bash
cd /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend
python app/tests/diagnose_oauth_error.py --step 1
```

**预期输出：**
```
生成的 OAuth URL:
https://ftnndslwweerkddhavrh.supabase.co/auth/v1/authorize?provider=google&...
```

#### 2.2 在浏览器测试

1. **复制** OAuth URL
2. **在浏览器中打开**该 URL
3. **观察跳转行为：**

   **✅ 正确行为（配置成功）：**
   - 自动跳转到 **Google 登录页面**
   - 显示 "使用 Google 登录" 或 "Sign in with Google"
   - 可以选择 Google 账户

   **❌ 错误行为（配置失败）：**
   - 直接跳转回 `localhost:5173?code=<UUID>`
   - 显示错误页面
   - 提示配置错误

#### 2.3 完成授权流程（配置成功后）

1. **选择您的 Google 账户**
2. **点击"允许"授权应用**
3. **浏览器会重定向到：**
   ```
   http://localhost:5173/auth/callback?code=4/0AY0e-g7XXXXX...
   ```
   
   **注意：** 此时前端服务未运行会报错，但 `code` 参数应该是 **长字符串**，不再是 UUID

4. **从 URL 提取授权码：**
   - URL 中 `code=` 后面的完整字符串
   - 通常 50-200 字符
   - 示例: `4/0AY0e-g7xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

#### 2.4 测试授权码交换

```bash
# 替换 <真实授权码> 为从浏览器 URL 复制的 code 值
python app/tests/diagnose_oauth_error.py --code "<真实授权码>"
```

**预期成功响应：**
```
✅ 授权码交换成功!

用户信息:
  ID: uuid...
  Email: your-email@gmail.com
  Username: your-email
  Tier: free

Access Token: eyJhbGc...
Refresh Token: v1.MRTY...
```

---

### 💻 步骤 3: 启动前端服务（可选，用于完整测试）

如果您想测试完整的 OAuth 回调流程，需要启动前端：

```bash
cd /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/frontend
npm install  # 如果还没安装依赖
npm run dev  # 启动开发服务器
```

**前端应该监听在：** `http://localhost:5173`

---

## 🎯 快速检查清单

配置前请确认：

### Google Cloud Console
- [ ] 已创建 OAuth 客户端 ID
- [ ] 已添加重定向 URI: `https://ftnndslwweerkddhavrh.supabase.co/auth/v1/callback`
- [ ] 已保存 Client ID 和 Client Secret
- [ ] OAuth 同意屏幕已配置
- [ ] 测试用户列表中已添加您的 Google 账户

### Supabase Dashboard
- [ ] Google Provider 已启用
- [ ] Client ID 已填写
- [ ] Client Secret 已填写
- [ ] 配置已保存

### 测试验证
- [ ] OAuth URL 可以跳转到 Google 登录页面
- [ ] 授权后的 code 是长字符串（不是 UUID）
- [ ] 授权码可以成功交换为 Token

---

## ❓ 常见问题

### Q1: 授权后仍然返回 UUID code

**原因：** Supabase Google Provider 未配置

**解决：**
1. 检查 Supabase Dashboard → Authentication → Providers → Google
2. 确认 `Enabled` 开关已打开
3. 确认 Client ID 和 Secret 已填写
4. 保存后重试

### Q2: Google 登录页面显示 "redirect_uri_mismatch"

**原因：** Google Cloud Console 中的重定向 URI 配置不正确

**解决：**
1. 确认 Supabase 回调 URL: `https://ftnndslwweerkddhavrh.supabase.co/auth/v1/callback`
2. 在 Google Cloud Console → Credentials → OAuth Client → Authorized redirect URIs 中添加该 URL
3. 保存后等待 1-2 分钟生效

### Q3: 显示 "access_denied"

**原因：** 测试用户未添加或用户取消了授权

**解决：**
1. 在 Google Cloud Console → OAuth consent screen → Test users 中添加您的 Google 账户
2. 确保在授权页面点击"允许"而不是"拒绝"

---

## 📚 相关文档

- **[完整配置指南](../../backend/GOOGLE_OAUTH_SETUP_GUIDE.md)** - 详细的分步配置说明
- **[快速参考](../../backend/GOOGLE_OAUTH_QUICKREF.md)** - 快速命令参考
- **[错误修复指南](./google_oauth_error_fix.md)** - 常见错误和解决方案

---

## 🔗 快速链接

- **Google Cloud Console:** https://console.cloud.google.com/
- **Supabase Dashboard:** https://app.supabase.com/project/ftnndslwweerkddhavrh/auth/providers
- **测试脚本:** `backend/app/tests/diagnose_oauth_error.py`

---

**更新时间:** 2025-10-30  
**状态:** 待配置
