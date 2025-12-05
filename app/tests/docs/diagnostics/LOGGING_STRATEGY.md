# 视频上传处理日志策略设计

> **文档目标**: 提供完整的日志记录策略,帮助快速定位偶发性上传失败问题

---

## 📋 目录

- [1. 当前日志现状分析](#1-当前日志现状分析)
- [2. 日志策略设计原则](#2-日志策略设计原则)
- [3. 关键节点日志增强](#3-关键节点日志增强)
- [4. 结构化日志格式](#4-结构化日志格式)
- [5. 日志聚合与查询](#5-日志聚合与查询)
- [6. 实施计划](#6-实施计划)

---

## 1. 当前日志现状分析

### 1.1 日志覆盖情况

**统计结果** (基于代码扫描):
- 总日志记录点: **643 处**
- 分布文件: **30 个文件**
- 日志级别分布:
  - INFO: ~60%
  - WARNING: ~20%
  - ERROR: ~15%
  - DEBUG: ~5%

**主要日志文件**:
| 文件 | 日志点数 | 关键程度 |
|------|---------|---------|
| `pipeline_service.py` | ~80 | ⭐⭐⭐ |
| `video.py` (routes) | ~30 | ⭐⭐⭐ |
| `oss_service.py` | ~28 | ⭐⭐⭐ |
| `paraformer_service.py` | ~50 | ⭐⭐ |
| `main.py` (middleware) | ~10 | ⭐⭐ |

### 1.2 现有日志示例

**优秀实践** ✅:
```python
# backend/app/api/routes/video.py 第77-84行
logger.info(f"📤 开始保存上传的视频文件: {video_file.filename}, "
           f"大小: {video_file.size if hasattr(video_file, 'size') else 'unknown'}")

with open(video_path, "wb") as buffer:
    content = await video_file.read()
    buffer.write(content)

logger.info(f"✅ 已保存上传的视频文件: {video_path}, "
           f"文件大小: {os.path.getsize(video_path)} bytes")
```

**改进空间** ⚠️:
```python
# 当前: 缺少上下文信息
logger.error(f"视频上传失败: {e}")

# 改进: 添加完整上下文
logger.error(
    f"视频上传失败: video_id={video_id}, file={filename}, "
    f"size={file_size}, error_type={type(e).__name__}, error={e}",
    extra={
        "video_id": video_id,
        "filename": filename,
        "file_size": file_size,
        "error_type": type(e).__name__,
        "stack_trace": traceback.format_exc()
    }
)
```

### 1.3 日志缺失环节

**关键缺失**:
1. ❌ 缺少请求ID追踪 (无法关联同一请求的多条日志)
2. ❌ 缺少性能指标 (各阶段耗时不完整)
3. ❌ 缺少网络质量监控 (代理、OSS 连接状态)
4. ❌ 缺少资源使用监控 (磁盘、内存、CPU)

---

## 2. 日志策略设计原则

### 2.1 核心原则

#### 原则1: 可追踪性 (Traceability)
每个请求分配唯一 `request_id`,所有相关日志必须包含此 ID。

```python
import uuid

request_id = str(uuid.uuid4())[:8]  # 短 ID: e4f2a1b3

# 所有日志格式
logger.info(f"[{request_id}] 操作描述: 详细信息")
```

#### 原则2: 可观测性 (Observability)
关键指标必须量化,避免模糊描述。

```python
# ❌ 不好的日志
logger.info("文件很大,上传较慢")

# ✅ 好的日志
logger.info(f"文件大小: {file_size / 1024 / 1024:.2f}MB, "
           f"上传速度: {speed / 1024:.2f} KB/s, "
           f"预计耗时: {estimated_time:.1f}s")
```

#### 原则3: 可操作性 (Actionability)
错误日志必须包含诊断建议。

```python
# ❌ 不好的日志
logger.error("OSS上传失败")

# ✅ 好的日志
logger.error(
    "OSS上传失败: endpoint=oss-cn-beijing.aliyuncs.com, "
    "bucket=my-bucket, error=ConnectionTimeout, "
    "建议: 检查网络连接或增加超时设置"
)
```

#### 原则4: 性能友好 (Performance)
避免在热路径记录过多日志。

```python
# ❌ 不好的做法 (循环中记录详细日志)
for chunk in file_chunks:
    logger.debug(f"处理分片: {chunk.index}, 大小: {chunk.size}")  # 可能上千次

# ✅ 好的做法 (按百分比记录)
for i, chunk in enumerate(file_chunks):
    if i % (len(file_chunks) // 10) == 0:  # 每 10% 记录一次
        progress = (i / len(file_chunks)) * 100
        logger.info(f"处理进度: {progress:.0f}%")
```

### 2.2 日志级别规范

| 级别 | 用途 | 示例场景 | 是否需要告警 |
|------|------|---------|-------------|
| **DEBUG** | 开发调试,详细执行流程 | 函数入参、中间变量值 | ❌ |
| **INFO** | 正常业务流程 | 请求开始/完成、关键步骤 | ❌ |
| **WARNING** | 可恢复的异常,降级服务 | API 限流、Supabase 失败 | ⚠️ (可选) |
| **ERROR** | 影响功能的错误 | 上传失败、处理异常 | ✅ (必须) |
| **CRITICAL** | 系统级故障 | 服务无法启动、数据丢失 | ✅ (立即) |

**使用建议**:
```python
# DEBUG: 开发环境可见,生产环境关闭
logger.debug(f"[{request_id}] 函数 process_video 接收参数: video_file={video_file}")

# INFO: 正常业务流程,关键里程碑
logger.info(f"[{request_id}] ✅ 视频处理完成: video_id={video_id}, 耗时={duration}s")

# WARNING: 非致命问题,需要关注
logger.warning(f"[{request_id}] ⚠️ Paraformer转录失败,使用空转录: error={e}")

# ERROR: 影响用户功能
logger.error(f"[{request_id}] ❌ OSS上传失败: video_id={video_id}, error={e}")

# CRITICAL: 严重系统故障
logger.critical(f"OSS服务完全不可用,所有上传将失败: error={e}")
```

---

## 3. 关键节点日志增强

### 3.1 前端上传阶段

**日志位置**: 浏览器控制台 (Frontend)

```typescript
// frontend/src/services/video-upload.ts

const uploadVideo = async (file: File) => {
  const requestId = generateRequestId();  // 生成唯一 ID
  const startTime = Date.now();
  
  console.log(`[${requestId}] 📤 开始上传视频`, {
    request_id: requestId,
    filename: file.name,
    file_size: file.size,
    file_type: file.type,
    timestamp: new Date().toISOString()
  });
  
  try {
    const formData = new FormData();
    formData.append('video_file', file);
    formData.append('request_id', requestId);  // 传递到后端
    
    const response = await fetch(`${API_BASE_URL}/video/process`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'X-Request-ID': requestId  // 添加到请求头
      },
      body: formData
    });
    
    const duration = (Date.now() - startTime) / 1000;
    
    console.log(`[${requestId}] ✅ 上传完成`, {
      request_id: requestId,
      status: response.status,
      duration_seconds: duration,
      timestamp: new Date().toISOString()
    });
    
    return response.json();
    
  } catch (error) {
    const duration = (Date.now() - startTime) / 1000;
    
    console.error(`[${requestId}] ❌ 上传失败`, {
      request_id: requestId,
      error_type: error.name,
      error_message: error.message,
      duration_seconds: duration,
      timestamp: new Date().toISOString()
    });
    
    throw error;
  }
};
```

---

### 3.2 FastAPI 接收阶段

**日志位置**: `backend/app/api/routes/video.py`

**增强中间件** (`backend/app/main.py`):

```python
import uuid
import time
import json
from datetime import datetime
from fastapi import Request

@app.middleware("http")
async def enhanced_logging_middleware(request: Request, call_next):
    # 从请求头获取或生成 request_id
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
    start_time = time.time()
    
    # 记录请求开始
    request_log = {
        "request_id": request_id,
        "timestamp": datetime.utcnow().isoformat(),
        "method": request.method,
        "path": request.url.path,
        "query_params": dict(request.query_params),
        "client_ip": request.client.host if request.client else "Unknown",
        "user_agent": request.headers.get("user-agent", "Unknown"),
        "content_type": request.headers.get("content-type", ""),
        "content_length": request.headers.get("content-length", "0"),
        "host": request.headers.get("host", ""),
    }
    
    logger.info(f"[{request_id}] 📥 收到请求", extra=request_log)
    
    # 保存 request_id 到请求状态 (供路由使用)
    request.state.request_id = request_id
    
    try:
        response = await call_next(request)
        
        # 记录响应成功
        duration = time.time() - start_time
        response_log = {
            "request_id": request_id,
            "status_code": response.status_code,
            "duration_seconds": round(duration, 3),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        logger.info(f"[{request_id}] ✅ 请求完成", extra=response_log)
        
        # 添加 request_id 到响应头
        response.headers["X-Request-ID"] = request_id
        
        return response
        
    except Exception as e:
        duration = time.time() - start_time
        error_log = {
            "request_id": request_id,
            "error_type": type(e).__name__,
            "error_message": str(e),
            "duration_seconds": round(duration, 3),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        logger.error(f"[{request_id}] ❌ 请求异常", extra=error_log, exc_info=True)
        raise
```

**增强路由日志** (`backend/app/api/routes/video.py`):

```python
@router.post("/process")
async def process_video(
    request: Request,  # 添加 Request 参数
    youtube_url: Optional[str] = Form(None),
    video_file: Optional[UploadFile] = File(None),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    # 获取 request_id
    request_id = getattr(request.state, 'request_id', 'unknown')
    
    logger.info(f"[{request_id}] 🎬 开始视频处理流程")
    
    # 【阶段1】认证和配额检查
    user_id = None
    if credentials and supabase_service.is_available():
        try:
            user = supabase_service.verify_token(credentials.credentials)
            if user:
                user_id = user.get("id")
                logger.info(f"[{request_id}] 👤 用户认证成功: user_id={user_id}, email={user.get('email')}")
                
                quota_ok = supabase_service.check_user_quota(str(user_id))
                if not quota_ok:
                    logger.warning(f"[{request_id}] ⚠️ 用户配额不足: user_id={user_id}")
                    raise HTTPException(status_code=429, detail="已达到本月视频处理上限")
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"[{request_id}] ⚠️ Token验证失败,使用匿名模式: {e}")
    
    # 【阶段2】临时文件保存
    video_path = None
    if video_file:
        try:
            # 生成唯一文件名避免冲突
            temp_dir = tempfile.gettempdir()
            unique_filename = f"{request_id}_{video_file.filename}"
            video_path = os.path.join(temp_dir, unique_filename)
            
            file_size = 0
            if hasattr(video_file, 'size'):
                file_size = video_file.size
            
            logger.info(f"[{request_id}] 📥 开始保存上传文件", extra={
                "request_id": request_id,
                "filename": video_file.filename,
                "file_size": file_size,
                "temp_path": video_path,
                "content_type": video_file.content_type
            })
            
            save_start = time.time()
            
            # 流式写入
            chunk_size = 1024 * 1024  # 1MB
            bytes_written = 0
            with open(video_path, "wb") as buffer:
                while chunk := await video_file.read(chunk_size):
                    buffer.write(chunk)
                    bytes_written += len(chunk)
            
            save_duration = time.time() - save_start
            actual_size = os.path.getsize(video_path)
            write_speed = (actual_size / 1024 / 1024) / save_duration if save_duration > 0 else 0
            
            logger.info(f"[{request_id}] ✅ 文件保存成功", extra={
                "request_id": request_id,
                "temp_path": video_path,
                "file_size_bytes": actual_size,
                "file_size_mb": round(actual_size / 1024 / 1024, 2),
                "save_duration_seconds": round(save_duration, 2),
                "write_speed_mbps": round(write_speed, 2)
            })
            
            # 验证文件完整性
            if file_size > 0 and abs(actual_size - file_size) > 1024:  # 允许 1KB 误差
                logger.error(f"[{request_id}] ❌ 文件大小不匹配", extra={
                    "request_id": request_id,
                    "expected_size": file_size,
                    "actual_size": actual_size,
                    "difference": abs(actual_size - file_size)
                })
                raise HTTPException(status_code=500, detail="文件上传不完整")
                
        except Exception as e:
            logger.error(f"[{request_id}] ❌ 文件保存失败: {type(e).__name__} - {e}", 
                        exc_info=True)
            raise HTTPException(status_code=500, detail=f"文件保存失败: {str(e)}")
    
    # 【阶段3】调用处理管道
    try:
        logger.info(f"[{request_id}] 🚀 启动视频处理管道", extra={
            "request_id": request_id,
            "youtube_url": youtube_url,
            "video_file": video_path,
            "user_id": user_id
        })
        
        pipeline_start = time.time()
        
        result = await pipeline.process_video_with_summary(
            youtube_url=youtube_url,
            video_file=video_path,
            user_id=user_id,
            request_id=request_id  # 传递 request_id
        )
        
        pipeline_duration = time.time() - pipeline_start
        
        logger.info(f"[{request_id}] 📊 管道处理完成", extra={
            "request_id": request_id,
            "status": result.get('status'),
            "video_id": result.get('video_id'),
            "duration_seconds": round(pipeline_duration, 2)
        })
        
        # 递增配额使用
        if result.get("status") == "success" and supabase_service.is_available() and user_id:
            try:
                supabase_service.increment_video_usage(user_id)
                logger.info(f"[{request_id}] ✅ 配额使用已递增: user_id={user_id}")
            except Exception as e:
                logger.error(f"[{request_id}] ⚠️ 递增配额失败: {e}")
        
        return result
        
    finally:
        # 清理临时文件
        if video_path and os.path.exists(video_path):
            try:
                os.remove(video_path)
                logger.debug(f"[{request_id}] 🗑️ 已清理临时文件: {video_path}")
            except Exception as e:
                logger.warning(f"[{request_id}] ⚠️ 清理临时文件失败: {e}")
```

---

### 3.3 管道处理阶段

**日志位置**: `backend/app/services/pipeline_service.py`

```python
async def process_video_with_summary(
    self,
    video_file: Optional[str] = None,
    youtube_url: Optional[str] = None,
    user_id: Optional[str] = None,
    request_id: Optional[str] = None,  # 新增参数
    progress_callback: Optional[callable] = None
) -> Dict[str, Any]:
    
    request_id = request_id or str(uuid.uuid4())[:8]
    video_id = None
    
    # 记录管道开始
    pipeline_log = {
        "request_id": request_id,
        "timestamp": datetime.utcnow().isoformat(),
        "source_type": "youtube" if youtube_url else "upload",
        "user_id": user_id,
        "youtube_url": youtube_url,
        "video_file": video_file
    }
    logger.info(f"[{request_id}] 🎬 视频处理管道启动", extra=pipeline_log)
    
    try:
        # ========== 步骤1: 视频处理 ==========
        step1_start = time.time()
        logger.info(f"[{request_id}] 📹 步骤1/5: 开始视频处理和关键帧提取")
        
        video_result = await self.video_service.process_video_dual_source(
            video_file=video_file,
            youtube_url=youtube_url,
            request_id=request_id  # 传递 request_id
        )
        
        step1_duration = time.time() - step1_start
        
        if video_result["status"] != "success":
            logger.error(f"[{request_id}] ❌ 步骤1失败", extra={
                "request_id": request_id,
                "error": video_result.get("error"),
                "duration_seconds": round(step1_duration, 2)
            })
            return video_result
        
        video_id = video_result["video_id"]
        keyframes_count = len(video_result["keyframes"])
        
        logger.info(f"[{request_id}] ✅ 步骤1完成", extra={
            "request_id": request_id,
            "video_id": video_id,
            "keyframes_count": keyframes_count,
            "duration_seconds": round(step1_duration, 2)
        })
        
        # Supabase 集成 (带日志)
        if supabase_service.is_available() and user_id:
            try:
                video_data = {
                    "video_id": video_id,
                    "user_id": user_id,
                    # ... 其他字段
                }
                supabase_service.create_video_record(video_data)
                logger.info(f"[{request_id}] ✅ Supabase: 视频记录已创建", extra={
                    "request_id": request_id,
                    "video_id": video_id
                })
            except Exception as e:
                logger.error(f"[{request_id}] ⚠️ Supabase: 创建记录失败 (非致命): {e}")
        
        # ========== 步骤2: 音频转录 ==========
        step2_start = time.time()
        logger.info(f"[{request_id}] 🎤 步骤2/5: 开始音频提取和转录")
        
        transcript_result = await self.speech_service.extract_and_transcribe_audio(
            video_path, video_id, request_id=request_id
        )
        
        step2_duration = time.time() - step2_start
        
        if transcript_result:
            segments_count = len(transcript_result.segments) if transcript_result.segments else 0
            logger.info(f"[{request_id}] ✅ 步骤2完成", extra={
                "request_id": request_id,
                "video_id": video_id,
                "segments_count": segments_count,
                "duration_seconds": round(step2_duration, 2)
            })
        else:
            logger.warning(f"[{request_id}] ⚠️ 步骤2失败,使用空转录 (非致命)", extra={
                "request_id": request_id,
                "video_id": video_id,
                "duration_seconds": round(step2_duration, 2)
            })
            transcript_result = self._create_empty_transcript()
        
        # ========== 步骤3: 视频总结 ==========
        step3_start = time.time()
        logger.info(f"[{request_id}] 📊 步骤3/5: 开始视频总结生成")
        
        summary = await self.llm_service.generate_video_summary_v2(
            video_path=video_path,
            keyframes=keyframes,
            transcript=transcript_result,
            video_id=video_id,
            request_id=request_id
        )
        
        step3_duration = time.time() - step3_start
        
        logger.info(f"[{request_id}] ✅ 步骤3完成", extra={
            "request_id": request_id,
            "video_id": video_id,
            "summary_generated": bool(summary),
            "duration_seconds": round(step3_duration, 2)
        })
        
        # ========== 步骤4: Metadata 生成 ==========
        step4_start = time.time()
        logger.info(f"[{request_id}] 📝 步骤4/5: 生成统一 Metadata")
        
        metadata = await self._generate_unified_metadata(
            video_info, keyframes, transcript_result, video_metadata
        )
        
        step4_duration = time.time() - step4_start
        logger.info(f"[{request_id}] ✅ 步骤4完成: 耗时 {step4_duration:.2f}s")
        
        # ========== 步骤5: OSS 上传和清理 ==========
        step5_start = time.time()
        logger.info(f"[{request_id}] ☁️ 步骤5/5: 上传 Metadata 到 OSS")
        
        metadata_oss_url = await self.oss_service.upload_metadata(
            asdict(metadata), video_id, request_id=request_id
        )
        
        step5_duration = time.time() - step5_start
        logger.info(f"[{request_id}] ✅ 步骤5完成: 耗时 {step5_duration:.2f}s")
        
        # 清理临时文件
        self.video_service.cleanup_session(session_temp_dir)
        logger.info(f"[{request_id}] 🗑️ 临时文件已清理")
        
        # 更新 Supabase 状态为完成
        if supabase_service.is_available() and user_id:
            try:
                supabase_service.update_video_status(video_id, "completed", 100)
                logger.info(f"[{request_id}] ✅ Supabase: 状态已更新为完成")
            except Exception as e:
                logger.error(f"[{request_id}] ⚠️ Supabase: 更新状态失败: {e}")
        
        # 总结统计
        total_duration = step1_duration + step2_duration + step3_duration + step4_duration + step5_duration
        logger.info(f"[{request_id}] 🎉 视频处理管道完成", extra={
            "request_id": request_id,
            "video_id": video_id,
            "total_duration_seconds": round(total_duration, 2),
            "step1_video_processing": round(step1_duration, 2),
            "step2_transcription": round(step2_duration, 2),
            "step3_summary": round(step3_duration, 2),
            "step4_metadata": round(step4_duration, 2),
            "step5_oss_upload": round(step5_duration, 2)
        })
        
        return {
            "status": "success",
            "video_id": video_id,
            "metadata": metadata,
            "summary": summary,
            "performance": {
                "total_duration": round(total_duration, 2),
                "steps": {
                    "video_processing": round(step1_duration, 2),
                    "transcription": round(step2_duration, 2),
                    "summary": round(step3_duration, 2),
                    "metadata": round(step4_duration, 2),
                    "oss_upload": round(step5_duration, 2)
                }
            }
        }
        
    except Exception as e:
        logger.exception(f"[{request_id}] ❌ 管道处理异常", extra={
            "request_id": request_id,
            "video_id": video_id,
            "error_type": type(e).__name__,
            "error_message": str(e)
        })
        
        # 更新 Supabase 状态为失败
        if video_id and supabase_service.is_available():
            try:
                supabase_service.update_video_status(video_id, "failed", -1)
            except Exception as se:
                logger.error(f"[{request_id}] ⚠️ Supabase: 更新失败状态也失败: {se}")
        
        return {
            "status": "error",
            "error": str(e),
            "video_id": video_id
        }
```

---

### 3.4 OSS 上传阶段

**日志位置**: `backend/app/services/oss_service.py`

```python
async def upload_video(
    self, 
    video_path: str, 
    video_id: str,
    request_id: Optional[str] = None
) -> Optional[str]:
    
    request_id = request_id or "no-request-id"
    
    if not self.is_available():
        logger.error(f"[{request_id}] ❌ OSS服务不可用", extra={
            "request_id": request_id,
            "reason": "配置不完整或初始化失败"
        })
        return None
    
    try:
        filename = Path(video_path).name
        file_size = os.path.getsize(video_path)
        object_key = self._generate_object_key(video_id, "original", filename)
        
        logger.info(f"[{request_id}] ☁️ 开始OSS上传", extra={
            "request_id": request_id,
            "video_id": video_id,
            "local_path": video_path,
            "object_key": object_key,
            "file_size_bytes": file_size,
            "file_size_mb": round(file_size / 1024 / 1024, 2),
            "bucket": self.bucket_name,
            "endpoint": self.endpoint
        })
        
        upload_start = time.time()
        
        # 根据文件大小选择上传方式
        if file_size > 100 * 1024 * 1024:  # > 100MB 使用分片上传
            logger.info(f"[{request_id}] 📦 使用分片上传 (文件 > 100MB)")
            url = await self._upload_multipart(video_path, object_key, request_id)
        else:
            # 简单上传
            with open(video_path, 'rb') as fileobj:
                result = self.bucket.put_object(object_key, fileobj)
                
                # 检查上传结果
                if result.status != 200:
                    logger.error(f"[{request_id}] ❌ OSS上传返回异常状态码", extra={
                        "request_id": request_id,
                        "status_code": result.status,
                        "request_id_oss": result.request_id
                    })
                    return None
            
            clean_endpoint = self.endpoint.replace('https://', '').replace('http://', '')
            url = f"https://{self.bucket_name}.{clean_endpoint}/{object_key}"
        
        upload_duration = time.time() - upload_start
        upload_speed = (file_size / 1024 / 1024) / upload_duration if upload_duration > 0 else 0
        
        logger.info(f"[{request_id}] ✅ OSS上传成功", extra={
            "request_id": request_id,
            "video_id": video_id,
            "oss_url": url,
            "duration_seconds": round(upload_duration, 2),
            "upload_speed_mbps": round(upload_speed, 2)
        })
        
        return url
        
    except oss2.exceptions.RequestError as e:
        logger.error(f"[{request_id}] ❌ OSS请求错误 (网络问题)", extra={
            "request_id": request_id,
            "error_type": "RequestError",
            "error_code": e.code if hasattr(e, 'code') else 'unknown',
            "error_message": str(e),
            "建议": "检查网络连接或代理设置"
        }, exc_info=True)
        return None
        
    except oss2.exceptions.ServerError as e:
        logger.error(f"[{request_id}] ❌ OSS服务器错误", extra={
            "request_id": request_id,
            "error_type": "ServerError",
            "status_code": e.status,
            "error_message": str(e),
            "建议": "OSS服务异常,稍后重试"
        }, exc_info=True)
        return None
        
    except oss2.exceptions.NoSuchBucket as e:
        logger.error(f"[{request_id}] ❌ Bucket不存在", extra={
            "request_id": request_id,
            "bucket_name": self.bucket_name,
            "建议": "检查配置文件中的 ALIYUN_OSS_BUCKET"
        }, exc_info=True)
        return None
        
    except Exception as e:
        logger.error(f"[{request_id}] ❌ OSS上传失败 (未知错误)", extra={
            "request_id": request_id,
            "error_type": type(e).__name__,
            "error_message": str(e)
        }, exc_info=True)
        return None


async def _upload_multipart(
    self, 
    file_path: str, 
    object_key: str,
    request_id: str
) -> Optional[str]:
    """
    分片上传大文件
    """
    from oss2.models import PartInfo
    
    # 初始化分片上传
    upload_id = self.bucket.init_multipart_upload(object_key).upload_id
    parts = []
    
    part_size = 10 * 1024 * 1024  # 10MB
    file_size = os.path.getsize(file_path)
    part_count = (file_size + part_size - 1) // part_size
    
    logger.info(f"[{request_id}] 📦 分片上传初始化", extra={
        "request_id": request_id,
        "upload_id": upload_id,
        "total_size_mb": round(file_size / 1024 / 1024, 2),
        "part_size_mb": 10,
        "part_count": part_count
    })
    
    try:
        with open(file_path, 'rb') as f:
            for part_number in range(1, part_count + 1):
                offset = (part_number - 1) * part_size
                size = min(part_size, file_size - offset)
                
                f.seek(offset)
                part_start = time.time()
                
                result = self.bucket.upload_part(
                    object_key, upload_id, part_number, f.read(size)
                )
                parts.append(PartInfo(part_number, result.etag))
                
                part_duration = time.time() - part_start
                progress = (part_number / part_count) * 100
                
                # 每 10% 记录一次
                if part_number % max(1, part_count // 10) == 0:
                    logger.info(f"[{request_id}] 📦 分片上传进度: {progress:.0f}%", extra={
                        "request_id": request_id,
                        "part_number": part_number,
                        "part_count": part_count,
                        "progress_percent": round(progress, 1)
                    })
        
        # 完成分片上传
        self.bucket.complete_multipart_upload(object_key, upload_id, parts)
        
        clean_endpoint = self.endpoint.replace('https://', '').replace('http://', '')
        url = f"https://{self.bucket_name}.{clean_endpoint}/{object_key}"
        
        logger.info(f"[{request_id}] ✅ 分片上传完成", extra={
            "request_id": request_id,
            "oss_url": url
        })
        
        return url
        
    except Exception as e:
        # 取消上传
        try:
            self.bucket.abort_multipart_upload(object_key, upload_id)
            logger.warning(f"[{request_id}] 🗑️ 已取消分片上传")
        except:
            pass
        
        logger.error(f"[{request_id}] ❌ 分片上传失败", extra={
            "request_id": request_id,
            "upload_id": upload_id,
            "error": str(e)
        }, exc_info=True)
        return None
```

---

## 4. 结构化日志格式

### 4.1 JSON 日志格式

**配置文件**: `backend/app/core/logging.py`

```python
import logging
import json
import sys
from datetime import datetime
from pathlib import Path

class JSONFormatter(logging.Formatter):
    """
    JSON 格式日志输出
    """
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # 添加额外字段 (通过 logger.info(..., extra={...}) 传递)
        if hasattr(record, 'request_id'):
            log_data['request_id'] = record.request_id
        if hasattr(record, 'video_id'):
            log_data['video_id'] = record.video_id
        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id
        if hasattr(record, 'duration_seconds'):
            log_data['duration_seconds'] = record.duration_seconds
        
        # 合并所有 extra 字段
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'created', 'filename', 
                          'funcName', 'levelname', 'levelno', 'lineno', 
                          'module', 'msecs', 'message', 'pathname', 'process',
                          'processName', 'relativeCreated', 'thread', 'threadName']:
                if not key.startswith('_'):
                    log_data[key] = value
        
        # 添加异常信息
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)


def setup_logging(log_level: str = "INFO", log_file: str = None):
    """
    配置日志系统
    
    Args:
        log_level: 日志级别 (DEBUG/INFO/WARNING/ERROR/CRITICAL)
        log_file: 日志文件路径 (可选)
    """
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # 清除现有 handlers
    logger.handlers = []
    
    # 控制台输出 (彩色格式,易读)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # 文件输出 (JSON 格式,便于解析)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)  # 文件记录所有级别
        json_formatter = JSONFormatter()
        file_handler.setFormatter(json_formatter)
        logger.addHandler(file_handler)
    
    return logger


# 使用示例
logger = setup_logging(
    log_level="INFO",
    log_file="/var/log/video_analysis/app.log"
)
```

**日志输出示例**:

控制台输出 (彩色易读):
```
2025-01-15 14:30:45 - app.api.routes.video - INFO - [a3f2b1c4] 📥 开始保存上传文件
2025-01-15 14:30:48 - app.api.routes.video - INFO - [a3f2b1c4] ✅ 文件保存成功
2025-01-15 14:30:50 - app.services.oss_service - INFO - [a3f2b1c4] ☁️ 开始OSS上传
```

文件输出 (JSON 格式):
```json
{
  "timestamp": "2025-01-15T06:30:45.123Z",
  "level": "INFO",
  "logger": "app.api.routes.video",
  "message": "[a3f2b1c4] 📥 开始保存上传文件",
  "module": "video",
  "function": "process_video",
  "line": 85,
  "request_id": "a3f2b1c4",
  "filename": "test_video.mp4",
  "file_size": 52428800,
  "temp_path": "/tmp/a3f2b1c4_test_video.mp4",
  "content_type": "video/mp4"
}
```

---

## 5. 日志聚合与查询

### 5.1 日志文件组织

**目录结构**:
```
/var/log/video_analysis/
├── app.log                    # 主应用日志 (JSON 格式)
├── app-2025-01-15.log        # 按日期归档
├── error.log                  # 仅 ERROR 及以上级别
├── access.log                 # Nginx 访问日志
└── oss_upload.log            # OSS 上传专用日志
```

**日志轮转配置** (`/etc/logrotate.d/video-analysis`):
```bash
/var/log/video_analysis/*.log {
    daily                      # 每天轮转
    rotate 30                  # 保留 30 天
    compress                   # 压缩旧日志
    delaycompress             # 延迟一天压缩
    missingok                 # 文件不存在不报错
    notifempty                # 空文件不轮转
    create 0640 www-data www-data
    sharedscripts
    postrotate
        systemctl reload video-analysis
    endscript
}
```

### 5.2 快速查询命令

#### 查询特定 request_id 的所有日志:
```bash
# 查询单个请求的完整链路
grep "a3f2b1c4" /var/log/video_analysis/app.log | jq '.'

# 提取关键信息
grep "a3f2b1c4" /var/log/video_analysis/app.log | jq '{
  timestamp, level, message, video_id, duration_seconds
}'
```

#### 查询最近的上传失败:
```bash
# 最近 100 条 ERROR 日志
grep '"level":"ERROR"' /var/log/video_analysis/app.log | tail -100 | jq '.'

# 统计失败原因分布
grep '"level":"ERROR"' /var/log/video_analysis/app.log | \
  jq -r '.error_type' | sort | uniq -c | sort -rn
```

#### 查询 OSS 上传性能:
```bash
# 提取 OSS 上传耗时
grep "OSS上传成功" /var/log/video_analysis/app.log | \
  jq '{request_id, video_id, duration_seconds, upload_speed_mbps}'

# 计算平均上传速度
grep "OSS上传成功" /var/log/video_analysis/app.log | \
  jq -r '.upload_speed_mbps' | awk '{sum+=$1; count++} END {print sum/count " MB/s"}'
```

#### 查询慢请求 (> 60s):
```bash
grep '"duration_seconds"' /var/log/video_analysis/app.log | \
  jq 'select(.duration_seconds > 60)' | \
  jq '{request_id, message, duration_seconds}'
```

### 5.3 日志监控脚本

**实时监控上传失败** (`monitor_upload_failures.sh`):
```bash
#!/bin/bash

LOG_FILE="/var/log/video_analysis/app.log"
ALERT_THRESHOLD=5  # 5 分钟内失败 3 次告警

echo "开始监控上传失败 ($(date))"

tail -f "$LOG_FILE" | while read line; do
    # 检测 ERROR 级别日志
    if echo "$line" | jq -e 'select(.level == "ERROR")' > /dev/null 2>&1; then
        timestamp=$(echo "$line" | jq -r '.timestamp')
        request_id=$(echo "$line" | jq -r '.request_id // "unknown"')
        message=$(echo "$line" | jq -r '.message')
        error_type=$(echo "$line" | jq -r '.error_type // "unknown"')
        
        echo "🚨 检测到错误: [$request_id] $message (类型: $error_type)"
        
        # 发送告警 (可扩展到钉钉/邮件)
        # curl -X POST "https://oapi.dingtalk.com/robot/send?access_token=xxx" \
        #   -d "{\"msgtype\":\"text\",\"text\":{\"content\":\"上传失败告警\\n$message\"}}"
    fi
done
```

**运行监控**:
```bash
chmod +x monitor_upload_failures.sh
nohup ./monitor_upload_failures.sh > /var/log/video_analysis/monitor.log 2>&1 &
```

---

## 6. 实施计划

### 6.1 短期实施 (1 周内)

**Phase 1: 基础日志增强** (1-2 天)
- [ ] 添加 request_id 追踪 (中间件)
- [ ] 增强 video.py 路由日志
- [ ] 添加文件保存详细日志
- [ ] 添加 OSS 上传详细日志

**Phase 2: 结构化日志** (2-3 天)
- [ ] 配置 JSON 日志格式
- [ ] 设置日志文件轮转
- [ ] 编写日志查询脚本

**Phase 3: 监控部署** (1-2 天)
- [ ] 部署日志监控脚本
- [ ] 配置告警规则
- [ ] 验证日志采集完整性

### 6.2 中期实施 (1 个月内)

**Phase 4: 高级日志功能**
- [ ] 实现分布式追踪 (OpenTelemetry)
- [ ] 集成日志聚合平台 (ELK/Grafana Loki)
- [ ] 添加性能指标监控 (Prometheus)

### 6.3 验收标准

1. ✅ 每个上传请求可通过 request_id 追踪完整链路
2. ✅ 所有 ERROR 日志包含足够的上下文信息
3. ✅ 可快速查询特定 video_id/user_id 的所有日志
4. ✅ 日志查询响应时间 < 5s (近 7 天数据)
5. ✅ 偶发性失败可通过日志分析定位根因

---

**文档版本**: v1.0  
**最后更新**: 2025-01-15  
**维护者**: 系统架构组
