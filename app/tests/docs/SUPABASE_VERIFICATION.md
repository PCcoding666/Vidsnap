# Supabase 数据持久化验证 - 完整指南

## 📋 概述

本文档介绍如何验证 Supabase 中的数据持久化是否正常工作。验证脚本会检查以下内容：

1. **Supabase 连接** - 测试与数据库的连接
2. **用户认证数据** - 检查 `profiles` 表
3. **用户配额数据** - 检查 `user_quotas` 表
4. **视频记录数据** - 检查 `videos` 表
5. **关键帧数据** - 检查 `keyframes` 表
6. **转录段落数据** - 检查 `transcript_segments` 表
7. **视频总结数据** - 检查 `video_summaries` 表

---

## 🚀 快速开始

### 方式 1：使用 Shell 脚本（推荐）

```bash
cd /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend

# 验证所有数据
bash app/tests/run_supabase_verification.sh

# 验证特定用户
bash app/tests/run_supabase_verification.sh 56d85742-b58e-45a7-bda2-99f4f7841286

# 验证特定视频
bash app/tests/run_supabase_verification.sh 2ced316b-4cd4-4fbf-ac5d-29067012052e
```

### 方式 2：直接运行 Python 脚本

```bash
cd /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend

# 验证所有数据
python app/tests/verify_supabase_persistence.py

# 验证特定用户
python app/tests/verify_supabase_persistence.py --user-id 56d85742-b58e-45a7-bda2-99f4f7841286

# 验证特定视频
python app/tests/verify_supabase_persistence.py --video-id 2ced316b-4cd4-4fbf-ac5d-29067012052e
```

---

## 📊 验证输出示例

### 成功输出

当验证脚本成功运行时，你会看到类似的输出：

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
用户ID                           | 邮箱                      | 用户名       | 订阅等级 | 创建时间
56d85742-b58e-45a7-bda2-99f4f7 | test@example.com          | user_56d8    | free     | 2025-10-28 11:22:27
...

======================================================================
  3. 验证用户配额数据
======================================================================

✅ 找到 2 个用户的配额记录
...

======================================================================
  4. 验证视频记录数据
======================================================================

✅ 找到 1 个视频记录
📋 视频详情: 2ced316b-4cd4-4fbf-ac5d-29067012052e
  标题: Build beautiful frontends with OpenAI Codex
  状态: completed (100%)
  视频URL: https://yt-summerizer-aliyun.oss-cn-hangzhou.aliyuncs.com/...
  音频URL: https://yt-summerizer-aliyun.oss-cn-hangzhou.aliyuncs.com/...

======================================================================
  5. 验证关键帧数据
======================================================================

✅ 找到 20 个关键帧

📹 视频 2ced316b-4cd4-4fbf-ac5d-29067012052e: 20 个关键帧
帧ID   | 时间戳(s)   | URL (前60字)
0      | 0.00        | https://yt-summerizer-aliyun.oss-cn-hangzhou.aliyuncs.com/...
1      | 3.75        | https://yt-summerizer-aliyun.oss-cn-hangzhou.aliyuncs.com/...
...

======================================================================
  6. 验证转录段落数据
======================================================================

✅ 找到 1 个转录任务

💬 视频 2ced316b-4cd4-4fbf-ac5d-29067012052e: 50 个转录段落
序号 | 开始时间   | 结束时间   | 文本内容
0    | 0.00       | 2.50       | Hello everyone, today we're going...
1    | 2.50       | 5.00       | to build a beautiful frontend using...
...

======================================================================
  7. 验证视频总结数据
======================================================================

✅ 找到 3 个视频总结

📝 视频 2ced316b-4cd4-4fbf-ac5d-29067012052e: 3 种粒度的总结

  总结类型: brief
  模型: qwen3-vl-flash
  内容 (前200字):
  该视频介绍了如何使用 OpenAI Codex...

  总结类型: standard
  模型: qwen3-vl-flash
  内容 (前200字):
  视频展示了 OpenAI Codex 在前端开发...

  总结类型: detailed
  模型: qwen3-vl-flash
  内容 (前200字):
  [完整的详细描述]...

======================================================================
  验证总结
======================================================================

✅ 验证过程完成！

