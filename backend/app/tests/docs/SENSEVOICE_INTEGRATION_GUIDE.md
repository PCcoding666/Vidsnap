# 阿里云 SenseVoice 音频转录集成指南

## 📋 概述

本文档说明如何使用阿里云 DashScope SenseVoice 服务进行音频转录,包括:
- 完整替换 OpenAI Whisper
- YouTube 视频下载 → 音频提取 → OSS 上传 → SenseVoice 转录
- 端到端集成测试

## 🎯 主要变更

### 1. 核心服务文件

#### `app/services/speech_service.py`
- ✅ **完全替换** OpenAI Whisper 为阿里云 SenseVoice
- ✅ 使用 `dashscope.audio.asr.Transcription` API
- ✅ 支持异步转录 (`async_call` + `fetch` 轮询)
- ✅ 支持多语言 (中文、英文、韩文、日文等)
- ✅ 提取带时间戳的转录结果
- ✅ 音频必须先上传到 OSS (SenseVoice 需要公共 URL)

**关键方法**:
```python
# 转录音频 (使用 OSS URL)
async def transcribe_audio_with_timestamps(audio_oss_url: str, language: str = "auto")

# 从视频提取音频并转录
async def extract_and_transcribe_audio(video_path: str, video_id: str)

# 检查服务是否可用
def is_available() -> bool
```

#### `app/core/config.py`
- ✅ 添加 `DASHSCOPE_API_KEY` 配置
- ✅ 移除 `OPENAI_API_KEY` 配置
- ✅ 添加 `dashscope_available` 属性

#### `requirements.txt`
- ✅ 添加 `dashscope>=1.14.0`
- ✅ 移除 `openai>=1.0.0`

#### `.env.example`
- ✅ 添加 `QWEN_API_KEY` 示例
- ✅ 包含完整的 OSS 配置示例

### 2. 集成测试

#### `app/tests/test_video_to_transcription_pipeline.py`
完整的端到端测试,包括:

1. **test_dashscope_service_availability**: 
   - 验证 QWEN_API_KEY 是否设置
   - 验证 SenseVoice 服务可用性
   - 验证 OSS 服务可用性

2. **test_full_pipeline_youtube_to_transcription**:
   - 下载 YouTube 视频
   - 提取音频 (ffmpeg, WAV 格式, 16kHz, 单声道)
   - 上传音频到 OSS
   - 调用 SenseVoice 转录
   - 验证转录结果 (语言、置信度、文本长度)
   - 清理临时文件

3. **test_transcription_segments_format**:
   - 验证转录段落格式

4. **test_cleanup_after_processing**:
   - 验证临时文件清理

#### `run_transcription_test.sh`
自动化测试脚本:
- ✅ 从 .env 文件加载环境变量
- ✅ 检查环境变量 (QWEN_API_KEY, OSS 配置)
- ✅ 检查依赖 (dashscope, oss2, pytest)
- ✅ 运行 pytest 测试
- ✅ 生成详细的测试报告 (`TEST_TRANSCRIPTION_RESULTS.md`)
- ✅ 提取性能指标、转录示例、错误日志

## 🚀 使用指南

### 步骤 1: 安装依赖

```bash
cd /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend

# 安装更新的依赖
pip install -r requirements.txt

# 验证安装
python3 -c "import dashscope; print(f'dashscope version: {dashscope.__version__}')"
```

### 步骤 2: 配置环境变量

创建 `.env` 文件或设置环境变量:

```bash
# 阿里云 DashScope API Key (通义千问)
export QWEN_API_KEY="your_qwen_api_key_here"

# 阿里云 OSS 配置 (必需,SenseVoice 需要音频的公共 URL)
export ALIYUN_ACCESS_KEY_ID="your_access_key_id"
export ALIYUN_ACCESS_KEY_SECRET="your_access_key_secret"
export ALIYUN_OSS_ENDPOINT="oss-cn-hangzhou.aliyuncs.com"
export ALIYUN_OSS_BUCKET="your_bucket_name"
```

### 步骤 3: 运行测试

```bash
cd /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend

# 运行完整的集成测试
./run_transcription_test.sh
```

**或者直接使用 pytest**:

```bash
pytest app/tests/test_video_to_transcription_pipeline.py -v -s
```

### 步骤 4: 查看测试结果

测试完成后,查看生成的报告:

```bash
cat TEST_TRANSCRIPTION_RESULTS.md
```

测试报告包含:
- ✅ 总体状态和耗时
- ✅ 各阶段执行情况 (下载、提取、上传、转录)
- ✅ 转录结果示例 (前3个段落)
- ✅ 语言检测结果
- ✅ 转录准确性评估 (置信度)
- ✅ OSS URL 列表
- ✅ 错误日志 (如果有)

## 📊 预期输出示例

### 成功的测试输出

