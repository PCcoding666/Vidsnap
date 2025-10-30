# Supabase 环境配置完整指南

## 📋 快速配置步骤

### 1️⃣ 创建 .env 文件

在项目根目录创建 `.env` 文件:

```bash
cd /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer
cp .env.template .env
```

### 2️⃣ 获取 Supabase 密钥

#### 步骤 1: 创建 Supabase 项目

1. 访问 [Supabase Dashboard](https://app.supabase.com/)
2. 点击 **"New Project"**
3. 填写信息:
   - **Name**: My_Youtube_Summarizer
   - **Database Password**: 设置一个强密码(请牢记!)
   - **Region**: 选择最近的地区(如 Singapore)
4. 点击 **"Create new project"**
5. 等待约 1-2 分钟,直到项目创建完成

#### 步骤 2: 复制 API 密钥

1. 进入项目 Dashboard
2. 点击左侧菜单 **Settings** (⚙️图标)
3. 点击 **API** 子菜单
4. 复制以下三个值:

```bash
# 在 "Project URL" 部分
SUPABASE_URL=https://xxxxxxxxxxxxx.supabase.co

# 在 "Project API keys" 部分
# anon public (可公开)
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# service_role (严格保密!)
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### 3️⃣ 填写 .env 文件

打开 `.env` 文件,填入您的密钥:

```bash
# Supabase 配置
SUPABASE_URL=https://xxxxxxxxxxxxx.supabase.co
SUPABASE_ANON_KEY=eyJhbGc...完整的 anon key
SUPABASE_SERVICE_KEY=eyJhbGc...完整的 service_role key

# 阿里云配置(保持原有配置不变)
ALIYUN_ACCESS_KEY_ID=your_existing_key
ALIYUN_ACCESS_KEY_SECRET=your_existing_secret
ALIYUN_OSS_ENDPOINT=oss-cn-beijing.aliyuncs.com
ALIYUN_OSS_BUCKET=your_bucket_name
QWEN_API_KEY=sk-your-qwen-key
```

### 4️⃣ 初始化数据库

#### 方法 1: 使用 Supabase Dashboard (推荐)

1. 在 Supabase Dashboard 点击左侧 **SQL Editor**
2. 点击 **"New query"**
3. 复制 `backend/sql/schema_v1.sql` 的完整内容
4. 粘贴到编辑器
5. 点击 **"Run"** (或按 Ctrl+Enter)
6. 等待执行完成,检查是否有错误信息

#### 方法 2: 使用初始化脚本

```bash
cd backend
python scripts/init_supabase_schema.py
# 按照脚本输出的指引,在 Dashboard 中执行 SQL
```

### 5️⃣ 验证配置

#### 检查数据库表

1. 在 Supabase Dashboard 点击 **Table Editor**
2. 应该看到 7 个新表:
   - ✅ profiles
   - ✅ user_quotas
   - ✅ videos
   - ✅ keyframes
   - ✅ transcripts
   - ✅ transcript_segments
   - ✅ video_summaries

#### 测试服务连接

```bash
cd backend
python -c "from app.services.supabase_service import supabase_service; print('✅ Supabase 可用' if supabase_service.is_available() else '❌ Supabase 不可用')"
```

期望输出:
```
✅ 已加载环境变量文件: /path/to/.env
✅ Supabase 服务初始化成功: https://xxx.supabase.co
✅ Supabase 可用
```

### 6️⃣ 测试 API

#### 启动服务

```bash
cd backend
python -m uvicorn app.main:app --reload
```

#### 测试用户注册

```bash
curl -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "password123",
    "username": "testuser"
  }'
```

期望响应:
```json
{
  "user": {
    "id": "uuid...",
    "email": "test@example.com",
    "username": "testuser",
    "subscription_tier": "free"
  },
  "access_token": "eyJhbGc...",
  "refresh_token": "..."
}
```

#### 测试用户登录

```bash
curl -X POST http://localhost:8000/auth/signin \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "password123"
  }'
