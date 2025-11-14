# Supabase 集成文档索引

## 📚 文档导航

本目录包含 Supabase 集成的完整文档。请根据您的需求选择合适的文档:

### 🚀 快速开始

### 30 秒快速启动

#### 1. 安装依赖
```bash
cd backend
pip install supabase>=2.10.0
```

#### 2. 配置环境变量
在项目根目录 `.env` 文件中添加:
```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_KEY=your_service_key
```

#### 3. 初始化数据库
1. 访问 [Supabase Dashboard](https://app.supabase.com/)
2. 进入 SQL Editor
3. 复制并执行 `backend/sql/schema_v1.sql`

#### 4. 启动服务
```bash
python -m uvicorn app.main:app --reload
```

#### 5. 测试 API

##### 注册用户
```bash
curl -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "password123"}'
```

##### 登录获取 Token
```bash
curl -X POST http://localhost:8000/auth/signin \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "password123"}'
```

##### 处理视频
```bash
curl -X POST http://localhost:8000/video/process \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "youtube_url=https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

### 核心概念

#### 认证流程
```
用户注册 → 获取 Token → 使用 Token 调用 API → Token 验证 → 配额检查 → 处理请求
```

#### 数据流
```
视频处理 → 创建视频记录 → 保存关键帧 → 保存转录 → 保存总结 → 更新状态 → 递增配额
```

#### 配额管理
- 免费用户: 10 个视频/月, 1GB 存储
- Pro 用户: 100 个视频/月, 10GB 存储
- Enterprise: 自定义

### 关键文件

| 文件 | 功能 |
|------|------|
| `app/services/supabase_service.py` | Supabase 服务类 |
| `app/api/routes/auth.py` | 认证路由 |
| `app/api/dependencies.py` | 认证中间件 |
| `sql/schema_v1.sql` | 数据库 Schema |
| `scripts/init_supabase_schema.py` | 初始化脚本 |

### 常用命令

```bash
# 运行初始化脚本
python backend/scripts/init_supabase_schema.py

# 运行测试(待实现)
pytest backend/app/tests/test_supabase_service.py

# 检查服务状态
curl http://localhost:8000/health
```

### 下一步

1. 阅读完整文档: `SUPABASE_INTEGRATION_STATUS.md`
2. 查看设计文档: `SUPABASE_INTEGRATION_DESIGN.md`
3. 完善 Pipeline 集成点
4. 编写单元测试

### 故障排除

#### Supabase 服务不可用
- 检查环境变量是否正确配置
- 确认 Supabase 项目状态
- 查看服务日志: `supabase_service.is_available()`

#### Token 验证失败
- Token 可能已过期(1 小时有效期)
- 重新登录获取新 Token
- 检查 Authorization Header 格式: `Bearer {token}`

#### 配额已满
- 等待下月自动重置
- 升级订阅等级
- 手动修改数据库 `user_quotas` 表

---

### 📋 实施检查清单

### 核心功能实施状态

#### 配置与基础设施
- [x] 扩展配置系统添加 Supabase 配置项 (`config.py`)
- [x] 创建数据库 Schema SQL 文件 (`sql/schema_v1.sql`)
- [x] 更新 requirements.txt 添加 supabase 依赖
- [x] 创建数据库初始化脚本 (`scripts/init_supabase_schema.py`)

#### 服务层实现
- [x] 实现 SupabaseService 核心服务类
  - [x] 用户注册 (`sign_up_user`)
  - [x] 用户登录 (`sign_in_user`)
  - [x] Token 验证 (`verify_token`)
  - [x] 获取用户资料 (`get_user_profile`)
  - [x] 配额检查 (`check_user_quota`)
  - [x] 配额递增 (`increment_video_usage`)
  - [x] 存储更新 (`update_storage_usage`)
  - [x] 创建视频记录 (`create_video_record`)
  - [x] 更新视频状态 (`update_video_status`)
  - [x] 保存关键帧 (`save_keyframes`)
  - [x] 保存转录段落 (`save_transcript_segments`)
  - [x] 保存视频总结 (`save_video_summary`)
  - [x] 查询视频信息 (`get_video_by_id`)

#### API 路由实现
- [x] 创建认证路由 (`api/routes/auth.py`)
  - [x] POST /auth/signup
  - [x] POST /auth/signin
  - [x] GET /auth/me
- [x] 创建认证数据模型 (`models/auth.py`)
- [x] 实现认证中间件 (`api/dependencies.py`)
  - [x] `get_current_user()` 依赖
  - [x] `check_quota()` 依赖
- [x] 保护视频路由 (`api/routes/video.py`)
  - [x] 添加认证依赖
  - [x] 传递 user_id 到 Pipeline
  - [x] 递增配额使用
- [x] 注册认证路由到主应用 (`main.py`)

#### Pipeline 集成
- [x] 添加 user_id 参数到 process_video_with_summary
- [x] 创建视频记录(0% 初始化)
- [x] 更新视频 URL(15% 视频上传完成)
- [ ] 保存关键帧数据(45% 关键帧上传完成)
- [ ] 保存转录段落(60% 音频转录完成)
- [ ] 保存视频总结(80% LLM 总结完成)
- [ ] 更新处理完成状态(100%)

#### 文档
- [x] 创建集成状态文档 (`SUPABASE_INTEGRATION_STATUS.md`)
- [x] 创建快速开始指南 (`SUPABASE_QUICKSTART.md`)
- [x] 创建实施检查清单 (本文件)

### 待完成任务

#### 高优先级
- [ ] **完善 Pipeline 集成**: 在 `pipeline_service.py` 中添加所有 Supabase 调用点
  - 文件: `backend/app/services/pipeline_service.py`
  - 方法: `process_video_with_summary()`
  - 行数: ~360-440

- [ ] **环境变量配置**: 在 `.env` 文件中添加 Supabase 配置
  ```bash
  SUPABASE_URL=
  SUPABASE_ANON_KEY=
  SUPABASE_SERVICE_KEY=
  ```

- [ ] **数据库初始化**: 在 Supabase Dashboard 执行 `sql/schema_v1.sql`

#### 中优先级
- [ ] **Gradio 界面集成**
  - 添加登录/注册界面
  - 显示用户配额信息
  - 传递认证 Token

- [ ] **单元测试**
  - `test_supabase_service.py`: 服务类测试
  - `test_auth_routes.py`: 认证路由测试
  - `test_auth_middleware.py`: 中间件测试

- [ ] **集成测试**
  - `test_complete_flow_with_auth.py`: 端到端流程测试
  - 配额限制测试
  - 错误处理测试

#### 低优先级
- [ ] **性能优化**
  - 添加 Redis 缓存层
  - 批量插入优化
  - 数据库连接池

- [ ] **监控与日志**
  - 添加 Prometheus 指标
  - 结构化日志输出
  - 错误追踪集成

- [ ] **扩展功能**
  - 视频分享链接
  - 用户收藏功能
  - 视频标签系统

### 环境配置步骤

#### 1. Supabase 项目设置
- [ ] 创建 Supabase 项目
- [ ] 复制项目 URL 和 API Keys
- [ ] 禁用邮箱确认(可选,用于快速测试)

#### 2. 本地环境配置
- [ ] 安装 supabase 依赖: `pip install supabase>=2.10.0`
- [ ] 配置环境变量到 `.env` 文件
- [ ] 验证配置: `python -c "from app.services.supabase_service import supabase_service; print(supabase_service.is_available())"`

#### 3. 数据库初始化
- [ ] 运行初始化脚本: `python backend/scripts/init_supabase_schema.py`
- [ ] 在 Supabase Dashboard SQL Editor 执行 SQL
- [ ] 验证表创建: 检查 Supabase 表编辑器

#### 4. 功能测试
- [ ] 测试用户注册
- [ ] 测试用户登录
- [ ] 测试 Token 验证
- [ ] 测试视频处理(带认证)
- [ ] 检查数据库记录

### 验证检查项

#### API 端点测试
```bash
# 健康检查
curl http://localhost:8000/health

# 用户注册
curl -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "test1234"}'

