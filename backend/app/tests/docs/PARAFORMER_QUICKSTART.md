# Paraformer-v2 快速开始指南

## 为什么切换到 Paraformer？

你在使用 SenseVoice 时遇到的问题：

```text
❌ [00:00 - 00:00] . <|Speech|>andfor us,it'Svery important...
❌ 大量 <|Speech|> <|/Speech|> 标签
❌ 无意义的 .. . . . 。。。。。 占位符
❌ 时间戳不准确
❌ 没有说话人分离
```

Paraformer-v2 的输出：

```text
✅ [0.10s - 3.82s] 说话人0: Hello world, 这里是阿里巴巴语音实验室。
✅ 清晰的时间戳
✅ 自动说话人分离
✅ 结构化的 JSON 输出
✅ 无乱码和标签
```

---

## 快速开始（3 步）

### 步骤 1: 设置 API Key

```bash
# 优先使用专用的转录服务密钥
export TRANSCRIPT_SERVICE_API_KEY='your-dashscope-api-key'

# 或者使用 QWEN API Key
export QWEN_API_KEY='your-api-key'

# 或者使用通用的 DashScope Key
export DASHSCOPE_API_KEY='your-api-key'
```

**获取 API Key:**
1. 访问 [阿里云 DashScope](https://dashscope.console.aliyun.com/)
2. 登录并创建 API Key
3. 复制密钥

### 步骤 2: 运行测试

```bash
cd backend/app/tests
./run_paraformer_test.sh
```

### 步骤 3: 查看结果

测试会使用阿里云官方示例音频，你会看到：

```
================================================================================
✅ 转录成功!
================================================================================

📊 转录统计:
   - 段落数量: 1
   - 说话人数: 1
   - 置信度: 95.00%
   - 文本长度: XX 字符

📄 完整文本:
   Hello world, 这里是阿里巴巴语音实验室。

📝 详细段落:
--------------------------------------------------------------------------------

[段落 1]
  时间: 0.10s - 3.82s (时长: 3.72s)
  置信度: 95.00%
  文本: Hello world, 这里是阿里巴巴语音实验室。
```

---

## 在代码中使用

### 基础用法

```python
from app.services.paraformer_service import paraformer_service

# 转录音频（需要 OSS URL）
result = await paraformer_service.transcribe_file(
    audio_url="https://your-oss-bucket.com/audio.wav",
    language="auto",
    enable_diarization=True  # 启用说话人分离
)

if result:
    print(f"文本: {result.full_text}")
    print(f"说话人数: {result.speaker_count}")
```

### 完整示例

```python
async def transcribe_my_audio():
    """转录自己的音频"""
    
    # 1. 上传音频到 OSS
    from app.services.oss_service import oss_service
    
    audio_oss_url = await oss_service.upload_audio(
        file_path="path/to/your/audio.wav",
        video_id="my_video_001"
    )
    
    # 2. 转录音频
    result = await paraformer_service.transcribe_file(
        audio_url=audio_oss_url,
        enable_diarization=True
    )
    
    # 3. 处理结果
    if result:
        # 打印每个说话人的文本
        current_speaker = None
        for segment in result.segments:
            # 注意：speaker_id 在原始 JSON 中，这里简化处理
            print(f"[{segment.start_time:.2f}s] {segment.text}")
```

---

## 与 SenseVoice 对比

| 特性 | SenseVoice | Paraformer-v2 |
|------|-----------|---------------|
| **输出格式** | 带标签文本流 | ✅ 结构化 JSON |
| **时间戳** | 不明确 `[00:00]` | ✅ 毫秒级 `0.10s` |
| **说话人分离** | ❌ | ✅ speaker_id |
| **分句质量** | 较差 | ✅ 优秀 |
| **适用场景** | 多语言混合 | 中文/英文录音 |

---

## 配置选项

### 1. 说话人分离

```python
result = await paraformer_service.transcribe_file(
    audio_url=audio_url,
    enable_diarization=True  # True=开启, False=关闭
)
```

**何时开启：**
- ✅ 多人对话（会议、访谈）
- ✅ 播客、脱口秀
- ❌ 单人独白（不需要）

**限制：**
- 仅支持**单声道**音频
- 多声道会自动混音为单声道

### 2. 语言设置

```python
result = await paraformer_service.transcribe_file(
    audio_url=audio_url,
    language="auto"  # auto=自动检测, zh=中文, en=英文
)
```

---

## 音频要求

Paraformer 服务会**自动转换**音频为最佳格式：

- **采样率**: 16kHz
- **声道**: 单声道 (mono)
- **编码**: PCM 16-bit
- **格式**: WAV

**手动转换（可选）：**

```bash
ffmpeg -i input.mp4 \
    -vn \
    -acodec pcm_s16le \
    -ar 16000 \
    -ac 1 \
    -f wav \
    output.wav
```

---

## 故障排查

### ❌ API Key 错误

```
Error: HTTP 401 - Invalid API Key
```

**解决方案：**
1. 确认已设置环境变量
2. 检查密钥是否过期
3. 确认密钥有转录权限

```bash
# 检查环境变量
echo $TRANSCRIPT_SERVICE_API_KEY
```

### ❌ OSS URL 错误

```
Error: Paraformer 需要公共的 OSS URL
```

**解决方案：**
确保传入的是 HTTP(S) URL：

```python
# ❌ 错误
audio_url = "/local/path/audio.wav"

# ✅ 正确
audio_url = "https://your-bucket.oss-cn-beijing.aliyuncs.com/audio.wav"
```

### ❌ 没有 speaker_id

**可能原因：**
1. 未启用说话人分离
2. 音频是多声道

**解决方案：**

```python
# 确保启用说话人分离
result = await paraformer_service.transcribe_file(
    audio_url=audio_url,
    enable_diarization=True  # 必须 True
)
```

---

## 下一步

### 📚 阅读更多文档

- [Paraformer vs SenseVoice 详细对比](./PARAFORMER_VS_SENSEVOICE.md)
- [Paraformer 官方文档](https://help.aliyun.com/zh/model-studio/paraformer-recorded-speech-recognition-python-sdk)

### 🔧 集成到你的项目

```python
# 在 pipeline_service.py 中使用
from app.services.paraformer_service import paraformer_service

async def process_video(video_url: str):
    # ... 下载视频 ...
    # ... 上传到 OSS ...
    
    # 使用 Paraformer 转录
    result = await paraformer_service.extract_and_transcribe_audio(
        video_path=video_path,
        video_id=video_id,
        enable_diarization=True
    )
    
    # ... 使用 LLM 分析 ...
```

---

## 总结

### ✅ Paraformer 解决的问题

1. **无乱码** - 清晰的 JSON 输出，无 `<|Speech|>` 标签
2. **精确时间** - 毫秒级时间戳
3. **说话人分离** - 自动识别不同说话人
4. **更好分句** - 语义合理的句子切分

### 🚀 立即开始

```bash
# 1. 设置 API Key
export TRANSCRIPT_SERVICE_API_KEY='your-key'

# 2. 运行测试
cd backend/app/tests
./run_paraformer_test.sh

# 3. 查看结果 ✨
```

---

**需要帮助？** 查看 [PARAFORMER_VS_SENSEVOICE.md](./PARAFORMER_VS_SENSEVOICE.md) 获取更多信息。
