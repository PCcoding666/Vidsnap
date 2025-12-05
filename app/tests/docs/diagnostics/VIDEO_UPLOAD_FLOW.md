# 视频上传处理完整链路梳理

> **文档目标**: 详细描述从前端文件选择到最终处理完成的完整技术流程，识别每个环节的异常点

---

## 📋 目录

- [1. 完整流程概览](#1-完整流程概览)
- [2. 详细链路分析](#2-详细链路分析)
  - [2.1 前端上传阶段](#21-前端上传阶段)
  - [2.2 网络传输层](#22-网络传输层)
  - [2.3 后端接收阶段](#23-后端接收阶段)
  - [2.4 管道处理阶段](#24-管道处理阶段)
  - [2.5 云存储阶段](#25-云存储阶段)
  - [2.6 数据库持久化](#26-数据库持久化)
- [3. 异常点分析](#3-异常点分析)
- [4. 数据流转图](#4-数据流转图)

---

## 1. 完整流程概览

### 时序图

```
用户           前端           Nginx         FastAPI        Pipeline        OSS/Supabase
 │              │              │              │              │                  │
 │─选择文件─────>│              │              │              │                  │
 │              │              │              │              │                  │
 │              │─构造FormData─>│              │              │                  │
 │              │              │              │              │                  │
 │              │              │─反向代理─────>│              │                  │
 │              │              │              │              │                  │
 │              │              │              │─接收文件─────>│                  │
 │              │              │              │              │                  │
 │              │              │              │              │─验证文件─────────>│
 │              │              │              │              │                  │
 │              │              │              │              │─提取关键帧───────>│
 │              │              │              │              │                  │
 │              │              │              │              │─转录音频─────────>│
 │              │              │              │              │                  │
 │              │              │              │              │─生成总结─────────>│
 │              │              │              │              │                  │
 │              │              │              │              │<─返回URLs────────│
 │              │              │              │              │                  │
 │              │              │              │<─返回结果────│                  │
 │              │              │              │              │                  │
 │              │              │<─返回响应────│              │                  │
 │              │              │              │              │                  │
 │              │<─显示结果────│              │              │                  │
 │<─查看总结────│              │              │              │                  │
```

### 关键指标

| 阶段 | 正常耗时 | 关键操作 | 失败率（理想） |
|------|---------|---------|---------------|
| 前端上传 | < 5s (100MB) | FormData 构造 | < 1% |
| 网络传输 | 根据带宽 | HTTP POST | < 2% |
| 后端接收 | < 10s | 文件写入磁盘 | < 1% |
| 视频处理 | 30-60s | 关键帧提取 | < 5% |
| 音频转录 | 40-120s | Paraformer-v2 | < 3% |
| 视频总结 | 20-60s | Qwen3-VL | < 3% |
| OSS 上传 | 10-30s | 云存储 | < 2% |

---

## 2. 详细链路分析

### 2.1 前端上传阶段

#### 2.1.1 文件选择 (React 组件)

**代码位置**: `frontend/src/components/video-upload/` (推测)

**技术实现**:
```jsx
// 示例代码（基于标准 React 实现）
const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
  const file = event.target.files?.[0];
  if (!file) return;
  
  // 验证文件类型
  const allowedTypes = ['video/mp4', 'video/avi', 'video/mov', 'video/x-matroska'];
  if (!allowedTypes.includes(file.type)) {
    alert('不支持的文件格式');
    return;
  }
  
  // 验证文件大小（例如限制 500MB）
  const maxSize = 500 * 1024 * 1024;
  if (file.size > maxSize) {
    alert('文件过大，最大支持 500MB');
    return;
  }
  
  setSelectedFile(file);
};
```

**关键信息记录**:
- `file.name`: 文件名
- `file.size`: 文件大小（字节）
- `file.type`: MIME 类型
- `file.lastModified`: 最后修改时间

**潜在异常点**:
1. ❌ **文件类型误判**: 某些编码的视频文件 MIME 类型识别错误
2. ❌ **文件损坏**: 用户选择已损坏的视频文件
3. ❌ **浏览器兼容性**: 旧版浏览器不支持 File API

**诊断建议**:
```javascript
// 添加详细日志
console.log('Selected file:', {
  name: file.name,
  size: file.size,
  type: file.type,
  lastModified: new Date(file.lastModified).toISOString()
});
```

---

#### 2.1.2 FormData 构造与发送

**技术实现**:
```typescript
const uploadVideo = async (file: File) => {
  const formData = new FormData();
  formData.append('video_file', file);
  
  // 如果是 YouTube URL 上传
  // formData.append('youtube_url', url);
  
  const response = await fetch(`${API_BASE_URL}/video/process`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${authToken}`,
      // 注意: 不要手动设置 Content-Type，浏览器会自动添加 boundary
    },
    body: formData,
  });
  
  return response.json();
};
```

**关键配置**:
- `Content-Type`: 自动设置为 `multipart/form-data; boundary=----WebKitFormBoundary...`
- `Content-Length`: 浏览器自动计算

**潜在异常点**:
1. ❌ **网络中断**: 上传过程中用户网络断开
2. ❌ **跨域问题**: CORS 配置不正确（虽然项目已配置 `allow_origins=["*"]`）
3. ❌ **Token 过期**: 认证 Token 在上传过程中失效

**诊断建议**:
```typescript
// 添加上传进度监控
const xhr = new XMLHttpRequest();
xhr.upload.addEventListener('progress', (e) => {
  if (e.lengthComputable) {
    const percent = (e.loaded / e.total) * 100;
    console.log(`Upload progress: ${percent.toFixed(2)}%`);
  }
});

xhr.upload.addEventListener('error', (e) => {
  console.error('Upload error:', e);
});
```

---

### 2.2 网络传输层

#### 2.2.1 反向代理 (Nginx)

**配置文件示例**: `/etc/nginx/sites-available/video-analysis`

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    # 关键配置1: 限制上传文件大小
    client_max_body_size 1G;  # 默认1MB，必须调整！
    
    # 关键配置2: 超时设置
    proxy_connect_timeout 600;
    proxy_send_timeout 600;
    proxy_read_timeout 600;
    send_timeout 600;
    
    # 关键配置3: 缓冲区设置
    client_body_buffer_size 10M;
    client_body_temp_path /var/nginx/temp;
    
    location /video/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # 禁用请求缓冲（流式上传）
        proxy_request_buffering off;
    }
}
```

**潜在异常点**:
1. ❌ **413 Request Entity Too Large**: `client_max_body_size` 不足
2. ❌ **504 Gateway Timeout**: `proxy_read_timeout` 不足
3. ❌ **磁盘空间不足**: 临时缓冲区 (`client_body_temp_path`) 所在分区满

**诊断命令**:
```bash
# 查看 Nginx 配置
nginx -T | grep -A 5 "client_max_body_size\|proxy_read_timeout"

# 查看 Nginx 错误日志
tail -100 /var/log/nginx/error.log | grep -i "client\|timeout"

# 检查临时目录空间
df -h /var/nginx/temp
```

---

#### 2.2.2 网络代理影响

**项目配置** (来自 `start_dev.sh` 等脚本):
```bash
export https_proxy=http://127.0.0.1:33210
export http_proxy=http://127.0.0.1:33210
export all_proxy=socks5://127.0.0.1:33211
```

**影响分析**:
- ✅ **优势**: 可以访问国际资源（YouTube）
- ❌ **风险**: 代理稳定性影响上传成功率

**潜在异常点**:
1. ❌ **代理服务不稳定**: 偶发性连接失败
2. ❌ **代理超时**: 大文件传输时代理中断
3. ❌ **代理认证失败**: 代理需要认证但未配置

**诊断建议**:
```bash
# 测试代理连通性
curl -x http://127.0.0.1:33210 -I https://www.google.com

# 测试直连 vs 代理速度
time curl http://localhost:8000/health
time curl -x http://127.0.0.1:33210 http://localhost:8000/health

# 查看代理日志（如 V2Ray/Clash）
tail -f /path/to/proxy/logs
```

---

### 2.3 后端接收阶段

#### 2.3.1 FastAPI 路由处理

**代码位置**: `backend/app/api/routes/video.py` (第19-134行)

**核心代码分析**:
```python
@router.post("/process")
async def process_video(
    youtube_url: Optional[str] = Form(None),
    video_file: Optional[UploadFile] = File(None),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    logger.info("收到视频处理请求")  # ✅ 日志点1
    
    # 【阶段1】认证和配额检查
    user_id = None
    if credentials and supabase_service.is_available():
        user = supabase_service.verify_token(credentials.credentials)
        if user:
            user_id = user.get("id")
            quota_ok = supabase_service.check_user_quota(str(user_id))
            if not quota_ok:
                raise HTTPException(status_code=429, ...)  # ❌ 异常点1
    
    # 【阶段2】输入验证
    if not youtube_url and not video_file:
        raise HTTPException(status_code=400, ...)  # ❌ 异常点2
    
    # 【阶段3】临时文件保存（关键！）
    video_path = None
    if video_file:
        temp_dir = tempfile.gettempdir()  # 通常是 /tmp
        video_path = os.path.join(temp_dir, video_file.filename)
        
        logger.info(f"📤 开始保存上传的视频文件: {video_file.filename}, "
                   f"大小: {video_file.size if hasattr(video_file, 'size') else 'unknown'}")
        # ✅ 日志点2
        
        with open(video_path, "wb") as buffer:
            content = await video_file.read()  # ⚠️ 内存读取，大文件风险
            buffer.write(content)
        
        logger.info(f"✅ 已保存上传的视频文件: {video_path}, "
                   f"文件大小: {os.path.getsize(video_path)} bytes")
        # ✅ 日志点3
    
    # 【阶段4】调用处理管道
    result = await pipeline.process_video_with_summary(
        youtube_url=youtube_url,
        video_file=video_path,
        user_id=user_id
    )
    # ✅ 日志点4 (在管道内部)
    
    # 【阶段5】清理临时文件
    if video_path and os.path.exists(video_path):
        os.remove(video_path)
        logger.debug(f"已清理临时文件: {video_path}")
    
    return result
```

**潜在异常点**:

| 编号 | 异常类型 | 触发条件 | 错误码 | 影响 |
|------|---------|---------|-------|------|
| ❌1 | 配额限制 | 用户超过月度限额 | 429 | 用户无法上传 |
| ❌2 | 输入验证失败 | 未提供文件或 URL | 400 | 请求被拒绝 |
| ❌3 | 磁盘写入失败 | `/tmp` 空间不足 | 500 | 文件保存失败 |
| ❌4 | 权限错误 | `/tmp` 无写权限 | 500 | 文件保存失败 |
| ❌5 | 内存溢出 | 大文件读取到内存 | 500 | 进程崩溃 |
| ❌6 | 文件名冲突 | 相同文件名并发上传 | 数据覆盖 | 数据错误 |

**诊断要点**:

```python
# 改进建议1: 流式写入避免内存问题
async def save_upload_file_streaming(upload_file: UploadFile, dest_path: str):
    """流式保存上传文件，避免大文件占用内存"""
    chunk_size = 1024 * 1024  # 1MB chunks
    with open(dest_path, 'wb') as f:
        while chunk := await upload_file.read(chunk_size):
            f.write(chunk)

# 改进建议2: 添加文件完整性检查
import hashlib
def verify_file_integrity(file_path: str) -> str:
    """计算文件 MD5 哈希"""
    md5 = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            md5.update(chunk)
    return md5.hexdigest()

# 改进建议3: 使用唯一文件名避免冲突
import uuid
def generate_temp_filename(original_filename: str) -> str:
    """生成唯一临时文件名"""
    suffix = Path(original_filename).suffix
    return f"{uuid.uuid4()}{suffix}"
```

---

#### 2.3.2 中间件日志记录

**代码位置**: `backend/app/main.py` (第21-37行)

**当前实现**:
```python
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    logger.info(f"🔵 收到请求: {request.method} {request.url.path}")
    logger.info(f"   客户端: {request.client.host if request.client else 'Unknown'}")
    logger.info(f"   Headers: {dict(request.headers)}")
    
    response = await call_next(request)
    
    process_time = time.time() - start_time
    logger.info(f"✅ 请求完成: {request.method} {request.url.path} - "
               f"状态码: {response.status_code} - 耗时: {process_time:.2f}s")
    
    return response
```

**增强建议**:
```python
@app.middleware("http")
async def enhanced_log_requests(request: Request, call_next):
    start_time = time.time()
    request_id = str(uuid.uuid4())[:8]  # 生成短请求ID
    
    # 记录请求信息
    log_data = {
        "request_id": request_id,
        "timestamp": datetime.utcnow().isoformat(),
        "method": request.method,
        "path": request.url.path,
        "client_ip": request.client.host if request.client else "Unknown",
        "user_agent": request.headers.get("user-agent", "Unknown"),
        "content_type": request.headers.get("content-type", ""),
        "content_length": request.headers.get("content-length", "0"),
    }
    
    logger.info(f"[{request_id}] 📥 收到请求: {json.dumps(log_data, ensure_ascii=False)}")
    
    try:
        response = await call_next(request)
        
        # 记录响应信息
        process_time = time.time() - start_time
        logger.info(f"[{request_id}] ✅ 请求完成: 状态={response.status_code}, "
                   f"耗时={process_time:.2f}s")
        
        # 添加请求ID到响应头（便于追踪）
        response.headers["X-Request-ID"] = request_id
        
        return response
        
    except Exception as e:
        process_time = time.time() - start_time
        logger.error(f"[{request_id}] ❌ 请求异常: {type(e).__name__} - {str(e)}, "
                    f"耗时={process_time:.2f}s")
        raise
```

---

### 2.4 管道处理阶段

#### 2.4.1 管道入口

**代码位置**: `backend/app/services/pipeline_service.py` (第306-500行)

**核心流程**:
```python
async def process_video_with_summary(
    self,
    video_file: Optional[str] = None,
    youtube_url: Optional[str] = None,
    user_id: Optional[str] = None,
    progress_callback: Optional[callable] = None
) -> Dict[str, Any]:
    
    video_id = None
    
    try:
        # ========== 步骤1: 视频处理和关键帧提取 ==========
        logger.info("🚀 步骤1: 开始视频处理")
        video_result = await self.video_service.process_video_dual_source(
            video_file=video_file,
            youtube_url=youtube_url
        )
        
        if video_result["status"] != "success":
            return video_result  # ❌ 异常点1
        
        video_id = video_result["video_id"]
        video_info = video_result["video_info"]
        keyframes = video_result["keyframes"]
        session_temp_dir = video_result["session_temp_dir"]
        
        # Supabase 集成: 创建视频记录
        if supabase_service.is_available() and user_id:
            video_data = {
                "video_id": video_id,
                "user_id": user_id,
                "title": video_info.title or "处理中...",
                "duration": video_info.duration,
                "source_type": "youtube" if youtube_url else "upload",
                "processing_status": "processing",
                "processing_progress": 0
            }
            supabase_service.create_video_record(video_data)
        
        # ========== 步骤2: 音频转录 ==========
        logger.info("🎤 步骤2: 开始音频转录")
        
        # 确定视频文件路径
        if youtube_url:
            session_path = Path(session_temp_dir)
            video_path = None
            for file_path in session_path.iterdir():
                if file_path.suffix.lower() in ['.mp4', '.avi', '.mov', '.mkv']:
                    video_path = str(file_path)
                    break
        else:
            video_path = video_file
        
        if not video_path:
            return {
                "status": "error",
                "error": "找不到视频文件用于音频提取",
                "video_id": video_id
            }  # ❌ 异常点2
        
        # 执行音频转录
        transcript_result = await self.speech_service.extract_and_transcribe_audio(
            video_path, video_id
        )
        
        if not transcript_result:
            logger.warning("音频转录失败，继续处理其他部分")  # ⚠️ 软失败
            transcript_result = self._create_empty_transcript()
        
        # Supabase 集成: 更新进度 (45%)
        if supabase_service.is_available() and user_id:
            supabase_service.update_video_status(video_id, "processing", 45)
        
        # ========== 步骤3: 视频总结 (Qwen3-VL) ==========
        logger.info("📊 步骤3: 开始视频总结")
        
        summary = await self.llm_service.generate_video_summary_v2(
            video_path=video_path,
            keyframes=keyframes,
            transcript=transcript_result,
            video_id=video_id
        )
        
        # Supabase 集成: 保存总结
        if summary and supabase_service.is_available():
            supabase_service.save_video_summary(video_id, summary)
        
        # ========== 步骤4: 生成统一 Metadata ==========
        metadata = await self._generate_unified_metadata(
            video_info, keyframes, transcript_result, video_metadata
        )
        
        # ========== 步骤5: 上传 Metadata 到 OSS ==========
        metadata_oss_url = await self.oss_service.upload_metadata(
            asdict(metadata), video_id
        )
        
        # ========== 步骤6: 清理临时文件 ==========
        self.video_service.cleanup_session(session_temp_dir)
        
        # Supabase 集成: 标记完成 (100%)
        if supabase_service.is_available() and user_id:
            supabase_service.update_video_status(video_id, "completed", 100)
        
        return {
            "status": "success",
            "video_id": video_id,
            "metadata": metadata,
            "summary": summary
        }
        
    except Exception as e:
        logger.exception(f"❌ 视频处理管道异常: {str(e)}")
        
        # Supabase 集成: 标记失败
        if video_id and supabase_service.is_available():
            supabase_service.update_video_status(video_id, "failed", -1)
        
        return {
            "status": "error",
            "error": str(e),
            "video_id": video_id
        }
```

**潜在异常点**:

| 步骤 | 异常类型 | 可能原因 | 影响等级 |
|------|---------|---------|---------|
| 步骤1 | 视频处理失败 | 文件格式不支持、损坏 | P1 |
| 步骤1 | 关键帧提取失败 | PySceneDetect 错误 | P2 |
| 步骤1 | OSS 上传失败 | 网络、凭证问题 | P1 |
| 步骤2 | 音频提取失败 | ffmpeg 错误、无音轨 | P2 (软失败) |
| 步骤2 | Paraformer 转录失败 | API 限流、格式问题 | P2 (软失败) |
| 步骤3 | Qwen3-VL 总结失败 | API 限流、超时 | P2 (软失败) |
| 全局 | Supabase 操作失败 | 数据库连接问题 | P3 (不影响核心) |

---

#### 2.4.2 视频服务处理

**代码位置**: `backend/app/services/video_service.py`

**双输入源处理逻辑**:
```python
async def process_video_dual_source(
    self, 
    video_file: Optional[str] = None,
    youtube_url: Optional[str] = None
) -> Dict[str, Any]:
    
    video_id = self._generate_video_id()
    session_temp_dir = self.temp_dir / f"session_{video_id}"
    session_temp_dir.mkdir(exist_ok=True)
    
    try:
        # 路径1: YouTube 下载
        if youtube_url:
            logger.info(f"从YouTube下载视频: {youtube_url}")
            video_result = await self._download_from_youtube(youtube_url, session_temp_dir)
            
            if video_result["status"] != "success":
                return video_result  # ❌ 下载失败
            
            video_path = video_result["video_path"]
            video_metadata = video_result["metadata"]
            source_type = "youtube"
            
        # 路径2: 用户上传
        else:
            logger.info(f"处理用户上传的视频: {video_file}")
            video_path = video_file
            video_metadata = await self._extract_video_metadata(video_path)
            source_type = "upload"
        
        # 【关键步骤1】提取视频基础信息
        video_info = await self._get_video_info(video_path)
        
        # 【关键步骤2】上传原始视频到 OSS
        oss_video_url = await oss_service.upload_video(video_path, video_id)
        if oss_video_url:
            video_info.oss_video_url = oss_video_url
        
        # 【关键步骤3】提取关键帧
        keyframes = await self._extract_keyframes_pyscenedetect(video_path, video_id)
        
        # 【关键步骤4】上传关键帧到 OSS
        for idx, keyframe in enumerate(keyframes):
            if keyframe.image_path and os.path.exists(keyframe.image_path):
                oss_url = await oss_service.upload_keyframe(
                    keyframe.image_path, video_id, idx
                )
                if oss_url:
                    keyframe.oss_image_url = oss_url
        
        return {
            "status": "success",
            "video_id": video_id,
            "video_info": video_info,
            "keyframes": keyframes,
            "video_metadata": video_metadata,
            "session_temp_dir": str(session_temp_dir)
        }
        
    except Exception as e:
        logger.exception(f"视频处理失败: {e}")
        return {
            "status": "error",
            "error": str(e),
            "video_id": video_id
        }
```

**关键帧提取细节** (PySceneDetect):
```python
async def _extract_keyframes_pyscenedetect(
    self, 
    video_path: str, 
    video_id: str
) -> List[KeyframeInfo]:
    
    from scenedetect import detect, AdaptiveDetector, split_video_ffmpeg
    
    try:
        # 使用 AdaptiveDetector 检测场景变化
        scene_list = detect(
            video_path, 
            AdaptiveDetector(adaptive_threshold=3.0)  # 阈值可调
        )
        
        if not scene_list:
            logger.warning("未检测到场景变化，提取首尾帧")
            scene_list = self._extract_first_last_frames(video_path)
        
        # 限制关键帧数量（避免过多）
        max_keyframes = 10
        if len(scene_list) > max_keyframes:
            step = len(scene_list) // max_keyframes
            scene_list = scene_list[::step]
        
        # 生成关键帧图片
        keyframes = []
        for idx, scene in enumerate(scene_list):
            timestamp = scene[0].get_seconds()  # 场景开始时间
            
            # 使用 ffmpeg 提取帧
            output_path = self.temp_dir / f"keyframe_{video_id}_{idx}.jpg"
            ffmpeg_cmd = [
                'ffmpeg', '-ss', str(timestamp), '-i', video_path,
                '-vframes', '1', '-q:v', '2', str(output_path)
            ]
            subprocess.run(ffmpeg_cmd, check=True, capture_output=True)
            
            keyframes.append(KeyframeInfo(
                frame_id=f"{video_id}_frame_{idx}",
                timestamp=timestamp,
                image_path=str(output_path),
                oss_image_url=None
            ))
        
        logger.info(f"提取了 {len(keyframes)} 个关键帧")
        return keyframes
        
    except Exception as e:
        logger.error(f"关键帧提取失败: {e}")
        return []
```

**潜在异常点**:
1. ❌ **PySceneDetect 安装问题**: 依赖 OpenCV，可能安装不完整
2. ❌ **ffmpeg 不可用**: 系统未安装 ffmpeg
3. ❌ **视频编码不支持**: 某些编码格式 PySceneDetect 无法解析
4. ❌ **内存不足**: 大视频文件场景检测占用内存过高

---

### 2.5 云存储阶段

#### 2.5.1 OSS 服务初始化

**代码位置**: `backend/app/services/oss_service.py` (第17-45行)

**初始化逻辑**:
```python
class AliyunOSSService:
    def __init__(self):
        # 从配置获取凭证
        self.access_key_id = settings.ALIYUN_ACCESS_KEY_ID
        self.access_key_secret = settings.ALIYUN_ACCESS_KEY_SECRET
        self.endpoint = settings.ALIYUN_OSS_ENDPOINT
        self.bucket_name = settings.ALIYUN_OSS_BUCKET
        
        # 检查配置完整性
        if not all([self.access_key_id, self.access_key_secret, 
                   self.endpoint, self.bucket_name]):
            logger.warning("阿里云OSS配置不完整")
            self.available = False
            return
        
        try:
            # 初始化 OSS 连接
            self.auth = oss2.Auth(self.access_key_id, self.access_key_secret)
            self.bucket = oss2.Bucket(self.auth, self.endpoint, self.bucket_name)
            self.available = True
            logger.info(f"阿里云OSS服务初始化成功，Bucket: {self.bucket_name}")
        except Exception as e:
            logger.error(f"阿里云OSS初始化失败: {e}")
            self.available = False
```

**环境变量配置** (`.env` 文件):
```bash
# 阿里云 OSS 配置
OSS_ACCESS_KEY_ID=LTAI5t...
OSS_ACCESS_KEY_SECRET=abc123...
OSS_BUCKET=your-bucket-name
OSS_ENDPOINT=oss-cn-beijing.aliyuncs.com
```

**潜在异常点**:
1. ❌ **凭证错误**: AccessKey 无效或过期
2. ❌ **Bucket 不存在**: 配置的 Bucket 名称错误
3. ❌ **区域不匹配**: Endpoint 和 Bucket 所在区域不一致
4. ❌ **网络不通**: 服务器无法访问 OSS Endpoint

**诊断命令**:
```bash
# 测试 OSS 连接
python3 << EOF
import oss2
auth = oss2.Auth('YOUR_ACCESS_KEY_ID', 'YOUR_ACCESS_KEY_SECRET')
bucket = oss2.Bucket(auth, 'oss-cn-beijing.aliyuncs.com', 'your-bucket')
try:
    bucket.get_bucket_info()
    print("✅ OSS 连接成功")
except Exception as e:
    print(f"❌ OSS 连接失败: {e}")
EOF
```

---

#### 2.5.2 文件上传流程

**视频上传代码** (第56-90行):
```python
async def upload_video(self, video_path: str, video_id: str) -> Optional[str]:
    if not self.is_available():
        logger.error("OSS服务不可用")
        return None
    
    try:
        filename = Path(video_path).name
        object_key = self._generate_object_key(video_id, "original", filename)
        # 例如: videos/20250115/uuid-xxx/original/video.mp4
        
        logger.info(f"开始上传视频文件: {video_path} -> {object_key}")
        
        # 上传文件
        with open(video_path, 'rb') as fileobj:
            self.bucket.put_object(object_key, fileobj)  # ⚠️ 简单上传，不适合超大文件
        
        # 生成访问 URL
        clean_endpoint = self.endpoint.replace('https://', '').replace('http://', '')
        url = f"https://{self.bucket_name}.{clean_endpoint}/{object_key}"
        logger.info(f"视频上传成功: {url}")
        
        return url
        
    except oss2.exceptions.RequestError as e:
        logger.error(f"OSS 请求错误: {e}")
        return None
    except oss2.exceptions.ServerError as e:
        logger.error(f"OSS 服务器错误: {e}")
        return None
    except Exception as e:
        logger.error(f"视频上传失败: {e}")
        return None
```

**潜在异常点**:
1. ❌ **网络超时**: 大文件上传时网络中断
2. ❌ **权限不足**: Bucket Policy 限制上传
3. ❌ **存储空间不足**: Bucket 已满
4. ❌ **并发限制**: OSS QPS 限制触发

**改进建议（分片上传）**:
```python
async def upload_large_file(self, file_path: str, object_key: str) -> Optional[str]:
    """
    分片上传大文件（支持断点续传）
    适用于 > 100MB 的文件
    """
    import oss2
    from oss2.models import PartInfo
    
    # 初始化分片上传
    upload_id = self.bucket.init_multipart_upload(object_key).upload_id
    parts = []
    
    # 分片大小（默认 10MB）
    part_size = 10 * 1024 * 1024
    file_size = os.path.getsize(file_path)
    part_count = (file_size + part_size - 1) // part_size
    
    logger.info(f"开始分片上传: {object_key}, 总大小={file_size}, 分片数={part_count}")
    
    try:
        with open(file_path, 'rb') as f:
            for part_number in range(1, part_count + 1):
                offset = (part_number - 1) * part_size
                size = min(part_size, file_size - offset)
                
                f.seek(offset)
                result = self.bucket.upload_part(
                    object_key, upload_id, part_number, f.read(size)
                )
                parts.append(PartInfo(part_number, result.etag))
                
                progress = (part_number / part_count) * 100
                logger.info(f"上传进度: {progress:.1f}%")
        
        # 完成分片上传
        self.bucket.complete_multipart_upload(object_key, upload_id, parts)
        
        clean_endpoint = self.endpoint.replace('https://', '').replace('http://', '')
        url = f"https://{self.bucket_name}.{clean_endpoint}/{object_key}"
        logger.info(f"分片上传成功: {url}")
        
        return url
        
    except Exception as e:
        # 取消上传
        self.bucket.abort_multipart_upload(object_key, upload_id)
        logger.error(f"分片上传失败: {e}")
        return None
```

---

### 2.6 数据库持久化

#### 2.6.1 Supabase 集成点

**代码位置**: 分布在 `pipeline_service.py` 多个位置

**集成点1 - 创建视频记录** (第350-366行):
```python
if supabase_service.is_available() and user_id:
    video_data = {
        "video_id": video_id,
        "user_id": user_id,
        "title": video_info.title or "处理中...",
        "duration": video_info.duration,
        "source_type": "youtube" if youtube_url else "upload",
        "original_url": youtube_url or "",
        "oss_video_url": video_info.oss_video_url or "",
        "processing_status": "processing",
        "processing_progress": 0
    }
    supabase_service.create_video_record(video_data)
```

**集成点2 - 更新处理进度**:
```python
# 不同阶段的进度更新
supabase_service.update_video_status(video_id, "processing", 15)   # 视频上传完成
supabase_service.update_video_status(video_id, "processing", 45)   # 关键帧完成
supabase_service.update_video_status(video_id, "processing", 70)   # 转录完成
supabase_service.update_video_status(video_id, "processing", 90)   # 总结完成
supabase_service.update_video_status(video_id, "completed", 100)   # 全部完成
```

**集成点3 - 保存元数据**:
```python
# 保存转录文本
supabase_service.save_transcript_segments(video_id, transcript_result.segments)

# 保存关键帧
supabase_service.save_keyframes(video_id, keyframes)

# 保存视频总结
supabase_service.save_video_summary(video_id, summary)
```

**潜在异常点**:
1. ❌ **数据库连接失败**: Supabase 服务不可用
2. ❌ **认证失败**: Service Key 无效
3. ❌ **数据验证失败**: 字段类型不匹配
4. ⚠️ **软失败**: Supabase 失败不影响核心功能（已设计为可选）

**容错设计**:
```python
# 所有 Supabase 操作都用 try-except 包裹
try:
    supabase_service.create_video_record(video_data)
    logger.info(f"✅ Supabase: 创建视频记录 {video_id}")
except Exception as e:
    logger.error(f"⚠️ Supabase: 创建视频记录失败: {e}")
    # 不抛出异常，继续处理
```

---

## 3. 异常点分析

### 3.1 异常点优先级矩阵

| 异常点 | 发生概率 | 影响范围 | 诊断难度 | 优先级 |
|-------|---------|---------|---------|-------|
| Nginx `client_max_body_size` 限制 | 中 | 高 | 低 | P1 |
| 临时目录磁盘空间不足 | 高 | 高 | 中 | P1 |
| OSS 网络连接失败 | 中 | 高 | 中 | P1 |
| 代理服务不稳定 | 高 | 中 | 高 | P1 |
| 文件并发冲突 | 低 | 中 | 中 | P2 |
| PySceneDetect 失败 | 低 | 低 | 中 | P2 |
| Paraformer API 限流 | 中 | 低 | 低 | P2 |
| Supabase 连接失败 | 低 | 低 | 低 | P3 |

### 3.2 异常链路追踪

**场景1: 偶发性上传中断**
```
用户上传 → Nginx 接收 → [❌ 网络波动] → FastAPI 接收不完整
→ 临时文件写入部分数据 → 管道处理读取损坏文件
→ ffmpeg 解析失败 → ❌ 返回 500 错误
```

**诊断路径**:
1. 检查 Nginx access.log 是否有完整请求记录
2. 检查 FastAPI 日志中的文件大小是否匹配
3. 检查临时文件实际大小 vs 预期大小
4. 检查代理日志是否有中断记录

---

**场景2: OSS 上传失败**
```
管道处理成功 → 临时文件完整 → 尝试 OSS 上传
→ [❌ OSS 网络超时] → 上传失败返回 None
→ 视频记录无 oss_video_url → 前端显示不完整
```

**诊断路径**:
1. 检查 OSS 服务日志中的错误类型
2. 测试服务器到 OSS Endpoint 的网络
3. 验证 AccessKey 权限
4. 检查 Bucket Policy 设置

---

**场景3: 磁盘空间不足**
```
大视频文件上传 → FastAPI 开始写入 /tmp
→ [❌ 磁盘空间不足] → 写入失败抛出 IOError
→ ❌ 返回 500 错误，临时文件不完整
```

**诊断路径**:
1. `df -h /tmp` 检查磁盘空间
2. `du -sh /tmp/aliyun_video_service/*` 检查残留文件
3. 设置磁盘空间监控告警
4. 配置定时清理脚本

---

## 4. 数据流转图

### 4.1 成功流程数据流

```
[用户文件: 150MB video.mp4]
        │
        ▼
[前端 FormData: multipart/form-data]
        │
        ▼
[Nginx 缓冲: /var/nginx/temp/xxx]
        │
        ▼
[FastAPI 接收: UploadFile 对象]
        │
        ▼
[临时文件: /tmp/video.mp4, 150MB]
        │
        ├─────────────────┬─────────────────┬──────────────────┐
        ▼                 ▼                 ▼                  ▼
[关键帧提取]      [音频提取]        [元数据提取]      [OSS 上传]
    │                 │                 │                  │
    ▼                 ▼                 ▼                  ▼
[10张 JPG]        [audio.wav]     [duration=600s]   [OSS URL]
    │                 │                                    │
    ▼                 ▼                                    ▼
[OSS 上传]       [Paraformer 转录]                 [Supabase 保存]
    │                 │                                    │
    ▼                 ▼                                    │
[10个 OSS URLs]  [transcript.json]                       │
    │                 │                                    │
    └─────────────────┴────────────────────────────────────┘
                      │
                      ▼
              [统一 Metadata JSON]
                      │
                      ▼
              [metadata.json → OSS]
                      │
                      ▼
              [返回给前端显示]
```

### 4.2 失败流程数据流

```
[用户文件: 500MB large_video.mp4]
        │
        ▼
[前端 FormData 上传]
        │
        ▼
[Nginx: client_max_body_size=1G] ✅ 通过
        │
        ▼
[FastAPI 接收: content = await video_file.read()]
        │
        ▼ [⚠️ 内存占用 500MB]
        │
[临时文件写入: /tmp 空间不足] ❌
        │
        ▼
[IOError: No space left on device]
        │
        ▼
[FastAPI 捕获异常]
        │
        ▼
[返回 500 错误给前端]
        │
        ▼
[前端显示: "视频处理失败"]
```

---

## 5. 总结与建议

### 5.1 关键风险点

1. **临时文件管理**:
   - 使用流式写入避免大文件占用内存
   - 定期清理 `/tmp` 残留文件
   - 监控磁盘空间使用率

2. **OSS 上传稳定性**:
   - 对大文件使用分片上传
   - 实现重试机制
   - 添加上传超时控制

3. **网络依赖**:
   - 监控代理服务稳定性
   - 实现优雅降级（代理失败时直连）
   - 添加网络质量监控

4. **并发处理**:
   - 使用唯一文件名避免冲突
   - 限制并发上传数量
   - 实现任务队列机制

### 5.2 改进建议

**短期优化** (1周内):
- [ ] 添加临时文件流式写入
- [ ] 添加磁盘空间检查
- [ ] 增强错误日志记录

**中期优化** (1月内):
- [ ] 实现 OSS 分片上传
- [ ] 添加上传进度回调
- [ ] 实现失败重试机制

**长期优化** (3月内):
- [ ] 引入任务队列（Celery/RQ）
- [ ] 实现视频预处理验证
- [ ] 添加全链路监控告警

---

**文档版本**: v1.0  
**最后更新**: 2025-01-15  
**维护者**: 系统架构组
