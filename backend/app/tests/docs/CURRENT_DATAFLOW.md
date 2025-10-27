# 当前视频上传处理完整数据流

> **项目版本**: v0.1.2  
> **生成时间**: 2025-10-27  
> **用途**: 理解现有数据流架构，为生产稳定版本提供参考

---

## 📊 完整数据流图

```
┌──────────────────────────┐
│    用户输入层            │
│  (Gradio Web 界面)       │
├──────────────────────────┤
│ ① YouTube URL 输入       │
│ ② 或本地视频文件上传     │
│ ③ 选择语言、粒度、帧数   │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ gradio_app.py            │
│ process_video_wrapper()  │
└──────────┬───────────────┘
           │
           ▼ 调用异步函数
┌──────────────────────────────────────────────────┐
│ pipeline_service.py                              │
│ AliyunVideoProcessingPipeline                    │
│ .process_video_with_summary()                    │
└──────────┬───────────────────────────────────────┘
           │
     ┌─────┴──────┬──────────┬──────────┐
     │            │          │          │
     ▼            ▼          ▼          ▼
  ┌────────────────────────────────────────────────────┐
  │ 步骤1: 视频处理 (video_service.py)                │
  │ process_video_dual_source()                        │
  ├────────────────────────────────────────────────────┤
  │ ① 双输入源判断:                                    │
  │   - YouTube: 用yt-dlp下载 → _download_from_youtube│
  │   - 本地: 直接使用上传的文件路径                   │
  │                                                    │
  │ ② 提取视频元数据:                                  │
  │   - ffprobe 获取时长、分辨率、编码等              │
  │   - 返回 VideoInfo 对象                           │
  │                                                    │
  │ ③ 上传原始视频到OSS:                              │
  │   - oss_service.upload_video()                     │
  │   - 获得 oss_video_url                            │
  │                                                    │
  │ ④ 提取关键帧 (最多10帧):                           │
  │   a) PySceneDetect 场景检测 (优先)                │
  │   b) FFmpeg 场景检测 (fallback)                   │
  │   c) 均匀采样 (最后fallback)                      │
  │   → extract_keyframes_scene_detection()           │
  │   → 为每帧调用 oss_service.upload_keyframe()      │
  │   → 返回 KeyframeInfo 列表                        │
  └────────┬─────────────────────────────────────────┘
           │ 返回: video_result
           │ {
           │   status, video_id, video_info,
           │   keyframes[], video_metadata,
           │   session_temp_dir
           │ }
           │
           ▼
  ┌────────────────────────────────────────────────────┐
  │ 步骤2: 音频转录 (paraformer_service.py)           │
  │ extract_and_transcribe_audio() - 异步并行执行      │
  ├────────────────────────────────────────────────────┤
  │ ① 从视频文件提取音频:                              │
  │   - ffmpeg -i video.mp4 -q:a 0 audio.mp3         │
  │   - 保存到临时文件                                │
  │                                                    │
  │ ② 音频转录 (Paraformer-v2):                       │
  │   - 模型下载(modelscope): damo/speech_paraformer  │
  │   - 支持中英文自动识别                            │
  │   - 输出: TranscriptSegment[] 包含:               │
  │     * text: 转录文本                              │
  │     * start_time, end_time: 时间戳                │
  │     * confidence: 置信度                          │
  │                                                    │
  │ ③ 上传音频到OSS:                                  │
  │   - oss_service.upload_audio()                     │
  │   - 获得 oss_audio_url                            │
  │                                                    │
  │ ④ 返回 TranscriptResult:                          │
  │   {                                               │
  │     segments[], language, confidence,             │
  │     audio_oss_url                                 │
  │   }                                               │
  └────────┬─────────────────────────────────────────┘
           │
           ▼
  ┌────────────────────────────────────────────────────┐
  │ 步骤3: 生成统一Metadata (pipeline_service.py)     │
  │ _generate_unified_metadata()                       │
  ├────────────────────────────────────────────────────┤
  │ 整合以上所有数据为 VideoMetadata 对象:            │
  │ {                                                  │
  │   video_id, title, duration,                      │
  │   oss_video_url,                                  │
  │   source_type (youtube/upload),                   │
  │   upload_time,                                    │
  │   processing_completed_time,                      │
  │   keyframes: [                                    │
  │     {                                             │
  │       frame_id, timestamp,                        │
  │       oss_image_url, scene_description            │
  │     }                                             │
  │   ],                                              │
  │   transcript: {                                   │
  │     oss_audio_url, language, overall_confidence,  │
  │     segments: [...]                               │
  │   },                                              │
  │   processing_status,                              │
  │   video_format, video_size, video_resolution      │
  │ }                                                  │
  └────────┬─────────────────────────────────────────┘
           │
           ▼
  ┌────────────────────────────────────────────────────┐
  │ 步骤4: 生成LLM视频总结 (llm_service.py) - 异步   │
  │ llm_service.generate_video_summary()               │
  ├────────────────────────────────────────────────────┤
  │ ① 收集输入数据:                                    │
  │   - 关键帧列表 (KeyframeMetadata[])               │
  │   - 转录片段 (TranscriptMetadata)                  │
  │   - video_id, granularity (brief/standard/detailed)
  │                                                    │
  │ ② 调用 Qwen3-VL-Flash 模型 (DashScope API):      │
  │   - 输入: 关键帧OSS URL + 转录文本                │
  │   - 处理: 多模态内容分析                          │
  │   - 输出: VideoSummary {                          │
  │       brief_summary (简要总结),                   │
  │       standard_summary (标准总结),                │
  │       detailed_summary (详细总结),                │
  │       keyframe_descriptions[]                     │
  │     }                                             │
  │                                                    │
  │ ③ 上传总结到OSS:                                  │
  │   - 生成 {video_id}_summary                       │
  │   - 获得 summary_oss_url                          │
  └────────┬─────────────────────────────────────────┘
           │
           ▼
  ┌────────────────────────────────────────────────────┐
  │ 步骤5: 上传Metadata到OSS (oss_service.py)        │
  │ oss_service.upload_metadata()                      │
  ├────────────────────────────────────────────────────┤
  │ ① 序列化 VideoMetadata 为 JSON                     │
  │ ② 生成 OSS 对象名: {video_id}/metadata.json       │
  │ ③ 上传到 OSS Bucket                              │
  │ ④ 返回 metadata_oss_url                           │
  └────────┬─────────────────────────────────────────┘
           │
           ▼
  ┌────────────────────────────────────────────────────┐
  │ 步骤6: 清理临时文件 (video_service.py)            │
  │ cleanup_session(session_temp_dir)                  │
  ├────────────────────────────────────────────────────┤
  │ ① 递归删除临时目录:                               │
  │   - {temp_dir}/session_{video_id}/                │
  │   - 删除：下载的视频、临时音频、关键帧等          │
  │   - 释放磁盘空间                                  │
  └────────┬─────────────────────────────────────────┘
           │ 返回完整结果
           ▼
  ┌───────────────────────────────────────────────────────┐
  │ 返回给 Gradio 界面:                                   │
  │ {                                                     │
  │   status: "success",                                │
  │   video_id: "uuid",                                 │
  │   metadata: VideoMetadata {...},                    │
  │   video_summary: VideoSummary {...},                │
  │   keyframes_count, transcript_segments_count,       │
  │   summary_generated: bool                           │
  │ }                                                     │
  └───────────────────────────────────────────────────────┘
           │
           ▼
  ┌───────────────────────────────────────────────────────┐
  │ Gradio 结果展示 (gradio_app.py)                       │
  ├───────────────────────────────────────────────────────┤
  │ ① 提取简要总结 → brief_summary Textbox             │
  │ ② 提取标准总结 → standard_summary Textbox           │
  │ ③ 提取详细总结 → detailed_summary Textbox           │
  │ ④ 转录文本     → transcript_text Textbox            │
  │ ⑤ 关键帧列表   → keyframes Gallery                  │
  │    (转换为 Gradio Gallery 格式: [(url, caption)])   │
  │ ⑥ 视频信息HTML → video_info_html                    │
  │ ⑦ 下载链接HTML → download_html                      │
  │    - 原视频URL、音频URL、元数据URL                 │
  │ ⑧ 状态消息     → status_msg                         │
  └───────────────────────────────────────────────────────┘
           │
           ▼
  ┌───────────────────────────────────────────────────────┐
  │ 用户界面展示完成                                       │
  │ - 用户可下载所有资源                                  │
  │ - 可启动聊天会话进行多轮问答                          │
  └───────────────────────────────────────────────────────┘
```

