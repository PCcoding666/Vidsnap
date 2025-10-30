# Supabase 集成实施文档

## 概述

本文档记录了 YouTube 视频分析系统集成 Supabase 的完整实施情况,包括已完成的功能、待完成的工作以及使用指南。

## 已完成的功能

### 1. 配置管理 ✅

**文件**: `backend/app/core/config.py`

已添加以下 Supabase 配置项:
- `SUPABASE_URL`: Supabase 项目 URL
- `SUPABASE_ANON_KEY`: 匿名客户端密钥
- `SUPABASE_SERVICE_KEY`: 服务角色密钥(后端专用)
- `supabase_available`: 配置完整性检查属性

### 2. 数据库 Schema ✅

**文件**: `backend/sql/schema_v1.sql`

已创建完整的数据库表结构:
- `profiles`: 用户资料表(扩展 auth.users)
- `user_quotas`: 用户配额管理表
- `videos`: 视频信息主表
- `keyframes`: 关键帧表
- `transcripts`: 转录元数据表
- `transcript_segments`: 转录段落表
- `video_summaries`: 视频总结表

**安全特性**:
- Row Level Security (RLS) 已启用
- 自动触发器创建用户资料和配额
- 完整的索引优化

### 3. SupabaseService 服务类 ✅

**文件**: `backend/app/services/supabase_service.py`

**核心功能**:
- 用户认证
  - `sign_up_user()`: 用户注册
  - `sign_in_user()`: 用户登录
  - `verify_token()`: Token 验证
  - `get_user_profile()`: 获取用户资料
  
- 配额管理
  - `check_user_quota()`: 检查配额
  - `increment_video_usage()`: 递增使用次数
  - `update_storage_usage()`: 更新存储使用量
  
- 视频数据管理
  - `create_video_record()`: 创建视频记录
  - `update_video_status()`: 更新处理状态
  - `update_video_urls()`: 更新 OSS URL
  - `save_keyframes()`: 批量保存关键帧
  - `save_transcript_segments()`: 保存转录段落
  - `save_video_summary()`: 保存视频总结
  - `get_video_by_id()`: 查询视频信息
  - `get_user_videos()`: 查询用户视频列表

### 4. 认证路由 ✅

**文件**: `backend/app/api/routes/auth.py`

已实现的端点:
- `POST /auth/signup`: 用户注册
- `POST /auth/signin`: 用户登录
- `GET /auth/me`: 获取当前用户信息(需认证)

**数据模型**:
- `SignUpRequest`
- `SignInRequest`
- `UserResponse`
- `AuthResponse`

### 5. 认证中间件 ✅

**文件**: `backend/app/api/dependencies.py`

已实现的依赖函数:
- `get_current_user()`: 验证 JWT Token 并返回用户信息
- `check_quota()`: 检查用户配额是否充足

**特性**:
- 自动降级模式(Supabase 不可用时跳过认证)
- 标准 HTTP Bearer 认证
- 配额超限返回 429 错误

### 6. 视频路由保护 ✅

**文件**: `backend/app/api/routes/video.py`

已更新的端点:
- `POST /video/process`: 添加了认证依赖和配额检查
- 自动递增用户配额使用次数
- 传递 `user_id` 到 Pipeline 服务

### 7. Pipeline 集成(部分完成) ⚠️

**文件**: `backend/app/services/pipeline_service.py`

已添加:
- `user_id` 参数到 `process_video_with_summary()` 方法
- 初始视频记录创建(0% 进度)
- 视频 URL 更新(15% 进度)

**待完善**:
- 关键帧数据保存(45% 进度)
- 转录数据保存(60% 进度)
- 视频总结保存(80% 进度)
- 处理完成状态更新(100%)

### 8. 数据库初始化脚本 ✅

**文件**: `backend/scripts/init_supabase_schema.py`

**功能**:
- 读取 SQL 文件
- 提供执行指南(Supabase SDK 不支持直接执行 SQL)
- 支持 `--dry-run` 模式

### 9. 依赖更新 ✅

**文件**: `backend/requirements.txt`

已添加:
- `supabase>=2.10.0`

### 10. 路由注册 ✅

**文件**: `backend/app/main.py`

已添加:
- 导入 `auth` 路由模块
- 注册 `/auth` 路由

## 待完成的工作

### 1. Pipeline 完整集成 🔧

需要在 `process_video_with_summary()` 方法中添加以下集成点:

```python
# 在关键帧上传完成后(45%)
if supabase_service.is_available() and user_id:
    supabase_service.update_video_status(video_id, "processing", 45)
    supabase_service.save_keyframes(video_id, keyframes)

# 在音频转录完成后(60%)
if supabase_service.is_available() and user_id:
    supabase_service.update_video_status(video_id, "processing", 60)
    supabase_service.save_transcript_segments(video_id, transcript_result.segments)

# 在 LLM 总结完成后(80%)
if supabase_service.is_available() and user_id:
    supabase_service.update_video_status(video_id, "processing", 80)
    supabase_service.save_video_summary(video_id, "brief", video_summary.brief_summary)
    supabase_service.save_video_summary(video_id, "standard", video_summary.standard_summary)
    supabase_service.save_video_summary(video_id, "detailed", video_summary.detailed_summary)

# 处理完成(100%)
if supabase_service.is_available() and user_id:
    supabase_service.update_video_status(video_id, "completed", 100)
```

