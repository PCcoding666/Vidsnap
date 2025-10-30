# Supabase 数据持久化验证指南

## 概述

本文档介绍如何验证 Supabase 中的数据持久化是否正常工作。验证脚本会检查以下内容：

1. **Supabase 连接** - 测试与数据库的连接
2. **用户认证数据** - 检查 `profiles` 表
3. **用户配额数据** - 检查 `user_quotas` 表
4. **视频记录数据** - 检查 `videos` 表
5. **关键帧数据** - 检查 `keyframes` 表
6. **转录段落数据** - 检查 `transcript_segments` 表
7. **视频总结数据** - 检查 `video_summaries` 表

## 快速开始

### 1. 验证所有数据

```bash
cd /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend
python app/tests/verify_supabase_persistence.py
```

### 2. 验证特定用户的数据

```bash
python app/tests/verify_supabase_persistence.py --user-id <user_id>
```

**例子**：
```bash
python app/tests/verify_supabase_persistence.py --user-id 56d85742-b58e-45a7-bda2-99f4f7841286
```

### 3. 验证特定视频的数据

```bash
python app/tests/verify_supabase_persistence.py --video-id <video_id>
```

**例子**：
```bash
python app/tests/verify_supabase_persistence.py --video-id video_20251028_113741_2ced316b
```

## 输出说明

### 成功输出示例

```
======================================================================
  Supabase 数据持久化验证工具
======================================================================

======================================================================
  1. 验证 Supabase 连接
======================================================================

SUPABASE_URL: https://ftnndsllwweerkddhavrzh.supabase.co...
SUPABASE_ANON_KEY: eyJhbGc...
SUPABASE_SERVICE_KEY: eyJhbGc...

✅ Supabase 服务已启用
✅ 数据库连接成功 (schema_versions 表可访问)

======================================================================
  2. 验证用户认证数据
======================================================================

✅ 找到 2 个用户
用户ID                           | 邮箱                      | 用户名          | 订阅等级 | 创建时间
56d85742-b58e-45a7-bda2-99f4f7 | test@example.com          | user_56d8 | free         | 2025-10-28 11:22:27

======================================================================
  3. 验证用户配额数据
======================================================================

✅ 找到 2 个用户的配额记录
用户ID                           | 视频限额   | 已使用   | 存储(MB)     | 已用   | 重置日期
56d85742-b58e-45a7-bda2-99f4f7 | 10         | 1        | 1000         | 50     | 2025-11-28 00:00:00
```

### 错误排查

#### 错误 1：Supabase 服务不可用

```
❌ Supabase 服务不可用
```

**原因**：
- 环境变量未正确设置
- Supabase 库未安装

**解决**：
```bash
# 检查 .env 文件是否存在并包含以下变量
cat backend/.env | grep SUPABASE

# 安装 supabase 库
pip install supabase
```

#### 错误 2：数据库连接失败

```
❌ 数据库连接失败: ...
```

**原因**：
- API 密钥无效或过期
- Supabase 服务不可用
- 网络连接问题

**解决**：
1. 检查 API 密钥是否正确
2. 访问 https://supabase.com 确认服务状态
3. 检查网络连接

#### 错误 3：未找到用户数据

```
❌ 未找到用户数据
```

**原因**：
- 数据库中没有用户记录
- 用户ID 错误

**解决**：
1. 先执行注册和登录操作，创建用户
2. 确认用户ID 格式正确（应为 UUID）
3. 检查 RLS 策略是否阻止了查询

## 数据检查清单

### ✅ 用户认证数据 (profiles)

```
用户ID: 56d85742-b58e-45a7-bda2-99f4f7841286
邮箱: test@example.com
用户名: user_56d8574
订阅等级: free
创建时间: 2025-10-28 11:22:27
```

### ✅ 用户配额数据 (user_quotas)

```
用户ID: 56d85742-b58e-45a7-bda2-99f4f7841286
月度视频限额: 10
已使用视频数: 1
总存储空间(MB): 1000
已使用存储(MB): 50
重置日期: 2025-11-28
```

### ✅ 视频记录数据 (videos)

```
视频ID: 2ced316b-4cd4-4fbf-ac5d-29067012052e
标题: Build beautiful frontends with OpenAI Codex
状态: completed
进度: 100%
来源: youtube
OSS视频URL: https://yt-summerizer-aliyun.oss-cn-hangzhou.aliyuncs.com/videos/20251028/2ced316b.../original/downloaded_video.mp4
OSS音频URL: https://yt-summerizer-aliyun.oss-cn-hangzhou.aliyuncs.com/videos/20251028/2ced316b.../audio/audio.wav
上传时间: 2025-10-28 11:37:41
```