---

## 📁 关键文件与数据流对应关系

| 文件位置 | 函数/类 | 输入 | 输出 | 作用 |
|---------|--------|------|------|------|
| `gradio_app.py` | `process_video_wrapper()` | YouTube URL / 视频文件 | 展示结果 | 入口点，处理用户交互 |
| `pipeline_service.py` | `process_video_with_summary()` | 视频源 + 参数 | ProcessResult | 协调整个处理流程 |
| `video_service.py` | `process_video_dual_source()` | 视频源 | VideoInfo + 关键帧 | 处理视频，提取关键帧 |
| `video_service.py` | `extract_keyframes_scene_detection()` | 视频文件路径 | KeyframeInfo[] | 场景检测提取关键帧 |
| `paraformer_service.py` | `extract_and_transcribe_audio()` | 视频文件路径 | TranscriptResult | 音频转录 |
| `oss_service.py` | `upload_video/keyframe/audio()` | 本地文件路径 | OSS URL | 上传到云存储 |
| `llm_service.py` | `generate_video_summary()` | KeyframeMetadata + Transcript | VideoSummary | 生成AI总结 |

---

## 🔄 关键数据对象流转

### 1️⃣ **VideoInfo** (视频基本信息)
```python
VideoInfo:
  ├─ video_id: str (UUID)
  ├─ title: str
  ├─ duration: float (秒)
  ├─ oss_video_url: str (上传后的OSS地址)
  ├─ upload_time: datetime
  ├─ source_type: str ("youtube" | "upload")
  └─ original_url: Optional[str] (YouTube原始URL)
```

