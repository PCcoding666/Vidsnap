# Supabase 数据验证命令快速参考

## 🚀 快速命令

### 1. 验证所有数据（完整扫描）

```bash
cd /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend
python app/tests/verify_supabase_persistence.py
```

**输出**：显示所有用户、配额、视频、关键帧、转录、总结数据

---

### 2. 验证特定用户的数据

```bash
python app/tests/verify_supabase_persistence.py --user-id 56d85742-b58e-45a7-bda2-99f4f7841286
```

**输出**：仅显示该用户的数据

---

### 3. 验证特定视频的数据

```bash
python app/tests/verify_supabase_persistence.py --video-id 2ced316b-4cd4-4fbf-ac5d-29067012052e
```

**输出**：仅显示该视频相关的所有数据

---

## 📊 数据验证标准

| 表名 | 应有数据 | 检查方法 |
|------|---------|---------|
| profiles | ✅ 至少1个用户 | `python verify_supabase_persistence.py` 第2步 |
| user_quotas | ✅ 每个用户1条 | `python verify_supabase_persistence.py` 第3步 |
| videos | ✅ 处理过的视频 | `python verify_supabase_persistence.py` 第4步 |
| keyframes | ✅ 每个视频20个 | `python verify_supabase_persistence.py` 第5步 |
| transcript_segments | ✅ 转录的段落 | `python verify_supabase_persistence.py` 第6步 |
| video_summaries | ✅ 每个视频3种 | `python verify_supabase_persistence.py` 第7步 |

---

## ✅ 成功标志

验证脚本运行成功的标志：

```
✅ Supabase 服务已启用
✅ 数据库连接成功
✅ 找到 N 个用户
✅ 找到 N 个用户的配额记录
✅ 找到 N 个视频记录
✅ 找到 N 个关键帧
✅ 找到 N 个转录任务
✅ 找到 N 个视频总结
```

---

## ❌ 故障排查

### 问题：Supabase 服务不可用

```
❌ Supabase 服务不可用
❌ 无法连接到 Supabase，停止验证
```

**原因和解决**：

1. **环境变量未设置**
   ```bash
   # 检查 .env 文件
   cat /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend/.env | grep SUPABASE
   
   # 应该看到类似输出：
   SUPABASE_URL=https://ftnndsllwweerkddhavrzh.supabase.co
   SUPABASE_ANON_KEY=eyJhbGc...
   SUPABASE_SERVICE_KEY=eyJhbGc...
   ```

2. **supabase 库未安装**
   ```bash
   pip install supabase>=2.10.0
   ```

3. **API 密钥无效**
   - 登录 https://supabase.com/dashboard
   - 检查项目的 API 密钥是否正确
   - 如果密钥无效，重新生成

---

### 问题：未找到用户数据

```
❌ 未找到用户数据
```

**原因和解决**：

1. **用户还未注册**
   ```bash
   # 注册用户
   curl -X POST http://localhost:8000/auth/signup \
     -H "Content-Type: application/json" \
     -d '{
       "email": "test@example.com",
       "password": "password123",
       "username": "testuser"
     }'
   ```

2. **用户ID 错误**
   ```bash
   # 先运行验证脚本看所有用户
   python app/tests/verify_supabase_persistence.py
   # 然后用正确的ID再试
   python app/tests/verify_supabase_persistence.py --user-id <正确的ID>
   ```

---

### 问题：未找到视频数据

```
❌ 未找到视频数据
```

**原因和解决**：

1. **还未处理任何视频**
   ```bash
   # 发送处理请求
   curl -X POST http://localhost:8000/video/process \
     -H "Authorization: Bearer <access_token>" \
     -H "Content-Type: application/json" \
     -d '{"youtube_url": "https://www.youtube.com/watch?v=fK_bm84N7bs"}'
   
   # 等待处理完成后再验证
   ```

2. **用户ID 不匹配**
   ```bash
   # 确保用户ID 正确
   python app/tests/verify_supabase_persistence.py --user-id <user_id>
   ```

---

## 📝 实际验证流程

### 场景 1：验证新用户的完整流程

```bash
# 1️⃣ 注册用户
curl -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newuser@example.com",
    "password": "password123"
  }'

# 记录返回的 user.id，例如：12345678-1234-1234-1234-123456789012

# 2️⃣ 立即验证用户数据（应立即出现）
python app/tests/verify_supabase_persistence.py --user-id 12345678-1234-1234-1234-123456789012

# 预期结果：
# ✅ 找到 1 个用户
# ✅ 找到 1 个用户的配额记录

# 3️⃣ 检查配额（应该是默认值）
# 应看到：
# - monthly_video_limit: 10
# - monthly_videos_used: 0
# - total_storage_mb: 1000
# - used_storage_mb: 0
```

### 场景 2：验证视频处理的完整流程

```bash
# 1️⃣ 获取访问令牌
TOKEN=$(curl -X POST http://localhost:8000/auth/signin \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "password123"
  }' | jq -r '.access_token')

# 2️⃣ 上传视频
curl -X POST http://localhost:8000/video/process \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "youtube_url": "https://www.youtube.com/watch?v=fK_bm84N7bs"
  }'

# 3️⃣ 等待处理完成（可能需要 30-60 秒）
sleep 60

# 4️⃣ 验证数据（应该显示所有处理结果）
python app/tests/verify_supabase_persistence.py

# 预期结果：
# ✅ 找到视频记录
# ✅ 找到 20 个关键帧
# ✅ 找到 N 个转录段落
# ✅ 找到 3 种粒度的总结
```

---

## 🔍 高级检查

### 检查 RLS 策略

RLS（Row Level Security）策略确保用户只能访问自己的数据。验证脚本使用管理员密钥绕过 RLS，如果能读取数据说明：

✅ RLS 策略设置正确  
✅ 数据权限配置正确  
✅ 用户数据隔离生效  

### 检查数据库连接

```bash
# 验证 PostgreSQL 连接是否正常
# 如果看到以下输出，说明连接正常：
# ✅ 数据库连接成功 (schema_versions 表可访问)

# 如果出现连接错误，检查：
# 1. SUPABASE_URL 是否正确
# 2. SUPABASE_SERVICE_KEY 是否有效
# 3. 网络连接是否正常
```

### 检查数据完整性

每个视频应该有：

```
1. videos 表记录 (1条)
2. keyframes 表记录 (20条)
3. transcripts 表记录 (1条)
4. transcript_segments 表记录 (N条)
5. video_summaries 表记录 (3条: brief, standard, detailed)
```

---

## 📞 获取帮助

如果验证失败：

1. **查看服务器日志**
   ```bash
   # 后端服务应该显示数据保存日志
   # 应该看到类似：
   # ✅ 创建视频记录 video_20251028_113741_2ced316b
   # ✅ 保存 20 个关键帧
   # ✅ 保存 N 个转录段落
   # ✅ 保存视频总结
   ```

2. **检查 Supabase Dashboard**
   - 访问 https://supabase.com/dashboard
   - 查看表中的实际数据
   - 检查是否有错误日志

3. **运行诊断**
   ```bash
   python -c "from app.services.supabase_service import supabase_service; print('✅ Supabase 可用' if supabase_service.is_available() else '❌ Supabase 不可用')"
   ```