如果上述所有步骤都成功，说明 Supabase 数据持久化工作正常。
```

---

## ✅ 数据完整性检查清单

验证后，你应该能看到以下数据存在于 Supabase 中：

### 用户认证数据 ✅

- [ ] `profiles` 表中至少有 1 个用户记录
  - 包含：`id, email, username, subscription_tier, created_at`
- [ ] `user_quotas` 表中每个用户有 1 条配额记录
  - 包含：`monthly_video_limit=10, monthly_videos_used, total_storage_mb=1000`

### 视频处理数据 ✅

- [ ] `videos` 表中有视频记录
  - 包含：`video_id, user_id, title, processing_status, oss_video_url`
- [ ] `keyframes` 表中有关键帧
  - 每个视频应有约 20 个关键帧
  - 包含：`video_id, frame_id, timestamp, oss_image_url`
- [ ] `transcripts` 表中有转录元数据
  - 包含：`video_id, language, total_segments`
- [ ] `transcript_segments` 表中有转录段落
  - 包含：`video_id, segment_index, text, start_time, end_time`
- [ ] `video_summaries` 表中有 AI 总结
  - 应有 3 条记录（brief, standard, detailed）
  - 包含：`video_id, summary_type, content, model_used`

---

## 🔍 故障排查

### 问题 1：Supabase 服务不可用

**症状**：
```
❌ Supabase 服务不可用
❌ 无法连接到 Supabase，停止验证
```

**解决步骤**：

1. 检查环境变量
   ```bash
   cat /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend/.env | grep SUPABASE
   ```
   
2. 确认三个变量都已设置
   ```
   SUPABASE_URL=https://...supabase.co
   SUPABASE_ANON_KEY=eyJ...
   SUPABASE_SERVICE_KEY=eyJ...
   ```

3. 安装或升级 supabase 库
   ```bash
   pip install supabase>=2.10.0
   ```

4. 测试连接
   ```bash
   python -c "from app.services.supabase_service import supabase_service; print('✅' if supabase_service.is_available() else '❌')"
   ```

### 问题 2：未找到用户数据

**症状**：
```
❌ 未找到用户数据
```

**解决步骤**：

1. 确认用户已注册
   ```bash
   curl -X POST http://localhost:8000/auth/signup \
     -H "Content-Type: application/json" \
     -d '{
       "email": "test@example.com",
       "password": "password123",
       "username": "testuser"
     }'
   ```

2. 获取用户 ID（从注册响应中）并验证
   ```bash
   python app/tests/verify_supabase_persistence.py --user-id <user_id>
   ```

### 问题 3：未找到视频数据

**症状**：
```
❌ 未找到视频数据
```

**解决步骤**：

1. 确认视频处理已完成
   ```bash
   # 首先获取 token
   TOKEN=$(curl -s -X POST http://localhost:8000/auth/signin \
     -H "Content-Type: application/json" \
     -d '{"email":"test@example.com","password":"password123"}' \
     | jq -r '.access_token')
   
   # 发送处理请求
   curl -X POST http://localhost:8000/video/process \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"youtube_url":"https://www.youtube.com/watch?v=fK_bm84N7bs"}'
   ```

2. 等待处理完成（30-60 秒）
   ```bash
   sleep 60
   ```

3. 再次验证
   ```bash
   python app/tests/verify_supabase_persistence.py
   ```

---

## 📈 典型工作流程

### 1. 首次设置验证

```bash
# 运行验证脚本
python app/tests/verify_supabase_persistence.py

# 预期：
# ✅ Supabase 连接成功
# ✅ 找到至少 1 个用户（来自前面的测试）
# ✅ 找到该用户的配额记录
# ❌ 或 ✅ 可能没有视频（正常，还未处理）
```

### 2. 处理视频后验证

```bash
# 上传并处理一个视频后...

# 验证所有数据
python app/tests/verify_supabase_persistence.py

# 预期：
# ✅ 找到视频记录
# ✅ 找到 20 个关键帧
# ✅ 找到转录段落
# ✅ 找到 3 种总结
```

### 3. 特定对象验证

```bash
# 验证特定用户
python app/tests/verify_supabase_persistence.py --user-id 56d85742-b58e-45a7-bda2-99f4f7841286

# 验证特定视频
python app/tests/verify_supabase_persistence.py --video-id 2ced316b-4cd4-4fbf-ac5d-29067012052e

# 预期：
# 仅显示该对象相关的数据
```

---

## 📚 进阶使用

### 自动化验证脚本

创建 `daily_verification.sh`：

```bash
#!/bin/bash

BACKEND_DIR="/Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend"
cd "$BACKEND_DIR"

# 每天运行一次验证
python app/tests/verify_supabase_persistence.py > logs/supabase_verification.log 2>&1

# 检查是否有错误
if grep -q "❌" logs/supabase_verification.log; then
    echo "⚠️ 发现数据持久化问题，请检查日志"
    cat logs/supabase_verification.log
else
    echo "✅ 数据持久化正常"
fi
```

### 集成到测试流程

```bash
# 在 CI/CD 中使用
python app/tests/verify_supabase_persistence.py && echo "✅ Supabase 验证通过" || echo "❌ Supabase 验证失败"
```

---

## 🎯 下一步

验证成功后：

1. **查看详细文档**
   - 参考 `SUPABASE_VERIFICATION_GUIDE.md` 了解完整细节
   - 参考 `SUPABASE_VERIFICATION_QUICK_REFERENCE.md` 获取命令快速参考

2. **集成到业务流程**
   - 在 API 响应中包含数据库查询结果
   - 实现用户数据查询端点
   - 构建视频搜索功能

3. **监控和维护**
   - 定期运行验证脚本
   - 检查数据库性能
   - 监控 RLS 策略

4. **扩展功能**
   - 实现配额管理
   - 添加用户分析
   - 构建推荐系统

---

## 🆘 获取帮助

如果遇到问题：

1. **查看脚本输出**
   - 错误信息会清楚地指示问题原因
   - 按照故障排查部分的步骤解决

2. **检查 Supabase Dashboard**
   - https://supabase.com/dashboard
   - 查看表中的实际数据
   - 检查 API 日志

3. **查看后端日志**
   ```bash
   # 观察后端服务输出
   # 应该看到数据保存日志：
   # ✅ 创建视频记录
   # ✅ 保存关键帧
   # ✅ 保存转录段落
   # ✅ 保存视频总结
   ```

4. **验证服务健康状态**
   ```bash
   python -c "from app.services.supabase_service import supabase_service; print('✅ Supabase 可用' if supabase_service.is_available() else '❌ Supabase 不可用')"
   ```

---

## 📞 关键资源

| 资源 | 位置 | 说明 |
|------|------|------|
| Supabase Dashboard | https://supabase.com/dashboard | 管理数据库、查看表数据 |
| API 文档 | `backend/app/services/supabase_service.py` | Python 服务实现 |
| 数据库 Schema | `backend/sql/schema_v1.sql` | 完整的表结构定义 |
| 配置文件 | `backend/app/core/config.py` | 环境变量加载逻辑 |

---

**祝你验证顺利！** 🎉

如果所有验证都通过，说明你的 Supabase 集成已经完美工作，可以放心使用数据库功能。
