# 系统集成测试快速指南

## 🚀 快速开始

### 一键执行完整测试

```bash
./app/tests/run_system_integration_test.sh
```

---

## 📋 测试内容概览

### ✅ 阶段 1：数据库初始化验证
- 8 张核心数据表结构验证
- Schema 版本管理
- 触发器功能（自动创建用户资料和配额）
- RLS 安全策略启用

### ✅ 阶段 2：服务连接与配置验证
- Supabase 配置完整性
- admin_client 和 anon_client 功能
- 服务降级机制

### ✅ 阶段 3：完整业务流程测试
- 用户注册 → 登录 → Token 验证
- 配额管理（初始配额、使用量递增）
- 视频处理全流程（创建记录 → 状态更新 → 保存数据）
- 数据一致性（外键关联验证）
- 权限验证（RLS 策略）

---

## 🔧 环境要求

### 必需环境变量

在项目根目录或 `backend/` 目录创建 `.env` 文件：

```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Python 依赖

```bash
pip install supabase
```

---

## 📊 测试结果示例

```
======================================================================
测试结果汇总
======================================================================
✅ 通过: 37
❌ 失败: 0
⚠️  警告: 0
======================================================================
🎉 恭喜！所有测试通过！系统集成验证完成。
```

---

## 🔍 关键验证点

### 1. 触发器自动化

**验证**: 用户注册时自动创建 profiles 和 user_quotas 记录

```python
# 注册新用户
supabase_service.sign_up_user(email, password, username)

# 自动创建：
# - profiles 记录（email, username, subscription_tier='free'）
# - user_quotas 记录（monthly_video_limit=10, total_storage_mb=1000）
```

### 2. 配额管理

**初始配额**（免费用户）：
- 月度视频处理：10 个/月
- 存储空间：1000 MB

**验证配额递增**：
```python
# 处理视频后
increment_video_usage(user_id)  # 视频数 +1
update_storage_usage(user_id, 50)  # 存储 +50MB
```

### 3. 数据一致性

**外键关联验证**：
- `videos.user_id` → `profiles.id` ✅
- `keyframes.video_id` → `videos.video_id` ✅
- `transcript_segments.video_id` → `videos.video_id` ✅
- `video_summaries.video_id` → `videos.video_id` ✅

**级联删除**：
- 删除视频 → 自动删除关键帧、转录、总结
- 删除用户 → 自动删除 profiles、quotas、所有视频

### 4. RLS 安全策略

**策略启用状态**：
```sql
-- 用户只能访问自己的数据
CREATE POLICY users_can_view_own_videos ON public.videos
    FOR SELECT USING (auth.uid() = user_id);
```

---

## 🛠️ 故障排查

### 问题 1：Supabase 连接失败

**症状**：
```
❌ Supabase 服务不可用
```

**解决方案**：
1. 检查 `.env` 文件是否存在
2. 确认环境变量已正确设置
3. 验证 Supabase 项目是否激活

### 问题 2：Schema 未初始化

**症状**：
```
❌ 表 'profiles' 不存在
```

**解决方案**：
1. 登录 Supabase Dashboard
2. 导航到 SQL Editor
3. 执行 `backend/sql/schema_v1.sql`

### 问题 3：触发器未生效

**症状**：
```
❌ profiles 记录未创建
```

**解决方案**：
1. 检查触发器是否已创建：
   ```sql
   SELECT * FROM pg_trigger WHERE tgname = 'on_auth_user_created';
   ```
2. 如果不存在，重新执行 `schema_v1.sql` 中的触发器部分

---

## 📁 测试文件位置

```
My_Youtube_Summarizer/
├── app/tests/
│   ├── run_system_integration_test.sh  # 执行脚本
│   └── docs/
│       ├── SYSTEM_INTEGRATION_TEST_REPORT.md  # 详细报告
│       └── SYSTEM_INTEGRATION_QUICK_GUIDE.md  # 本文档
└── backend/
    ├── app/tests/
    │   └── test_full_system_integration.py  # 主测试脚本
    └── sql/
        └── schema_v1.sql  # 数据库 Schema
```

---

## 🎯 测试成功标志

当看到以下输出时，表示测试完全成功：

```
✅ 阶段1 完成：数据库初始化验证通过
✅ 阶段2 完成：服务连接与配置验证通过
✅ 阶段3 完成：完整业务流程测试通过

======================================================================
✅ 通过: 37
❌ 失败: 0
⚠️  警告: 0
======================================================================
🎉 恭喜！所有测试通过！系统集成验证完成。
```

---

## 📚 相关文档

- [完整测试报告](./SYSTEM_INTEGRATION_TEST_REPORT.md)
- [Supabase 集成指南](../../../backend/SUPABASE_README.md)
- [数据库 Schema 文档](../../../backend/sql/schema_v1.sql)

---

**最后更新**: 2025-10-31
