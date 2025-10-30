# Supabase 集成快速开始指南

## 30 秒快速启动

### 1. 安装依赖
```bash
cd backend
pip install supabase>=2.10.0
```

### 2. 配置环境变量
在项目根目录 `.env` 文件中添加:
```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_KEY=your_service_key
```

### 3. 初始化数据库
1. 访问 [Supabase Dashboard](https://app.supabase.com/)
2. 进入 SQL Editor
3. 复制并执行 `backend/sql/schema_v1.sql`

### 4. 启动服务
```bash
python -m uvicorn app.main:app --reload
```

### 5. 测试 API

#### 注册用户
```bash
curl -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "password123"}'
```

#### 登录获取 Token
```bash
curl -X POST http://localhost:8000/auth/signin \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "password123"}'
```

#### 处理视频
```bash
curl -X POST http://localhost:8000/video/process \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "youtube_url=https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

## 核心概念

### 认证流程
```
用户注册 → 获取 Token → 使用 Token 调用 API → Token 验证 → 配额检查 → 处理请求
```

### 数据流
```
视频处理 → 创建视频记录 → 保存关键帧 → 保存转录 → 保存总结 → 更新状态 → 递增配额
```

### 配额管理
- 免费用户: 10 个视频/月, 1GB 存储
- Pro 用户: 100 个视频/月, 10GB 存储
- Enterprise: 自定义

## 关键文件

| 文件 | 功能 |
|------|------|
| `app/services/supabase_service.py` | Supabase 服务类 |
| `app/api/routes/auth.py` | 认证路由 |
| `app/api/dependencies.py` | 认证中间件 |
| `sql/schema_v1.sql` | 数据库 Schema |
| `scripts/init_supabase_schema.py` | 初始化脚本 |

## 常用命令

```bash
# 运行初始化脚本
python backend/scripts/init_supabase_schema.py

# 运行测试(待实现)
pytest backend/app/tests/test_supabase_service.py

# 检查服务状态
curl http://localhost:8000/health
```

## 下一步

1. 阅读完整文档: `SUPABASE_INTEGRATION_STATUS.md`
2. 查看设计文档: `SUPABASE_INTEGRATION_DESIGN.md`
3. 完善 Pipeline 集成点
4. 编写单元测试

## 故障排除

### Supabase 服务不可用
- 检查环境变量是否正确配置
- 确认 Supabase 项目状态
- 查看服务日志: `supabase_service.is_available()`

### Token 验证失败
- Token 可能已过期(1 小时有效期)
- 重新登录获取新 Token
- 检查 Authorization Header 格式: `Bearer {token}`

### 配额已满
- 等待下月自动重置
- 升级订阅等级
- 手动修改数据库 `user_quotas` 表

---

**快速链接**:
- [Supabase Dashboard](https://app.supabase.com/)
- [API 文档](http://localhost:8000/docs) (启动服务后访问)