### 2️⃣ **KeyframeInfo** (单个关键帧)
```python
KeyframeInfo:
  ├─ frame_id: int (1-10)
  ├─ timestamp: float (秒)
  ├─ local_path: str (提取时的临时路径，后续删除)
  ├─ oss_image_url: str (上传后的OSS地址)
  └─ scene_description: str (场景描述)
```

### 3️⃣ **TranscriptSegment** (转录片段)
```python
TranscriptSegment:
  ├─ text: str (转录文本)
  ├─ start_time: float (秒)
  ├─ end_time: float (秒)
  └─ confidence: float (置信度 0-1)
```

### 4️⃣ **VideoMetadata** (统一元数据)
```python
VideoMetadata:
  ├─ video_id: str
  ├─ title: str
  ├─ duration: float
  ├─ oss_video_url: str
  ├─ source_type: str
  ├─ upload_time: str (ISO格式)
  ├─ processing_completed_time: str
  ├─ keyframes: [KeyframeMetadata]
  ├─ transcript: TranscriptMetadata
  ├─ processing_status: str
  ├─ video_format: str
  ├─ video_size: int (字节)
  ├─ video_resolution: str ("1920x1080")
  └─ metadata_oss_url: str (元数据本身的OSS地址)
```

### 5️⃣ **VideoSummary** (AI生成的总结)
```python
VideoSummary:
  ├─ brief_summary: str (简要总结)
  ├─ standard_summary: str (标准总结)
  ├─ detailed_summary: str (详细总结)
  └─ keyframe_descriptions: [str] (关键帧描述)
```

---

## ⚙️ 关键处理步骤详解

### 步骤1: 双源输入处理
```
输入来源判断:
  │
  ├─→ YouTube URL
  │   ├─ 调用 yt-dlp 下载视频
  │   ├─ 使用最新HTTP头和代理配置应对反爬
  │   ├─ 支持多客户端降级策略 (android, web)
  │   └─ 返回: video_path, metadata
  │
  └─→ 本地上传文件
      ├─ 验证文件格式 (.mp4, .avi, .mov, .mkv)
      ├─ 直接使用文件路径
      └─ 返回: video_path, 通过ffprobe提取metadata
```

### 步骤2: 关键帧提取三层策略
```
优先级 1: PySceneDetect 场景检测
  ├─ 使用 ContentDetector (阈值27.0)
  ├─ 自动降采样提升性能
  ├─ 精度高、性能好
  ├─ 需安装 scenedetect 库
  └─ 失败则降级

优先级 2: FFmpeg 场景检测
  ├─ select="gt(scene,0.3)" 过滤器
  ├─ 解析 pts_time 提取时间戳
  ├─ 无额外依赖
  └─ 失败则降级

优先级 3: 均匀采样
  ├─ 根据视频时长均匀分布
  ├─ 保证至少能提取关键帧
  └─ 作为最后保底方案

后处理:
  ├─ 过滤相距<2秒的时间戳
  ├─ 最多提取10帧
  └─ 每帧单独上传到OSS
```

