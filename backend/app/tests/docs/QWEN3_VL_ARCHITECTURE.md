# Qwen3-VL-Flash 架构与数据流程文档

## 📋 目录

1. [架构概览](#架构概览)
2. [核心组件](#核心组件)
3. [完整数据流程](#完整数据流程)
4. [API 交互详情](#api-交互详情)
5. [数据模型](#数据模型)
6. [错误处理](#错误处理)

---

## 架构概览

### 系统架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户界面层                                  │
│              (Gradio / FastAPI REST API)                        │
└───────────────────────────┬─────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Pipeline Service                               │
│            (AliyunVideoProcessingPipeline)                       │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ Video Service│  │Speech Service│  │  OSS Service │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│                                                                  │
│                    ┌──────────────┐                             │
│                    │  LLM Service │ ◄─── Qwen3-VL-Flash        │
│                    └──────────────┘                             │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    外部服务层                                      │
│  ┌─────────┐  ┌──────────┐  ┌─────────┐  ┌─────────────────┐  │
│  │ YouTube │  │Aliyun OSS│  │SenseVoice│ │DashScope Qwen VL│  │
│  └─────────┘  └──────────┘  └─────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 核心组件

### 1. QwenVLService (`llm_service.py`)

**位置**: `/backend/app/services/llm_service.py`

**职责**:
- 管理与阿里云 DashScope Qwen3-VL-Flash 模型的所有交互
- 提供多模态输入处理（图片 URL + 文本上下文）
- 生成多粒度视频总结

**主要方法**:

```python
class QwenVLService:
    def __init__(self):
        """初始化 Qwen VL 服务，设置 API 密钥和模型配置"""
        
    def is_available(self) -> bool:
        """检查服务是否可用"""
        
    async def analyze_keyframe(self, image_url: str, context: str = "") -> Optional[str]:
        """分析单个关键帧，生成描述"""
        
    async def generate_video_summary(
        self,
        keyframes: List[KeyframeMetadata],
        transcription: TranscriptMetadata,
        video_id: str,
        granularity: str = "standard"
    ) -> Optional[VideoSummary]:
        """生成完整的视频总结"""
        
    async def _analyze_keyframes_batch(
        self,
        keyframes: List[KeyframeMetadata],
        transcription: TranscriptMetadata
    ) -> List[KeyframeDescription]:
        """批量分析关键帧（并发处理，最多3个同时）"""
        
    async def _generate_summaries_by_granularity(
        self,
        keyframe_descriptions: List[KeyframeDescription],
        transcription: TranscriptMetadata,
        granularity: str
    ) -> Dict[str, str]:
        """根据粒度生成不同层级的总结"""
        
    async def _generate_timeline_sections(
        self,
        keyframe_descriptions: List[KeyframeDescription],
        transcription: TranscriptMetadata
    ) -> List[SummarySection]:
        """生成基于时间线的总结段落"""
```

**配置参数**:
- **模型**: `qwen-vl-max`
- **Temperature**: `0.7`
- **Max Tokens**: `2000` (总结生成), `500` (关键帧描述)
- **并发限制**: 最多 3 个关键帧同时分析

---

### 2. AliyunVideoProcessingPipeline (`pipeline_service.py`)

**位置**: `/backend/app/services/pipeline_service.py`

**职责**:
- 协调整个视频处理流程
- 调用各个子服务（视频、语音、OSS、LLM）
- 管理数据流和状态

**与 LLM 服务的交互**:

```python
async def process_video_with_summary(
    self,
    video_file: Optional[str] = None,
    youtube_url: Optional[str] = None,
    granularity: str = "standard",
    progress_callback: Optional[callable] = None
) -> Dict[str, Any]:
    """
    完整流程:
    1. 视频下载/上传 + 关键帧提取
    2. 音频转录（SenseVoice）
    3. 生成统一 metadata
    4. 调用 LLM 生成视频总结 ◄── 这里调用 Qwen3-VL-Flash
    5. 上传 metadata 到 OSS
    6. 清理临时文件
    """
```

---

### 3. 数据模型 (`models/analysis.py`)

**位置**: `/backend/app/models/analysis.py`

**关键数据结构**:

#### KeyframeMetadata
```python
@dataclass
class KeyframeMetadata:
    frame_id: int                # 关键帧序号
    timestamp: float             # 时间戳（秒）
    oss_image_url: str          # OSS 图片 URL
    scene_description: str      # 场景描述
```

#### TranscriptMetadata
```python
@dataclass
class TranscriptMetadata:
    oss_audio_url: str                      # OSS 音频 URL
    language: str                           # 语言
    overall_confidence: float               # 整体置信度
    segments: List[TranscriptSegment]      # 转录段落列表
```

#### VideoSummary
```python
@dataclass
class VideoSummary:
    video_id: str                                  # 视频 ID
    brief_summary: str                             # 简要总结 (1-2句话)
    standard_summary: str                          # 标准总结 (100-200字)
    detailed_summary: Optional[str]                # 详细总结 (300-500字)
    sections: List[SummarySection]                 # 时间线段落
    keyframe_descriptions: List[KeyframeDescription]  # 关键帧描述
    language: str                                  # 总结语言
    generated_at: str                              # 生成时间
```

---

## 完整数据流程

### 端到端流程图

```
用户输入 (YouTube URL / 本地视频)
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ 1. 视频处理 (Video Service)                              │
│    - YouTube 下载 / 本地视频处理                          │
│    - 关键帧提取 (每10秒1帧)                               │
│    - 上传关键帧到 OSS                                     │
│                                                          │
│ 输出: keyframes = [                                      │
│   KeyframeMetadata(                                      │
│     frame_id=0,                                          │
│     timestamp=0.0,                                       │
│     oss_image_url="https://oss.../frame_000.jpg"        │
│   ), ...                                                 │
│ ]                                                        │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ 2. 音频转录 (Speech Service - SenseVoice)               │
│    - 提取音频                                            │
│    - 上传音频到 OSS                                       │
│    - 调用 SenseVoice API 转录                            │
│    - 获取转录结果（带时间戳）                              │
│                                                          │
│ 输出: transcription = TranscriptMetadata(               │
│   oss_audio_url="https://oss.../audio.wav",            │
│   language="zh-CN",                                     │
│   overall_confidence=0.90,                              │
│   segments=[                                            │
│     TranscriptSegment(                                  │
│       text="ever since he was a kid...",               │
│       start_time=4.14,                                  │
│       end_time=11.18,                                   │
│       confidence=0.95                                   │
│     ), ...                                              │
│   ]                                                     │
│ )                                                       │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ 3. LLM 视频总结生成 (LLM Service - Qwen3-VL-Flash)      │
│                                                          │
│ 3.1 批量分析关键帧                                        │
│     对每个关键帧:                                         │
│     ┌──────────────────────────────────────────┐       │
│     │ 输入:                                     │       │
│     │ - image_url: OSS 图片 URL                │       │
│     │ - context: 时间窗口内的转录文本 (±15秒)   │       │
│     │                                          │       │
│     │ API 调用 (MultiModalConversation.call):  │       │
│     │ {                                        │       │
│     │   "model": "qwen-vl-max",               │       │
│     │   "messages": [{                        │       │
│     │     "role": "user",                     │       │
│     │     "content": [                        │       │
│     │       {"image": "https://oss.../..."},  │       │
│     │       {"text": "请详细描述...上下文:..."} │       │
│     │     ]                                   │       │
│     │   }],                                   │       │
│     │   "temperature": 0.7,                   │       │
│     │   "max_length": 500                     │       │
│     │ }                                        │       │
│     │                                          │       │
│     │ 输出: description = "画面中..."          │       │
│     └──────────────────────────────────────────┘       │
│     并发处理（最多3个同时）                               │
│                                                          │
│ 3.2 生成多粒度总结                                        │
│     ┌──────────────────────────────────────────┐       │
│     │ Brief Summary (简要总结):                │       │
│     │ - 输入: 关键帧描述前500字 + 转录前500字   │       │
│     │ - Prompt: "用1-2句话简要总结..."         │       │
│     │ - Max Tokens: 200                        │       │
│     │ - 输出: "视频讲述了..."                  │       │
│     └──────────────────────────────────────────┘       │
│     ┌──────────────────────────────────────────┐       │
│     │ Standard Summary (标准总结):              │       │
│     │ - 输入: 所有关键帧描述 + 转录前1000字     │       │
│     │ - Prompt: "生成段落级别的标准总结..."    │       │
│     │ - Max Tokens: 500                        │       │
│     │ - 输出: "视频的主题是...主要内容..."     │       │
│     └──────────────────────────────────────────┘       │
│     ┌──────────────────────────────────────────┐       │
│     │ Detailed Summary (详细总结, 可选):        │       │
│     │ - 输入: 所有关键帧描述 + 转录前2000字     │       │
│     │ - Prompt: "生成详细的分段总结..."        │       │
│     │ - Max Tokens: 1000                       │       │
│     │ - 输出: "1.视频概述...2.主要内容..."     │       │
│     └──────────────────────────────────────────┘       │
│                                                          │
│ 3.3 生成时间线段落                                        │
│     根据关键帧时间戳划分段落，每个段落包含:                │
│     - start_time, end_time                               │
│     - title: "片段 1 (0.0s)"                            │
│     - content: 关键帧描述 + 该时段转录文本               │
│     - keyframe_ids: 关联的关键帧ID列表                   │
│                                                          │
│ 输出: video_summary = VideoSummary(...)                 │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ 4. 数据持久化 (OSS Service)                              │
│    - 上传 VideoSummary 到 OSS                            │
│    - 上传 VideoMetadata 到 OSS                           │
│                                                          │
│ 输出: OSS URLs                                           │
└─────────────────────────────────────────────────────────┘
    │
    ▼
返回给用户 (包含所有 metadata 和 summary)
```

---

## API 交互详情

### Qwen3-VL-Flash API 调用

**SDK**: `dashscope` (阿里云 DashScope SDK)

**认证方式**:
```python
# 环境变量优先级
QWEN_API_KEY (首选) → DASHSCOPE_API_KEY (备用)

# 设置方式
os.environ["DASHSCOPE_API_KEY"] = api_key
dashscope.api_key = api_key
```

**API 端点**: `MultiModalConversation.call()`

### 调用示例

#### 1. 关键帧描述生成

```python
# 输入
{
    "model": "qwen-vl-max",
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "image": "https://yt-summerizer-aliyun.oss-cn-hangzhou.aliyuncs.com/videos/20251018/xxx/keyframes/frame_000.jpg"
                },
                {
                    "text": "请详细描述这个视频关键帧中的内容，包括场景、人物、动作和关键元素。\n\n相关上下文：ever since he was a kid, he wanted to be a duckling racer..."
                }
            ]
        }
    ],
    "temperature": 0.7,
    "max_length": 500
}

# 输出
{
    "status_code": 200,
    "output": {
        "choices": [
            {
                "message": {
                    "content": "画面中一位男子正在整理西装袖口，表情专注..."
                }
            }
        ]
    }
}
```

#### 2. 视频总结生成

```python
# 简要总结 Prompt
"""
基于以下视频内容，用1-2句话简要总结视频的主要内容：

关键帧描述：
[0.0s] 画面中一位男子正在整理袖口...
[10.0s] 男子手持物品，表情专注...
...

转录文本：
ever since he was a kid, he wanted to be a duckling racer...

请用简洁的中文回答：
"""

# API 调用
{
    "model": "qwen-vl-max",
    "messages": [
        {
            "role": "user",
            "content": [
                {"text": "<上述 prompt>"}
            ]
        }
    ],
    "temperature": 0.7,
    "max_length": 200
}

# 输出
{
    "status_code": 200,
    "output": {
        "choices": [
            {
                "message": {
                    "content": "视频讲述了一位男子从小梦想成为鸭子赛车手，最终在16岁时成为瑞典最佳鸭子赛车手，并在18岁时赢得世界冠军的励志故事。"
                }
            }
        ]
    }
}
```

---

## 数据模型

### 输入数据结构

```python
# 从 Pipeline Service 传入 LLM Service 的数据

keyframes: List[KeyframeMetadata] = [
    KeyframeMetadata(
        frame_id=0,
        timestamp=0.0,
        oss_image_url="https://yt-summerizer-aliyun.oss-cn-hangzhou.aliyuncs.com/videos/20251018/xxx/keyframes/frame_000.jpg",
        scene_description=""
    ),
    # ... 通常 10 个关键帧
]

transcription: TranscriptMetadata = TranscriptMetadata(
    oss_audio_url="https://yt-summerizer-aliyun.oss-cn-hangzhou.aliyuncs.com/videos/20251018/xxx/audio/xxx_audio.wav",
    language="zh-CN",
    overall_confidence=0.90,
    segments=[
        TranscriptSegment(
            text="ever since he was a kid...",
            start_time=4.14,
            end_time=11.18,
            confidence=0.95
        ),
        # ... 多个段落
    ]
)
```

### 输出数据结构

```python
# LLM Service 返回的数据

video_summary: VideoSummary = VideoSummary(
    video_id="18ccd7bb-57ad-40f4-9f35-bde959a4ad95",
    
    # 多粒度总结
    brief_summary="视频讲述了一位男子从小梦想成为鸭子赛车手，最终成为世界冠军的励志故事。",
    standard_summary="视频的主题是关于一个从小就梦想成为鸭子赛车手的男孩的故事。他的第一个词是'嘎嘎'，第二个词是'冠军'。虽然他在家庭作业上不快，但天哪，这个男孩会骑鸭子。在16岁时，他成为瑞典最好的鸭子赛车手，到18岁时赢得了世界冠军...",
    detailed_summary=None,  # standard 模式下为 None
    
    # 关键帧描述列表
    keyframe_descriptions=[
        KeyframeDescription(
            frame_id=0,
            timestamp=0.0,
            description="画面中一位男子正在整理西装袖口，表情专注...",
            oss_image_url="https://..../frame_000.jpg",
            confidence=0.85
        ),
        # ... 10 个关键帧描述
    ],
    
    # 时间线段落
    sections=[
        SummarySection(
            start_time=0.0,
            end_time=15.0,
            title="片段 1 (0.0s)",
            content="画面中一位男子正在整理西装袖口...\n\n对话内容：ever since he was a kid...",
            keyframe_ids=[0]
        ),
        # ... 10 个段落
    ],
    
    language="zh-CN",
    generated_at="2025-10-18T17:54:53.519000"
)
```

---

## 错误处理

### 1. API 密钥问题

**问题**: API 密钥无效或过期
```python
# 错误日志
ERROR - API 调用失败: Invalid API-key provided.
```

**解决方案**:
1. 检查 `.env` 文件中的 `QWEN_API_KEY`
2. 验证密钥是否有效
3. 确认密钥有访问 `qwen-vl-max` 模型的权限

### 2. 模型名称问题

**当前配置**: `qwen-vl-max`

**可能的替代方案**:
- `qwen-vl-plus`
- `qwen-vl-v1`
- `qwenvl-plus`

### 3. 响应解析问题

**当前发现的问题**: 描述长度只有 1 字符

**可能原因**:
1. API 返回格式变更
2. 模型返回空白或特殊字符
3. 错误处理不当

**调试步骤**:
```python
# 已添加的日志
logger.info(f"描述内容: {description}")
logger.info(f"描述内容(repr): {repr(description)}")
```

### 4. 并发限制

**配置**: 最多 3 个关键帧同时分析

```python
max_concurrent = 3
semaphore = asyncio.Semaphore(max_concurrent)
```

**注意事项**:
- 避免超过 API 速率限制
- 平衡处理速度和 API 成本

---

## 性能指标

### 处理时间（测试结果）

- **总耗时**: ~3 分 50 秒（包含所有步骤）
- **关键帧分析**: ~10 秒 × 10 帧 = ~100 秒
- **总结生成**: ~13 秒

### 成本估算

**关键帧分析** (10 帧):
- 每帧 API 调用: 1 次
- Token 消耗: ~500 tokens/帧
- 总计: ~5,000 tokens

**总结生成** (3 次调用):
- Brief: ~200 tokens
- Standard: ~500 tokens  
- Timeline: 内部处理，不额外调用 API

**估计总 Token**: ~6,000 tokens/视频

---

## 配置文件

### 环境变量 (`.env`)

```bash
# Qwen API 密钥
QWEN_API_KEY=sk-ef05c88ce8eb4222b3cb9f013dbb0281

# 或者使用
DASHSCOPE_API_KEY=sk-ef05c88ce8eb4222b3cb9f013dbb0281
```

### 服务配置 (`llm_service.py`)

```python
# 模型配置
self.model = "qwen-vl-max"
self.temperature = 0.7
self.max_tokens = 2000

# 并发配置
max_concurrent = 3  # 最多同时分析 3 个关键帧

# 输入限制
context_length = 500  # 上下文文本限制
keyframe_max_length = 500  # 关键帧描述最大长度
```

---

## 总结

### 与 Qwen3-VL-Flash 交互的所有组件

1. **LLM Service** (`llm_service.py`) - 直接交互
2. **Pipeline Service** (`pipeline_service.py`) - 调用 LLM Service
3. **Data Models** (`models/analysis.py`) - 数据结构定义
4. **Test Suite** (`test_complete_pipeline.py`) - 集成测试

### 关键数据流

```
用户输入 
  → Video Service (关键帧提取)
  → Speech Service (音频转录)
  → LLM Service (视频总结) ◄── Qwen3-VL-Flash 交互点
  → OSS Service (持久化)
  → 返回结果
```

### 优化建议

1. **API 密钥验证**: 添加密钥有效性检查
2. **模型选择**: 支持配置不同的 Qwen VL 模型
3. **错误重试**: 实现 API 调用失败重试机制
4. **缓存机制**: 缓存已分析的关键帧描述
5. **成本监控**: 记录 API 调用次数和 Token 消耗

---

**文档版本**: 1.0  
**最后更新**: 2025-10-18  
**维护者**: AI Assistant
