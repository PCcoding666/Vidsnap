# Google OAuth 登录配置指南

本指南将帮助你为 Supabase 后端配置 Google OAuth 登录功能。

---

## 📋 目录

1. [前置条件](#前置条件)
2. [步骤 1: 创建 Google Cloud 项目](#步骤-1-创建-google-cloud-项目)
3. [步骤 2: 配置 OAuth 同意屏幕](#步骤-2-配置-oauth-同意屏幕)
4. [步骤 3: 创建 OAuth 客户端凭据](#步骤-3-创建-oauth-客户端凭据)
5. [步骤 4: 在 Supabase 中配置 Google OAuth](#步骤-4-在-supabase-中配置-google-oauth)
6. [步骤 5: 更新应用配置](#步骤-5-更新应用配置)
7. [步骤 6: 测试 OAuth 流程](#步骤-6-测试-oauth-流程)
8. [常见问题](#常见问题)

---

## Prerequisites

- ✅ Already have a Supabase project and completed basic configuration
- ✅ Have a Google account
- ✅ Backend service is deployed or running locally

---

## Step 1: Create Google Cloud Project

### 1.1 Access Google Cloud Console

1. Open [Google Cloud Console](https://console.cloud.google.com/)
2. Sign in with your Google account

### 1.2 Create a New Project

1. Click the project selector dropdown at the top of the page
2. Click **"New Project"**
3. Enter project name (e.g.: `my-youtube-summarizer`)
4. Click **"Create"**

---

## Step 2: Configure OAuth Consent Screen

### 2.1 Access OAuth Consent Screen Configuration

1. In the left sidebar, select **"APIs & Services" → "OAuth consent screen"**
2. Choose user type:
   - **External**: Allow any Google account to sign in (recommended for production)
   - **Internal**: Limited to users within your organization (requires Google Workspace)
3. Click **"Create"**

### 2.2 Fill in Application Information

**Application Information:**
- **App name**: `My Youtube Summarizer` (or your application name)
- **User support email**: Your email address
- **App logo**: (Optional) Upload your app logo

**Application Domain:**
- **Authorized domains**: 
  - If deploying to production, add your domain name (e.g.: `yourdomain.com`)
  - Skip for local testing

**Developer Contact Information:**
- Provide your email address

### 2.3 Configure Scopes

1. Click **"Add or Remove Scopes"**
2. Select the following scopes:
   - `.../auth/userinfo.email` - View user email address
   - `.../auth/userinfo.profile` - View user's basic profile information
3. Click **"Update"**

### 2.4 Add Test Users (Development Stage)

If you chose "External" user type and your app is in testing:
1. Click **"Add Users"** in the **"Test users"** section
2. Enter the Google account email you want to test
3. Click **"Save"**

---

## Step 3: Create OAuth Client Credentials

### 3.1 Create Credentials

1. In the left sidebar, select **"APIs & Services" → "Credentials"**
2. Click **"Create Credentials" → "OAuth Client ID"**
3. Select application type: **"Web application"**

### 3.2 Configure Client

**Application Name:**
- Enter name (e.g.: `Supabase OAuth Client`)

**Authorized JavaScript Origins:**
- Add your frontend URL:
  ```
  http://localhost:5173        # Local development
  https://yourdomain.com       # Production environment
  ```

**Authorized Redirect URIs:**
- Add Supabase callback URL:
  ```
  https://<your-supabase-project-ref>.supabase.co/auth/v1/callback
  ```
  
  > 📌 Replace `<your-supabase-project-ref>` with your Supabase project reference ID
  > 
  > You can find it in Supabase Dashboard → Settings → API

### 3.3 Save Credentials

1. Click **"Create"**
2. Your **Client ID** and **Client Secret** will be displayed
3. **Important**: Copy and save both values for later use

```
Client ID: 1234567890-abcdefghijklmnopqrstuvwxyz.apps.googleusercontent.com
Client Secret: GOCSPX-xxxxxxxxxxxxxxxxxxxxxxxx
```

---

## Step 4: Configure Google OAuth in Supabase

### 4.1 Sign in to Supabase Dashboard

1. Visit [Supabase Dashboard](https://app.supabase.com/)
2. Select your project

### 4.2 Enable Google Provider

1. In the left sidebar, select **"Authentication" → "Providers"**
2. Find **"Google"** and click it
3. Toggle **"Enable Google provider"** to ON

### 4.3 Fill in Google OAuth Credentials

1. **Client ID**: Paste the Client ID you copied from Google Cloud Console
2. **Client Secret**: Paste the Client Secret
3. **Authorized redirect URIs** will be displayed automatically. Verify it matches the one configured in Google Cloud Console
4. Click **"Save"**

### 4.4 (Optional) Configure Auto-Create Users

Supabase automatically creates accounts for OAuth users by default. If you want to customize this behavior:

1. Go to **"Authentication" → "Settings"**
2. Check **"User signup"** configuration
3. You can choose:
   - ✅ **Enable email confirmations**: Whether email verification is required
   - ✅ **Enable manual linking**: Whether to allow linking OAuth accounts to existing accounts

---

## Step 5: Update Application Configuration

### 5.1 Confirm Environment Variables

Make sure your `.env` file has Supabase credentials configured:

```bash
# Supabase Configuration
SUPABASE_URL=https://<your-project-ref>.supabase.co
SUPABASE_ANON_KEY=eyJhbGc...  # Get from Supabase Dashboard
SUPABASE_SERVICE_KEY=eyJhbGc...  # Get from Supabase Dashboard (backend only)
```

> 📌 How to get: Supabase Dashboard → Settings → API

### 5.2 No Additional Configuration Needed

The Google OAuth Client ID and Secret are already configured in Supabase. No additional configuration is needed in your application code.

---

## Step 6: Test OAuth Flow

### 6.1 Start Backend Service

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

### 6.2 Test API Endpoints

#### (1) Get Google OAuth URL

```bash
curl -X GET "http://localhost:8000/auth/oauth/google?redirect_url=http://localhost:5173/auth/callback"
```

**Expected Response:**
```json
{
  "url": "https://accounts.google.com/o/oauth2/v2/auth?...",
  "provider": "google"
}
```

#### (2) Visit OAuth URL in Browser

1. Copy the returned `url`
2. Open the URL in your browser
3. Select your Google account and authorize
4. You will be redirected back to `redirect_url` with a `code` parameter

Example: `http://localhost:5173/auth/callback?code=4/0AY0e-g7...`

#### (3) Exchange Authorization Code for Token

```bash
curl -X POST "http://localhost:8000/auth/oauth/callback" \
  -H "Content-Type: application/json" \
  -d '{"code": "4/0AY0e-g7..."}'
```

**Expected Response:**
```json
{
  "user": {
    "id": "abc-123-def-456",
    "email": "user@example.com",
    "username": "user",
    "subscription_tier": "free"
  },
  "access_token": "eyJhbGc...",
  "refresh_token": "v1.MRTY..."
}
```

#### (4) Verify Token

```bash
curl -X GET "http://localhost:8000/auth/me" \
  -H "Authorization: Bearer eyJhbGc..."
```

### 6.3 Frontend Integration Example

``typescript
// 1. Get OAuth URL and redirect
async function loginWithGoogle() {
  const redirectUrl = `${window.location.origin}/auth/callback`;
  const response = await fetch(
    `http://localhost:8000/auth/oauth/google?redirect_url=${encodeURIComponent(redirectUrl)}`
  );
  const { url } = await response.json();
  
  // Redirect to Google login page
  window.location.href = url;
}

// 2. Handle authorization code in callback page
// pages/auth/callback.tsx
useEffect(() => {
  const params = new URLSearchParams(window.location.search);
  const code = params.get('code');
  
  if (code) {
    // Exchange authorization code
    fetch('http://localhost:8000/auth/oauth/callback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code })
    })
      .then(res => res.json())
      .then(data => {
        // Save Token
        localStorage.setItem('access_token', data.access_token);
        localStorage.setItem('refresh_token', data.refresh_token);
        
        // Redirect to homepage
        window.location.href = '/dashboard';
      });
  }
}, []);
```

---

## FAQ

### ❓ Error: "redirect_uri_mismatch"

**Cause**: The redirect URI in Google Cloud Console doesn't match the actual request

**Solution**:
1. Check the callback URL displayed in Supabase Dashboard → Authentication → Providers → Google
2. Make sure that URL is added to Google Cloud Console → Credentials → OAuth Client → Authorized Redirect URIs

### ❓ Error: "access_denied"

**Cause**: User cancelled authorization, or the app is in testing mode and the user is not in the test users list

**Solution**:
1. If the app is in testing mode, go to Google Cloud Console → OAuth consent screen → Test users, and add the Google account you want to test
2. Or publish your app to production (requires Google review)

### ❓ Error: "Invalid OAuth code"

**Cause**: Authorization code has expired or been used

**Solution**:
- OAuth authorization codes can only be used once and are valid for a short time (usually 10 minutes)
- Restart the OAuth flow to get a new authorization code

### ❓ Profile Record Not Auto-Created

**Cause**: Database trigger may not be working

**Solution**:
Check if your database has the following trigger:

```sql
-- View trigger
SELECT * FROM pg_trigger WHERE tgname = 'on_auth_user_created';

-- If it doesn't exist, create it manually
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.profiles (id, email, username, subscription_tier)
  VALUES (
    NEW.id,
    NEW.email,
    SPLIT_PART(NEW.email, '@', 1),
    'free'
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
```

### ❓ How to distinguish between Google login and email/password login users?

**Solution 1**: Query the `app_metadata` of `auth.users` table

```python
# In Supabase Service
user_meta = self.admin_client.auth.admin.get_user_by_id(user_id)
providers = user_meta.user.app_metadata.get("providers", [])

if "google" in providers:
    print("User logged in with Google")
else:
    print("User logged in with email/password")
```

**Solution 2**: Add an `auth_provider` field to the `profiles` table

---

## 🎉 Complete!

Your application now supports the following login methods:
- ✅ Email/password registration/login (`POST /auth/signup`, `POST /auth/signin`)
- ✅ Google OAuth login (`GET /auth/oauth/google`, `POST /auth/oauth/callback`)

---

## 📚 Related Documentation

- [Supabase OAuth Documentation](https://supabase.com/docs/guides/auth/social-login/auth-google)
- [Google OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)
- [Project Supabase Quick Start](./SUPABASE_QUICKSTART.md)

---

**Maintainer**: Your Name  
**Last Updated**: 2025-10-29
