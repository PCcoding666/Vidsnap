# Supabase 数据持久化验证完全指南

## 📋 目录
1. [快速开始](#快速开始)
2. [三种验证方式](#三种验证方式)
3. [数据结构说明](#数据结构说明)
4. [常见问题解决](#常见问题解决)
5. [深入诊断](#深入诊断)

---

## 快速开始

### 方式1️⃣：运行 Python 验证脚本（推荐）

**最简单的验证方法，适合快速检查所有数据。**

```bash
# 进入项目目录
cd /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend

# 运行验证脚本
python -m app.tests.verify_supabase_persistence

# 或者验证特定用户
python -m app.tests.verify_supabase_persistence --user-id <user_id>

# 或者验证特定视频
python -m app.tests.verify_supabase_persistence --video-id <video_id>
```

**脚本会输出：**
- ✅ Supabase 连接状态
- 📊 所有用户列表及其资料
- 📈 用户配额使用情况
- 📹 视频处理状态和进度
- 🖼️ 关键帧数据统计
- 💬 转录段落信息
- 📝 视频总结内容

---

## 三种验证方式

### 方式 2️⃣：通过 Supabase 官方控制台

**用于直观查看数据的最佳方式。**

#### 步骤 1：登录 Supabase 控制台
1. 访问 [https://supabase.com/dashboard](https://supabase.com/dashboard)
2. 使用您的 Supabase 账户登录

#### 步骤 2：导航到您的项目
- 在项目列表中找到您的视频分析项目
- 点击进入项目

#### 步骤 3：查看各个表格

**查看用户认证数据：**
```
左侧菜单 → Editor → profiles 表
```
- 显示：用户ID、邮箱、用户名、订阅等级、创建时间等
- 可以直接编辑和删除记录

**查看用户配额：**
```
左侧菜单 → Editor → user_quotas 表
```
- 显示：每个用户的月度视频数限额、已使用数、存储配额等

**查看视频记录：**
```
左侧菜单 → Editor → videos 表
```
- 显示：视频ID、标题、处理状态、处理进度(0-100%)、OSS URL等

**查看关键帧：**
```
左侧菜单 → Editor → keyframes 表
```
- 显示：关键帧ID、对应视频ID、时间戳、图片URL、场景描述

**查看转录数据：**
```
左侧菜单 → Editor → transcript_segments 表
```
- 显示：转录段落的文本、时间范围、语音置信度、说话人ID

**查看视频总结：**
```
左侧菜单 → Editor → video_summaries 表
```
- 显示：各种粒度的总结(brief/standard/detailed)、使用的AI模型、内容

#### 步骤 4：运行 SQL 查询

在 Supabase 控制台中使用 SQL Editor：

**统计所有视频处理状态：**
```sql
SELECT 
  processing_status,
  COUNT(*) as count,
  AVG(processing_progress) as avg_progress
FROM videos
GROUP BY processing_status;
```

**查看最新的 5 个视频及其处理进度：**
```sql
SELECT 
  video_id,
  title,
  processing_status,
  processing_progress,
  upload_time
FROM videos
ORDER BY upload_time DESC
LIMIT 5;
```

**统计每个用户的视频数和使用配额：**
```sql
SELECT 
  p.username,
  COUNT(v.video_id) as total_videos,
  SUM(CASE WHEN v.processing_status = 'completed' THEN 1 ELSE 0 END) as completed_videos,
  uq.monthly_videos_used,
  uq.monthly_video_limit
FROM profiles p
LEFT JOIN videos v ON p.id = v.user_id
LEFT JOIN user_quotas uq ON p.id = uq.user_id
GROUP BY p.id, p.username, uq.monthly_videos_used, uq.monthly_video_limit;
```

**检查特定视频的所有关键帧：**
```sql
SELECT 
  frame_id,
  timestamp,
  scene_description,
  oss_image_url
FROM keyframes
WHERE video_id = '<your_video_id>'
ORDER BY frame_id ASC;
```

**检查特定视频的转录内容：**
```sql
SELECT 
  segment_index,
  start_time,
  end_time,
  text,
  confidence,
  speaker_id
FROM transcript_segments
WHERE video_id = '<your_video_id>'
ORDER BY segment_index ASC;
```

---

### 方式 3️⃣：通过 Python 脚本进行自定义查询

**用于需要特定查询和数据处理的场景。**

创建文件 `backend/app/tests/custom_supabase_query.py`：

```python
#!/usr/bin/env python3
"""
自定义 Supabase 查询脚本
根据需要修改查询条件
"""

import sys
from pathlib import Path

# 配置路径
project_root = Path(__file__).parent.parent.parent.parent
backend_path = project_root / "backend"
sys.path.insert(0, str(backend_path))

from app.services.supabase_service import supabase_service

def query_videos_by_status():
    """查询指定状态的视频"""
    if not supabase_service.is_available():
        print("❌ Supabase 不可用")
        return
    
    admin_client = supabase_service.admin_client
    
    # 查询所有 "processing" 状态的视频
    response = admin_client.table("videos").select("*").eq("processing_status", "processing").execute()
    
    print(f"\n🎬 正在处理的视频: {len(response.data)} 个")
    for video in response.data:
        print(f"\n  视频ID: {video['video_id']}")
        print(f"  标题: {video['title']}")
        print(f"  进度: {video['processing_progress']}%")
        print(f"  上传时间: {video['upload_time']}")


def query_user_keyframes(video_id: str):
    """查询特定视频的关键帧统计"""
    if not supabase_service.is_available():
        print("❌ Supabase 不可用")
        return
    
    admin_client = supabase_service.admin_client
    
    # 查询关键帧
    response = admin_client.table("keyframes").select("*").eq("video_id", video_id).execute()
    
    keyframes = response.data
    print(f"\n🖼️  视频 {video_id} 的关键帧: {len(keyframes)} 个")
    
    if keyframes:
        print("\n关键帧列表:")
        print(f"{'帧ID':<8} {'时间戳':<12} {'URL (前60字)':<60}")
        print("-" * 80)
        
        for kf in sorted(keyframes, key=lambda x: x['frame_id']):
            url = kf.get('oss_image_url', '')[:60]
            print(f"{kf['frame_id']:<8} {kf['timestamp']:<12.2f} {url:<60}")


def query_transcript_length(video_id: str):
    """查询转录文本的总长度"""
    if not supabase_service.is_available():
        print("❌ Supabase 不可用")
        return
    
    admin_client = supabase_service.admin_client
    
    # 查询转录段落
    response = admin_client.table("transcript_segments").select("*").eq("video_id", video_id).execute()
    
    segments = response.data
    total_text = "".join([seg.get('text', '') for seg in segments])
    
    print(f"\n📊 视频 {video_id} 的转录统计:")
    print(f"  总段落数: {len(segments)}")
    print(f"  总文字数: {len(total_text)} 字")
    print(f"  平均段落长度: {len(total_text) / len(segments) if segments else 0:.1f} 字")
    
    # 显示前3个段落
    if segments:
        print("\n  前3个段落:")
        for i, seg in enumerate(segments[:3]):
            start = seg.get('start_time', 0)
            end = seg.get('end_time', 0)
            text = seg.get('text', '')[:50]
            print(f"    [{i+1}] {start:.1f}s-{end:.1f}s: {text}...")


def check_storage_usage():
    """检查所有用户的存储使用情况"""
    if not supabase_service.is_available():
        print("❌ Supabase 不可用")
        return
    
    admin_client = supabase_service.admin_client
    
    # 查询所有配额
    response = admin_client.table("user_quotas").select("*").execute()
    
    quotas = response.data
    print(f"\n💾 用户存储使用情况: 共 {len(quotas)} 个用户")
    
    total_storage = 0
    total_limit = 0
    
    print(f"\n{'用户':<10} {'已使用(MB)':<15} {'总容量(MB)':<15} {'使用率':<10}")
    print("-" * 50)
    
    for quota in quotas:
        used = quota.get('used_storage_mb', 0)
        limit = quota.get('total_storage_mb', 0)
        usage_rate = (used / limit * 100) if limit > 0 else 0
        
        total_storage += used
        total_limit += limit
        
        print(f"{quota['user_id'][:10]:<10} {used:<15.1f} {limit:<15.1f} {usage_rate:<10.1f}%")
    
    print("-" * 50)
    total_rate = (total_storage / total_limit * 100) if total_limit > 0 else 0
    print(f"{'总计':<10} {total_storage:<15.1f} {total_limit:<15.1f} {total_rate:<10.1f}%")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("  自定义 Supabase 查询工具")
    print("="*70)
    
    # 运行示例查询
    query_videos_by_status()
    check_storage_usage()
    
    # 如果需要查询特定视频，取消下面的注释并替换 video_id
    # query_user_keyframes("2ced316b-4cd4-4fbf-ac5d-29067012052e")
    # query_transcript_length("2ced316b-4cd4-4fbf-ac5d-29067012052e")
    
    print("\n" + "="*70)
```

**使用此脚本：**
```bash
cd backend
python app/tests/custom_supabase_query.py
```

---

## 数据结构说明

### 1. `profiles` 表 - 用户认证数据

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | UUID | 用户ID (Supabase Auth ID) |
| email | text | 用户邮箱 |
| username | text | 用户名 |
| subscription_tier | text | 订阅等级 (free/pro/enterprise) |
| avatar_url | text | 头像URL |
| created_at | timestamp | 创建时间 |
| updated_at | timestamp | 更新时间 |

**验证示例：**
```sql
SELECT * FROM profiles WHERE email = 'user@example.com';
```

---

### 2. `user_quotas` 表 - 用户配额数据

| 字段名 | 类型 | 说明 |
|--------|------|------|
| user_id | UUID | 用户ID |
| monthly_video_limit | integer | 月度视频处理限额 |
| monthly_videos_used | integer | 本月已使用次数 |
| total_storage_mb | integer | 总存储空间(MB) |
| used_storage_mb | integer | 已使用存储空间(MB) |
| reset_date | date | 配额重置日期 |

**验证示例：**
```sql
SELECT 
  user_id,
  monthly_videos_used,
  monthly_video_limit,
  used_storage_mb,
  total_storage_mb
FROM user_quotas
WHERE used_storage_mb > 0;
```

---

### 3. `videos` 表 - 视频记录

| 字段名 | 类型 | 说明 |
|--------|------|------|
| video_id | UUID | 视频唯一标识 |
| user_id | UUID | 上传者ID |
| title | text | 视频标题 |
| source_type | text | 来源类型 (youtube/local) |
| source_url | text | 源URL (YouTube链接或本地路径) |
| processing_status | text | 处理状态 (pending/processing/completed/failed) |
| processing_progress | integer | 处理进度 (0-100) |
| oss_video_url | text | 处理后的视频URL |
| oss_audio_url | text | 提取的音频URL |
| processing_started_at | timestamp | 处理开始时间 |
| processing_completed_at | timestamp | 处理完成时间 |
| error_message | text | 错误信息(若处理失败) |
| upload_time | timestamp | 上传时间 |
| created_at | timestamp | 记录创建时间 |

**验证示例：**
```sql
-- 查看所有视频及其处理进度
SELECT video_id, title, processing_status, processing_progress 
FROM videos 
ORDER BY upload_time DESC;

-- 查看处理失败的视频
SELECT video_id, title, error_message 
FROM videos 
WHERE processing_status = 'failed';

-- 查看处理进度分布
SELECT 
  processing_status,
  COUNT(*) as count
FROM videos
GROUP BY processing_status;
```

---

### 4. `keyframes` 表 - 关键帧数据

| 字段名 | 类型 | 说明 |
|--------|------|------|
| keyframe_id | UUID | 关键帧记录ID |
| video_id | UUID | 关联视频ID |
| frame_id | integer | 关键帧序号 |
| timestamp | float | 视频中的时间戳(秒) |
| oss_image_url | text | 关键帧图片URL |
| scene_description | text | 场景描述(由AI生成) |
| created_at | timestamp | 创建时间 |

**验证示例：**
```sql
-- 查看某视频的所有关键帧
SELECT frame_id, timestamp, oss_image_url
FROM keyframes
WHERE video_id = '<video_id>'
ORDER BY frame_id;

-- 统计每个视频的关键帧数
SELECT 
  video_id,
  COUNT(*) as keyframe_count
FROM keyframes
GROUP BY video_id;
```

---

### 5. `transcript_segments` 表 - 转录段落

| 字段名 | 类型 | 说明 |
|--------|------|------|
| segment_id | UUID | 段落记录ID |
| video_id | UUID | 关联视频ID |
| segment_index | integer | 段落序号 |
| text | text | 转录文本内容 |
| start_time | float | 开始时间(秒) |
| end_time | float | 结束时间(秒) |
| confidence | float | 转录置信度(0-1) |
| speaker_id | integer | 说话人ID (若支持) |
| created_at | timestamp | 创建时间 |

**验证示例：**
```sql
-- 查看某视频的所有转录段落
SELECT segment_index, start_time, end_time, text, confidence
FROM transcript_segments
WHERE video_id = '<video_id>'
ORDER BY segment_index;

-- 统计转录数据量
SELECT 
  video_id,
  COUNT(*) as segment_count,
  SUM(CHAR_LENGTH(text)) as total_chars
FROM transcript_segments
GROUP BY video_id;
```

---

### 6. `video_summaries` 表 - 视频总结

| 字段名 | 类型 | 说明 |
|--------|------|------|
| summary_id | UUID | 总结记录ID |
| video_id | UUID | 关联视频ID |
| summary_type | text | 总结类型 (brief/standard/detailed) |
| content | text | 总结内容 |
| model_used | text | 使用的AI模型 |
| created_at | timestamp | 创建时间 |

**验证示例：**
```sql
-- 查看某视频的所有总结
SELECT summary_type, model_used, content
FROM video_summaries
WHERE video_id = '<video_id>';

-- 统计总结类型分布
SELECT 
  summary_type,
  COUNT(*) as count
FROM video_summaries
GROUP BY summary_type;
```

---

## 常见问题解决

### ❌ 问题1：无法连接到 Supabase

**症状：** 运行脚本时出现 "Supabase 服务不可用" 错误

**原因：**
- .env 文件未配置
- SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY 不完整

**解决方案：**
```bash
# 1. 检查 .env 文件是否存在
ls -la .env

# 2. 检查环境变量是否正确设置
grep SUPABASE .env

# 3. 如果未设置，从 .env.example 复制
cp .env.example .env

# 4. 编辑 .env 填入正确的值
# SUPABASE_URL=https://xxx.supabase.co
# SUPABASE_ANON_KEY=xxx
# SUPABASE_SERVICE_KEY=xxx
```

---

### ❌ 问题2：查询返回空结果

**症状：** 运行脚本后显示 "未找到数据"

**原因：**
- 数据库中确实没有数据
- 关键字段值不匹配
- 权限不足

**解决方案：**
```bash
# 检查数据库中是否有任何数据
python app/tests/verify_supabase_persistence.py

# 检查特定用户的数据
python app/tests.verify_supabase_persistence --user-id <user_id>

# 检查特定视频的数据
python app/tests.verify_supabase_persistence --video-id <video_id>
```

---

### ❌ 问题3：API 密钥权限不足

**症状：** 查询时出现 "permission denied" 或 "not authenticated" 错误

**原因：**
- SUPABASE_SERVICE_KEY 过期
- API 密钥权限配置不当
- RLS (Row-Level Security) 规则阻止了查询

**解决方案：**

在 Supabase 控制台检查 RLS 规则：
```
左侧菜单 → Authentication → Policies → 选择表格
```

如果需要调整权限，联系 Supabase 项目管理员。

---

### ❌ 问题4：视频处理卡在某个进度

**症状：** `processing_progress` 长时间不更新

**原因：**
- 后端处理服务出错
- 网络连接中断
- AI 服务（阿里云 OSS、Qwen 等）不可用

**诊断方法：**
```sql
-- 查看卡住的视频详情
SELECT 
  video_id,
  processing_status,
  processing_progress,
  processing_started_at,
  error_message
FROM videos
WHERE processing_status = 'processing'
  AND processing_started_at < NOW() - INTERVAL '1 hour';
```

**解决方案：**
1. 检查后端日志：`tail -f backend/logs/app.log`
2. 检查 OSS 服务连接：运行 `python backend/diagnose_oss_url.py`
3. 检查转录服务：确认 TRANSCRIPT_SERVICE_API_KEY 有效

---

## 深入诊断

### 检查点1️⃣：认证系统

```bash
# 运行认证测试
cd backend
python -m app.tests.test_chat_service

# 查看输出中的认证相关日志
```

**预期结果：**
```
✅ Supabase 服务初始化成功
✅ Token 验证通过
```

---

### 检查点2️⃣：数据写入操作

```bash
# 运行完整流程测试
cd backend
bash app/tests/run_complete_pipeline_test.sh

# 这会从头到尾测试整个数据流：
# 1. 视频下载
# 2. OSS 上传
# 3. 关键帧提取
# 4. 音频转录
# 5. 视频总结
# 6. 数据持久化到 Supabase
```

---

### 检查点3️⃣：数据读取操作

```bash
# 创建诊断脚本
cat > backend/app/tests/diagnose_supabase_read.py << 'EOF'
#!/usr/bin/env python3
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "backend"))

from app.services.supabase_service import supabase_service

# 测试各个表的读取权限
tables = ['profiles', 'user_quotas', 'videos', 'keyframes', 'transcript_segments', 'video_summaries']

for table in tables:
    try:
        response = supabase_service.admin_client.table(table).select("*").limit(1).execute()
        count = len(response.data)
        print(f"✅ {table}: 可读 ({count} 条记录)")
    except Exception as e:
        print(f"❌ {table}: 读取失败 - {e}")
EOF

python backend/app/tests/diagnose_supabase_read.py
```

---

### 检查点4️⃣：网络连接

```bash
# 测试到 Supabase 的连接
curl -I https://<your_supabase_url>/rest/v1/

# 预期响应：200 OK
```

---

## 总结

使用本指南，您可以通过以下方式验证 Supabase 数据持久化：

| 方式 | 复杂度 | 适用场景 |
|------|--------|---------|
| Python 脚本 | ⭐ | 快速检查、自动化测试 |
| 网页控制台 | ⭐⭐ | 直观查看、编辑数据 |
| SQL 查询 | ⭐⭐⭐ | 深度分析、统计报告 |

**推荐工作流：**
1. 🚀 首先运行 Python 脚本快速检查
2. 📊 通过网页控制台直观查看关键数据
3. 🔍 如有异常，使用 SQL 查询深入诊断
4. 🐛 参考"常见问题解决"部分解决问题

**如有问题，检查清单：**
- ✅ .env 文件是否正确配置
- ✅ Supabase 服务是否在线
- ✅ API 密钥是否有效且未过期
- ✅ 数据库连接权限是否正确
- ✅ 后端服务是否正常运行