**修改位置**: `backend/app/services/pipeline_service.py` 第 360-440 行

### 2. Gradio 界面集成 🔧

需要修改 `backend/gradio_app.py`:
- 添加登录/注册界面
- 在视频处理前进行用户认证
- 显示用户配额信息
- 传递 `user_id` 到处理管道

### 3. 环境变量配置 📋

在项目根目录 `.env` 文件中添加:
```bash
# Supabase 配置
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key_here
SUPABASE_SERVICE_KEY=your_service_key_here
```

### 4. 数据库初始化 📋

**步骤**:
1. 登录 [Supabase Dashboard](https://app.supabase.com/)
2. 创建新项目或选择现有项目
3. 导航到 SQL Editor
4. 复制 `backend/sql/schema_v1.sql` 内容并执行

**或使用 Supabase CLI**:
```bash
supabase db execute -f backend/sql/schema_v1.sql
```

### 5. 单元测试 🧪

需要创建以下测试文件:

**`backend/app/tests/test_supabase_service.py`**:
- 测试用户注册/登录
- 测试 Token 验证
- 测试配额管理
- 测试数据持久化

**`backend/app/tests/test_auth_routes.py`**:
- 测试认证端点
- 测试错误处理
- 测试 Token 过期

### 6. 集成测试 🧪

创建 `backend/app/tests/test_complete_flow_with_auth.py`:
- 测试完整的认证 + 视频处理流程
- 测试配额限制
- 测试数据库记录创建

## 使用指南

### 1. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 到 `.env`(如果不存在,创建新文件):
```bash
cp .env.example .env
```

编辑 `.env` 文件,添加 Supabase 配置。

### 3. 初始化数据库

```bash
python backend/scripts/init_supabase_schema.py
```

按照脚本输出的指南,在 Supabase Dashboard 中执行 SQL。

### 4. 启动服务

```bash
cd backend
python -m uvicorn app.main:app --reload
```

### 5. API 测试

#### 用户注册
```bash
curl -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "password123",
    "username": "testuser"
  }'
```

#### 用户登录
```bash
curl -X POST http://localhost:8000/auth/signin \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "password123"
  }'
```

#### 获取当前用户信息
```bash
curl -X GET http://localhost:8000/auth/me \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

#### 处理视频(需认证)
```bash
curl -X POST http://localhost:8000/video/process \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -F "youtube_url=https://www.youtube.com/watch?v=VIDEO_ID"
```

## 架构优势

### 1. 零影响原则
- Supabase 集成作为可选功能
- 服务不可用时自动降级
- 不影响现有视频处理流程

### 2. 安全性
- Row Level Security (RLS) 保护数据
- JWT Token 认证
- 服务角色密钥严格管理

### 3. 可扩展性
- 支持用户配额管理
- 预留扩展表结构(分享、收藏、标签)
- 支持多粒度视频总结

### 4. 性能优化
- 批量数据插入
- 索引优化
- 异步处理

## 下一步计划

### 阶段 1: 完成核心集成(1-2 天)
- [ ] 完善 Pipeline 集成点
- [ ] 添加错误处理和日志
- [ ] 编写单元测试

### 阶段 2: Gradio 集成(2-3 天)
- [ ] 添加登录/注册界面
- [ ] 显示用户配额
- [ ] 集成认证流程

### 阶段 3: 测试与优化(1-2 天)
- [ ] 端到端测试
- [ ] 性能优化
- [ ] 文档完善

### 阶段 4: 生产部署(1 天)
- [ ] 配置生产环境变量
- [ ] 数据库迁移
- [ ] 监控和日志

## 常见问题

### Q1: Supabase 服务不可用怎么办?
A: 系统会自动降级,跳过认证和数据持久化,仅执行视频处理。

### Q2: 如何重置用户配额?
A: 配额每月自动重置,或通过 Supabase Dashboard 手动修改 `user_quotas` 表。

### Q3: 如何修改配额限制?
A: 更新用户的 `subscription_tier`,系统会根据等级设置不同的配额。

### Q4: 数据库迁移如何管理?
A: 使用 `backend/sql/migrations/` 目录存放迁移脚本,按版本号顺序执行。

## 联系与支持

如有问题,请参考:
- [Supabase 官方文档](https://supabase.com/docs)
- [设计文档](./SUPABASE_INTEGRATION_DESIGN.md)
- 项目 Issue 跟踪器

---

**最后更新**: 2025-01-15  
**版本**: v1.0  
**状态**: 核心功能已完成,待完善集成点