```
==========================================
YouTube 视频转录集成测试
使用阿里云 DashScope SenseVoice
==========================================

检查环境配置...
✓ DASHSCOPE_API_KEY 已设置
✓ 阿里云 OSS 配置已设置
✓ OSS Endpoint 和 Bucket 已设置

检查依赖...
✓ dashscope 包已安装
✓ oss2 包已安装
✓ pytest 包已安装

开始运行测试...

步骤 1/5: 下载 YouTube 视频
✓ 视频下载成功
  - 视频ID: 1PaoWKvcJP0
  - 视频时长: 120秒
  - 下载耗时: 15.23秒

步骤 2/5: 提取音频文件
✓ 音频提取成功
  - 音频大小: 2.34MB
  - 提取耗时: 3.45秒

步骤 3/5: 上传音频到 OSS
✓ 音频上传成功
  - OSS URL: https://your-bucket.oss-cn-hangzhou.aliyuncs.com/audio/...
  - 上传耗时: 2.12秒

步骤 4/5: 使用 SenseVoice 转录音频
✓ 音频转录成功
  - 检测语言: zh
  - 段落数量: 25
  - 总体置信度: 92.5%
  - 转录耗时: 45.67秒

步骤 5/5: 验证转录结果
  转录内容示例(前3段):
    [1] 0.0s - 3.5s
        文本: 大家好,欢迎来到我的频道
        置信度: 95.2%
    [2] 3.5s - 7.2s
        文本: 今天我们要讨论一个非常重要的话题
        置信度: 93.8%
    [3] 7.2s - 11.0s
        文本: 关于人工智能的未来发展
        置信度: 91.5%

✓ 完整流程测试通过!
总耗时: 66.47秒
```

## 🔧 技术细节

### SenseVoice API 调用流程

1. **创建异步任务**:
```python
transcribe_response = Transcription.async_call(
    model='sensevoice-v1',
    file_urls=[audio_oss_url],  # 必须是公共的 OSS URL
    language_hints=['zh', 'en']  # 多语言支持
)
task_id = transcribe_response.output.task_id
```

2. **轮询任务状态**:
```python
while elapsed_time < max_wait_time:
    await asyncio.sleep(poll_interval)
    transcribe_response = Transcription.fetch(task=task_id)
    
    if transcribe_response.output.task_status == "SUCCEEDED":
        return transcribe_response.output
    elif transcribe_response.output.task_status == "FAILED":
        return None
```

3. **解析转录结果**:
```python
results = transcription_output.results[0]
sentences = result_data.get("sentences", [])

for sentence in sentences:
    segment = TranscriptSegment(
        text=sentence.get("text"),
        start_time=sentence.get("begin_time") / 1000.0,
        end_time=sentence.get("end_time") / 1000.0,
        confidence=sentence.get("confidence")
    )
```

### 音频格式要求

使用 ffmpeg 提取音频,针对 SenseVoice 优化:

```bash
ffmpeg -i video.mp4 \
  -vn \                      # 不处理视频
  -acodec pcm_s16le \        # PCM 16-bit 编码
  -ar 16000 \                # 16kHz 采样率
  -ac 1 \                    # 单声道
  -f wav \                   # WAV 格式 (推荐)
  audio.wav
```

### 支持的语言

SenseVoice 支持以下语言:
- `zh`: 中文
- `en`: 英文
- `yue`: 粤语
- `ja`: 日语
- `ko`: 韩语
- `es`: 西班牙语
- `fr`: 法语
- `de`: 德语
- `ru`: 俄语

使用 `auto` 可自动检测语言。

## ⚠️ 注意事项

1. **OSS 必需**: SenseVoice 需要音频的公共 URL,因此必须配置 OSS 服务

2. **转录超时**: 默认最大等待时间为 180 秒,可根据音频长度调整

3. **API 配额**: 注意阿里云 DashScope 的 API 调用配额和费用

4. **音频质量**: 音频质量直接影响转录准确度,建议使用高质量音频

5. **网络要求**: 需要稳定的网络连接,用于下载视频、上传 OSS 和调用 API

## 🐛 故障排查

### 问题: QWEN_API_KEY 未设置

```bash
# 检查环境变量
echo $QWEN_API_KEY

# 如果为空,在 .env 文件中设置或导出
export QWEN_API_KEY="your_api_key"
```

### 问题: OSS 服务不可用

```bash
# 检查 OSS 配置
echo $ALIYUN_ACCESS_KEY_ID
echo $ALIYUN_ACCESS_KEY_SECRET
echo $ALIYUN_OSS_ENDPOINT
echo $ALIYUN_OSS_BUCKET

# 测试 OSS 连接
python3 -c "from app.services.oss_service import oss_service; print('OSS可用:', oss_service.is_available())"
```

### 问题: dashscope 包未安装

```bash
# 安装 dashscope
pip install dashscope>=1.14.0

# 验证安装
python3 -c "import dashscope; print(dashscope.__version__)"
```

### 问题: 转录超时

- 增加 `max_wait_time` 参数 (在 `transcribe_audio_with_timestamps` 方法中)
- 检查网络连接
- 尝试使用更短的音频文件测试

### 问题: 转录置信度低

- 检查音频质量 (采样率、比特率)
- 确认语言设置正确
- 尝试使用更清晰的音频源

## 📚 相关资源

- [阿里云 DashScope 文档](https://help.aliyun.com/zh/dashscope/)
- [SenseVoice API 文档](https://help.aliyun.com/zh/dashscope/developer-reference/api-sensevoice)
- [阿里云 OSS Python SDK](https://help.aliyun.com/zh/oss/developer-reference/python-installation)

## ✅ 验收清单

- [x] 完全移除 OpenAI Whisper 相关代码
- [x] 集成阿里云 DashScope SenseVoice
- [x] 使用异步编程 (async/await)
- [x] 支持多语言转录
- [x] 添加详细的日志输出
- [x] 支持转录结果的时间戳对齐
- [x] 处理 DashScope API 的速率限制
- [x] 音频自动上传到 OSS
- [x] 创建端到端集成测试
- [x] 生成自动化测试脚本
- [x] 更新所有相关配置文件
- [x] 创建使用文档

---

**集成完成日期**: 2025-10-17  
**版本**: v1.0.0 (SenseVoice)
