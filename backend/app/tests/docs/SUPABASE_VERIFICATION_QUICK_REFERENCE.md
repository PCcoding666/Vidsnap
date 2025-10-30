# Supabase 数据验证 - 快速参考卡

## 🚀 1分钟快速验证

### 最快的方式：运行 Python 脚本

```bash
cd /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend
python -m app.tests.verify_supabase_persistence
```

✅ **输出内容：**
- Supabase 连接状态
- 所有用户列表
- 所有视频处理状态
- 关键帧、转录、总结数据统计

---

## 🎯 2. 针对性验证命令

### 验证特定用户的数据

```bash
python -m app.tests.verify_supabase_persistence --user-id <user_id>
```

**示例：**
```bash
python -m app.tests.verify_supabase_persistence --user-id 550e8400-e29b-41d4-a716-446655440000
```

### 验证特定视频的所有数据

```bash
python -m app.tests.verify_supabase_persistence --video-id <video_id>
```

**示例：**
```bash
python -m app.tests.verify_supabase_persistence --video-id 2ced316b-4cd4-4fbf-ac5d-29067012052e
```

---

## 📊 3. SQL 快速查询

### 3.1 查看所有用户

```sql
SELECT id, email, username, subscription_tier, created_at 
FROM profiles 
ORDER BY created_at DESC;
```

### 3.2 查看所有视频

```sql
SELECT video_id, title, processing_status, processing_progress, upload_time 
FROM videos 
ORDER BY upload_time DESC;
```

### 3.3 查看特定视频的关键帧

```sql
SELECT frame_id, timestamp, oss_image_url 
FROM keyframes 
WHERE video_id = '<video_id>'
ORDER BY frame_id;
```

### 3.4 查看特定视频的转录

```sql
SELECT segment_index, start_time, end_time, text 
FROM transcript_segments 
WHERE video_id = '<video_id>'
ORDER BY segment_index;
```

### 3.5 查看特定视频的总结

```sql
SELECT summary_type, content, model_used 
FROM video_summaries 
WHERE video_id = '<video_id>';
```

### 3.6 查看用户配额使用情况

```sql
SELECT 
  p.username,
  uq.monthly_videos_used,
  uq.monthly_video_limit,
  uq.used_storage_mb,
  uq.total_storage_mb
FROM profiles p
JOIN user_quotas uq ON p.id = uq.user_id;
```

### 3.7 查看处理中的视频

```sql
SELECT video_id, title, processing_progress, processing_started_at
FROM videos
WHERE processing_status = 'processing'
ORDER BY processing_started_at ASC;
```

### 3.8 查看失败的视频

```sql
SELECT video_id, title, error_message
FROM videos
WHERE processing_status = 'failed';
```

---

## 🔍 4. 数据统计查询

### 统计各状态视频数量

```sql
SELECT 
  processing_status,
  COUNT(*) as count,
  AVG(processing_progress) as avg_progress
FROM videos
GROUP BY processing_status;
```

### 统计每个用户的视频数

```sql
SELECT 
  p.username,
  COUNT(v.video_id) as video_count,
  SUM(CASE WHEN v.processing_status = 'completed' THEN 1 ELSE 0 END) as completed
FROM profiles p
LEFT JOIN videos v ON p.id = v.user_id
GROUP BY p.id, p.username
ORDER BY video_count DESC;
```

### 统计转录数据

```sql
SELECT 
  video_id,
  COUNT(*) as segment_count,
  SUM(CHAR_LENGTH(text)) as total_chars,
  MAX(end_time) as duration
FROM transcript_segments
GROUP BY video_id
ORDER BY total_chars DESC;
```

### 统计关键帧

```sql
SELECT 
  video_id,
  COUNT(*) as keyframe_count,
  MIN(timestamp) as first_frame,
  MAX(timestamp) as last_frame
FROM keyframes
GROUP BY video_id
ORDER BY keyframe_count DESC;
```

---

## 📱 5. Supabase 控制台访问

### 步骤
1. 访问 [https://supabase.com/dashboard](https://supabase.com/dashboard)
2. 登录您的账户
3. 选择您的项目
4. 左侧菜单 → **Editor** 查看表数据
5. 左侧菜单 → **SQL Editor** 执行 SQL 查询

### 快速导航
- **profiles** → 用户认证数据
- **user_quotas** → 用户配额
- **videos** → 视频记录
- **keyframes** → 关键帧
- **transcript_segments** → 转录段落
- **video_summaries** → 视频总结

---

## 🛠️ 6. 问题诊断

### 问题：无法连接到 Supabase

**检查步骤：**
```bash
# 1. 检查 .env 文件
cat .env | grep SUPABASE

# 2. 检查环境变量设置
env | grep SUPABASE

# 3. 测试 Python 连接
python -c "from app.core.config import settings; print(settings.supabase_available)"
```

**应该显示：**
```
SUPABASE_URL=https://...
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_KEY=...
True
```

### 问题：查询返回空结果

```bash
# 运行完整验证检查是否有任何数据
python -m app.tests.verify_supabase_persistence

# 如果显示"未找到"，检查：
# 1. 数据库是否真的没有数据
# 2. 是否应该运行测试流程先创建数据
# 3. 是否查询条件有误
```

### 问题：权限错误

**在 Supabase 控制台检查：**
```
Authentication → Policies → 选择表格 → 查看行级安全(RLS)规则
```

如果规则阻止了访问，可能需要调整 RLS 策略。

---

## 📚 7. 数据结构速查

### profiles 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 用户ID |
| email | text | 邮箱 |
| username | text | 用户名 |
| subscription_tier | text | free/pro/enterprise |

### videos 表
| 字段 | 类型 | 说明 |
|------|------|------|
| video_id | UUID | 视频ID |
| title | text | 标题 |
| processing_status | text | pending/processing/completed/failed |
| processing_progress | int | 0-100 |
| oss_video_url | text | 视频URL |

### keyframes 表
| 字段 | 类型 | 说明 |
|------|------|------|
| video_id | UUID | 视频ID |
| frame_id | int | 序号 |
| timestamp | float | 时间戳(秒) |
| oss_image_url | text | 图片URL |

### transcript_segments 表
| 字段 | 类型 | 说明 |
|------|------|------|
| video_id | UUID | 视频ID |
| segment_index | int | 序号 |
| text | text | 转录文本 |
| start_time | float | 开始时间(秒) |
| end_time | float | 结束时间(秒) |

### video_summaries 表
| 字段 | 类型 | 说明 |
|------|------|------|
| video_id | UUID | 视频ID |
| summary_type | text | brief/standard/detailed |
| content | text | 总结内容 |

---

## 🎓 8. 学习资源

- 📖 完整指南：`SUPABASE_DATA_PERSISTENCE_GUIDE.md`
- 💻 验证脚本：`verify_supabase_persistence.py`
- 🔧 Supabase 官方文档：https://supabase.com/docs

---

## ✨ 快速检查清单

- [ ] 已运行 `python -m app.tests.verify_supabase_persistence`
- [ ] 确认 Supabase 连接成功
- [ ] 检查了用户数据（profiles 表）
- [ ] 检查了视频数据（videos 表）
- [ ] 如有问题，查看完整指南进行诊断

---

**最后更新：** 2025-10-28