### 步骤3: 音频转录流程
```
音频提取:
  ├─ ffmpeg -i video -q:a 0 audio.mp3
  ├─ 保存到临时目录
  └─ 支持各种视频格式

转录处理 (Paraformer-v2):
  ├─ 下载模型: damo/speech_paraformer-zh
  ├─ 支持中英文自动识别
  ├─ 输出分段转录 + 时间戳
  ├─ 计算置信度
  └─ 异步处理，不阻塞其他步骤

上传音频:
  ├─ 生成 {video_id}/audio.mp3
  ├─ 上传到OSS
  └─ 返回 oss_audio_url
```

### 步骤4: LLM 总结生成
```
输入准备:
  ├─ 关键帧: 转换OSS URL列表
  └─ 转录: 拼接所有片段文本

调用 Qwen3-VL-Flash:
  ├─ API: dashscope 多模态
  ├─ 并行处理: 关键帧 + 文本
  ├─ 输出多粒度总结:
  │  ├─ brief: 一句话概括 (50词左右)
  │  ├─ standard: 段落总结 (200-300词)
  │  └─ detailed: 详细总结 (500+词)
  └─ 附带关键帧描述

错误处理:
  ├─ API调用失败时打印警告
  ├─ 返回 None，不中断流程
  └─ Gradio展示为 "⚠️ LLM服务不可用"
```

### 步骤5: 数据存储
```
文件上传顺序:
  1. 原始视频 → {video_id}/video.mp4
  2. 关键帧 (10张) → {video_id}/keyframe_00_*.jpg
  3. 音频 → {video_id}/audio.mp3
  4. Metadata JSON → {video_id}/metadata.json
  5. Summary JSON → {video_id}_summary/summary.json

本地清理:
  ├─ session_temp_dir 完全删除
  ├─ 包括: 下载的视频、提取的音频、临时关键帧
  └─ 即使失败也尝试清理

性能考虑:
  ├─ 并行上传多个关键帧
  ├─ 异步转录不阻塞其他步骤
  └─ 总处理时间: 2-10分钟 (取决于视频长度和网络)
```

---

## 🌐 OSS 存储结构

```
bucket/
├── {video_id}/
│   ├── video.mp4                    (原始视频)
│   ├── audio.mp3                    (提取的音频)
│   ├── metadata.json                (统一元数据)
│   ├── keyframe_0_00.00s.jpg       (关键帧)
│   ├── keyframe_1_05.23s.jpg
│   ├── keyframe_2_10.45s.jpg
│   └── ...
│
└── {video_id}_summary/
    └── summary.json                 (LLM总结)
```

---

## ❌ 错误处理与容错机制

| 故障点 | 处理方式 | 结果 |
|-------|--------|------|
| YouTube 下载失败 | 返回错误，中断流程 | ❌ 处理失败 |
| 本地文件格式错误 | 验证时拒绝，错误提示 | ❌ 处理失败 |
| 视频元数据提取失败 | 返回默认值 (0时长等) | ⚠️ 降级处理 |
| 关键帧提取失败 | 三层 fallback 策略 | ✅ 至少提取帧 |
| 音频转录失败 | 返回空转录，继续处理 | ⚠️ 无转录内容 |
| OSS 上传失败 | 返回空URL，记录日志 | ⚠️ 资源不可下载 |
| LLM 总结失败 | 返回 None，显示提示 | ⚠️ 无AI总结 |
| 临时文件清理失败 | 记录警告，不中断 | ⚠️ 可能占用磁盘 |

---

## 🚀 生产环境稳定性检查清单

### 关键配置
- [ ] OSS 访问凭证正确配置
- [ ] Qwen/DashScope API Key 有效
- [ ] yt-dlp 版本最新 (≥2025.10.14)
- [ ] FFmpeg / FFprobe 已安装并可用
- [ ] 代理设置正确 (如需要)

### 性能考虑
- [ ] 临时目录磁盘空间充足 (单视频最多需要 2-3GB)
- [ ] 网络连接稳定 (重试机制: 10次)
- [ ] OSS 上传速度 (大视频可能需要 5-10 分钟)
- [ ] 并行处理限制 (同时不超过 5 个任务)

### 监控指标
- [ ] 处理成功率
- [ ] 平均处理时间
- [ ] OSS 存储成本
- [ ] API 调用次数和费用

### 日志记录
- [ ] 所有关键步骤已记录
- [ ] 错误信息详细且可追踪
- [ ] 进度回调实时更新