### ✅ 关键帧数据 (keyframes)

```
视频: 2ced316b-4cd4-4fbf-ac5d-29067012052e
总数: 20 个关键帧
示例：
- 帧 0: 时间戳 0.00s, URL: https://yt-summerizer-aliyun.oss-cn-hangzhou.aliyuncs.com/videos/20251028/.../frame_000.jpg
- 帧 1: 时间戳 3.75s, URL: https://yt-summerizer-aliyun.oss-cn-hangzhou.aliyuncs.com/videos/20251028/.../frame_001.jpg
- ...
```

### ✅ 转录段落数据 (transcript_segments)

```
视频: 2ced316b-4cd4-4fbf-ac5d-29067012052e
总数: N 个转录段落
示例：
- 序号 0: [0.0s ~ 2.5s] "Hello everyone, today we're going to build..."
- 序号 1: [2.5s ~ 5.0s] "a beautiful frontend using OpenAI Codex..."
- ...
```

### ✅ 视频总结数据 (video_summaries)

```
视频: 2ced316b-4cd4-4fbf-ac5d-29067012052e

简要总结 (brief):
  这个视频介绍了如何使用 OpenAI Codex 构建前端界面...

标准总结 (standard):
  视频展示了 OpenAI Codex 在前端开发中的应用...

详细总结 (detailed):
  [完整的详细描述]
```

## 数据持久化流程验证

### 1️⃣ 用户注册和登录

```bash
# 注册用户
curl -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "password123",
    "username": "testuser"
  }'

# 预期结果
# ✅ profiles 表中出现新用户
# ✅ user_quotas 表中自动创建配额记录
```

### 2️⃣ 视频处理

```bash
# 发送视频处理请求
curl -X POST http://localhost:8000/video/process \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "youtube_url": "https://www.youtube.com/watch?v=fK_bm84N7bs"
  }'

# 预期结果
# ✅ videos 表中创建视频记录
# ✅ keyframes 表中保存关键帧
# ✅ transcripts 表中创建转录元数据
# ✅ transcript_segments 表中保存转录段落
# ✅ video_summaries 表中保存AI总结
```

### 3️⃣ 数据验证

```bash
# 运行验证脚本
python app/tests/verify_supabase_persistence.py --video-id 2ced316b-4cd4-4fbf-ac5d-29067012052e

# 预期输出
# ✅ 找到视频记录
# ✅ 找到 20 个关键帧
# ✅ 找到 N 个转录段落
# ✅ 找到 3 种粒度的总结
```

## 常见问题 (FAQ)

### Q1: 如何查找用户ID和视频ID?

**A**: 在验证脚本的输出中可以看到。也可以通过以下方式获取：

```bash
# 查看最近的用户ID
python app/tests/verify_supabase_persistence.py

# 输出中会显示所有用户ID和视频ID
```

### Q2: 如果某个表为空，是否意味着出现了问题？

**A**: 不一定。如果系统刚刚设置，可能没有数据。但是：

- **profiles 表应该有数据** - 至少应该有一个用户
- **user_quotas 表应该有数据** - 每个用户应该有一条配额记录
- **videos 表可能为空** - 如果还没有处理任何视频
- **keyframes 表可能为空** - 如果还没有处理任何视频
- **transcript_segments 表可能为空** - 如果还没有处理任何视频
- **video_summaries 表可能为空** - 如果还没有处理任何视频

### Q3: 如何确保 RLS 策略正确？

**A**: RLS 策略应该允许用户访问自己的数据。验证脚本使用管理员客户端（带有 SERVICE_KEY），可以绕过 RLS。如果看到数据，说明 RLS 策略设置正确。

### Q4: 数据多久才能出现在数据库中？

**A**:
- 用户注册：立即出现（通过触发器自动创建）
- 视频处理：在处理过程中逐步出现（每个处理节点更新一次）
- 转录和总结：处理完成后立即保存

## 下一步

验证成功后，你可以：

1. **测试 API 端点** - 通过 API 查询和检索数据
2. **构建前端应用** - 使用 REST API 显示用户数据
3. **实现搜索功能** - 使用转录内容进行全文搜索
4. **配置配额管理** - 根据用户订阅等级限制使用量

## 获取帮助

如果验证失败，请检查以下日志文件：

```bash
# 后端服务日志
tail -f backend/logs/app.log

# Supabase 问题排查
- 访问 https://supabase.com/dashboard
- 检查 API 日志
- 验证 RLS 策略
- 检查表权限
```