# 用户登录
curl -X POST http://localhost:8000/auth/signin \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "test1234"}'

# 获取用户信息
curl http://localhost:8000/auth/me \
  -H "Authorization: Bearer YOUR_TOKEN"

# 视频处理
curl -X POST http://localhost:8000/video/process \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "youtube_url=https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

#### 数据库检查
```sql
-- 检查用户
SELECT * FROM public.profiles LIMIT 10;

-- 检查配额
SELECT * FROM public.user_quotas LIMIT 10;

-- 检查视频记录
SELECT video_id, title, processing_status, processing_progress
FROM public.videos
ORDER BY created_at DESC
LIMIT 10;

-- 检查关键帧
SELECT COUNT(*) as keyframe_count, video_id
FROM public.keyframes
GROUP BY video_id;
```

### 代码质量检查

#### Python 代码规范
- [ ] 所有新文件包含完整文档字符串
- [ ] 函数参数和返回值有类型注解
- [ ] 异常处理完整
- [ ] 日志记录规范

#### 安全检查
- [ ] 敏感密钥不硬编码
- [ ] RLS 策略已启用
- [ ] Token 过期时间合理
- [ ] 密码强度验证

#### 性能检查
- [ ] 数据库索引优化
- [ ] 批量插入使用
- [ ] 避免 N+1 查询
- [ ] 异步操作正确实现