```

## 🔍 常见问题

### Q1: "Supabase 服务不可用"

**原因**: 环境变量未正确加载

**解决方案**:
1. 检查 `.env` 文件是否在项目根目录
2. 确认环境变量名称拼写正确(区分大小写)
3. 重启 Python 进程

### Q2: "401 Unauthorized" 错误

**原因**: API 密钥错误或已过期

**解决方案**:
1. 重新从 Supabase Dashboard 复制密钥
2. 确认复制了完整的密钥(JWT 很长)
3. 检查项目状态是否正常

### Q3: 数据库表未创建

**原因**: SQL 脚本执行失败

**解决方案**:
1. 检查 SQL Editor 中的错误信息
2. 确认您有足够的数据库权限
3. 尝试分段执行 SQL(每次执行一个表)

### Q4: "Row Level Security" 阻止访问

**原因**: RLS 策略配置问题

**解决方案**:
1. 使用 `SUPABASE_SERVICE_KEY` 绕过 RLS
2. 检查 RLS 策略是否正确创建
3. 在 Dashboard > Authentication > Policies 查看策略

## 🔒 安全最佳实践

### ✅ 应该做的

- ✅ 将 `.env` 添加到 `.gitignore`
- ✅ 使用环境变量而非硬编码
- ✅ 定期轮换 API 密钥
- ✅ 在生产环境使用密钥管理服务(如 AWS Secrets Manager)
- ✅ 启用 Supabase 项目的 IP 白名单

### ❌ 不应该做的

- ❌ 将 `SUPABASE_SERVICE_KEY` 暴露给前端
- ❌ 将密钥提交到 Git 仓库
- ❌ 在日志中输出密钥
- ❌ 在公开文档中分享密钥
- ❌ 使用弱密码

## 📊 .env 文件完整示例

```bash
# ==============================================================================
# Supabase 配置
# ==============================================================================
SUPABASE_URL=https://abcdefghijklmn.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFiY2RlZmdoaWprbG1uIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MDAwMDAwMDAsImV4cCI6MjAxNTU3NjAwMH0.example-anon-key
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFiY2RlZmdoaWprbG1uIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTcwMDAwMDAwMCwiZXhwIjoyMDE1NTc2MDAwfQ.example-service-key

# ==============================================================================
# 阿里云服务配置
# ==============================================================================
ALIYUN_ACCESS_KEY_ID=LTAI5tABCDefGhIjKlMn
ALIYUN_ACCESS_KEY_SECRET=abc123DEF456ghi789JKL012mno345PQR
ALIYUN_OSS_ENDPOINT=oss-cn-beijing.aliyuncs.com
ALIYUN_OSS_BUCKET=my-youtube-summarizer

# ==============================================================================
# AI 服务配置
# ==============================================================================
QWEN_API_KEY=sk-1234567890abcdef1234567890abcdef

# ==============================================================================
# 应用配置
# ==============================================================================
TEMP_DIR=/tmp/video_analysis
PORT=8000

# ==============================================================================
# 代理配置(可选)
# ==============================================================================
# 如果需要代理访问,取消注释以下行
# https_proxy=http://127.0.0.1:33210
# http_proxy=http://127.0.0.1:33210
# all_proxy=socks5://127.0.0.1:33211
```

## 🎯 下一步

配置完成后,您可以:

1. **测试完整流程**: 参考 [SUPABASE_QUICKSTART.md](./SUPABASE_QUICKSTART.md)
2. **查看集成状态**: 参考 [SUPABASE_INTEGRATION_STATUS.md](./SUPABASE_INTEGRATION_STATUS.md)
3. **开始开发**: 参考 [SUPABASE_IMPLEMENTATION_SUMMARY.md](./SUPABASE_IMPLEMENTATION_SUMMARY.md)

---

**需要帮助?**
- Supabase 官方文档: https://supabase.com/docs
- 项目文档索引: [SUPABASE_README.md](./SUPABASE_README.md)