### 部署前检查

#### 生产环境配置
- [ ] 环境变量通过密钥管理系统注入
- [ ] CORS 设置为具体域名
- [ ] 数据库备份策略
- [ ] 监控告警配置

#### 安全加固
- [ ] API 速率限制
- [ ] SQL 注入防护
- [ ] XSS 防护
- [ ] HTTPS 强制

#### 文档更新
- [ ] API 文档完整
- [ ] 部署文档更新
- [ ] 故障排除指南
- [ ] 变更日志

### 进度追踪

**当前完成度**: 75%

**核心功能**: ✅ 已完成
**Pipeline 集成**: ⚠️ 部分完成
**测试覆盖**: ❌ 未开始
**生产就绪**: ❌ 未开始

**预计剩余工作量**: 1-2 天

---

---

## 🗂️ 核心文件位置

### 配置文件
- **Config**: `backend/app/core/config.py`
- **Environment**: 项目根目录 `.env`

### 数据库
- **Schema**: `backend/sql/schema_v1.sql`
- **Init Script**: `backend/scripts/init_supabase_schema.py`

### 服务层
- **Supabase Service**: `backend/app/services/supabase_service.py`
- **Pipeline Service**: `backend/app/services/pipeline_service.py`

### API 层
- **Auth Routes**: `backend/app/api/routes/auth.py`
- **Video Routes**: `backend/app/api/routes/video.py`
- **Middleware**: `backend/app/api/dependencies.py`
- **Models**: `backend/app/models/auth.py`

### 主应用
- **Main App**: `backend/app/main.py`

---

## 🎯 常见场景

### 场景 1: 我是新手,想快速了解
1. 阅读 [SUPABASE_QUICKSTART.md](./SUPABASE_QUICKSTART.md)
2. 按照步骤配置环境
3. 测试 API 端点

### 场景 2: 我需要完成剩余工作
1. 查看 [SUPABASE_CHECKLIST.md](./SUPABASE_CHECKLIST.md) 待办任务
2. 阅读 [SUPABASE_INTEGRATION_STATUS.md](./SUPABASE_INTEGRATION_STATUS.md) 待完成部分
3. 按优先级执行

### 场景 3: 我需要向团队汇报
1. 参考 [SUPABASE_IMPLEMENTATION_SUMMARY.md](./SUPABASE_IMPLEMENTATION_SUMMARY.md)
2. 使用代码统计数据
3. 强调技术亮点

### 场景 4: 系统出现问题
1. 检查 [SUPABASE_QUICKSTART.md](./SUPABASE_QUICKSTART.md) 故障排除部分
2. 查看服务日志: `supabase_service.is_available()`
3. 验证环境变量配置

---

## 📞 获取帮助

### 官方文档
- [Supabase 官方文档](https://supabase.com/docs)
- [Supabase Python SDK](https://supabase.com/docs/reference/python/introduction)
- [FastAPI 文档](https://fastapi.tiangolo.com/)

### 项目文档
- 设计文档: (如果有,请添加链接)
- API 文档: `http://localhost:8000/docs` (启动服务后)

---

## 🔄 版本信息

- **当前版本**: v1.0
- **最后更新**: 2025-01-15
- **状态**: 核心功能已完成,待完善集成点
- **完成度**: 75%

---

## ⚡ 快速命令参考

```bash
# 安装依赖
pip install supabase>=2.10.0

# 运行初始化脚本
python backend/scripts/init_supabase_schema.py

# 启动服务
python -m uvicorn app.main:app --reload

# 测试注册
curl -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "password123"}'

# 检查服务状态
curl http://localhost:8000/health
```

---

**💡 提示**: 建议按照文档顺序阅读,先快速开始,再深入了解细节!
