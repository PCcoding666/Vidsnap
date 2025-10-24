# Paraformer vs SenseVoice 对比指南

## 问题背景

在使用 SenseVoice 模型时，发现转录结果中包含大量格式问题：

### SenseVoice 输出的问题

```text
[00:00 - 00:00] . <|Speech|>andfor us,it'Svery important for codex to be everywhere you work.and that'Swhy we launched an IDextension.you can now have codex right in your code editor,whether it'Slike vs code cursor,winster or for many others<|/Speech|>.. . . . <|Speech|>whenyou win the ID y. 。 。 。 。 。 。. . . <|Speech|>start sending them over to codex.yeah,that'Sright.can you show us a little bit like what'Shappening behind the scenes now?so behind the scenes,when you ask codex to do something<|/Speech|>.. . . . . . . . . . . <|Speech|>...
```

**主要问题：**
1. ❌ 时间戳格式不清晰 `[00:00 - 00:00]`
2. ❌ 大量奇怪的占位符 `<|Speech|>`, `<|/Speech|>`
3. ❌ 无意义的符号 `.. . . .`, `。 。 。 。`
4. ❌ 分句不准确，整段文本混在一起
5. ❌ 缺少说话人分离信息

---

## 解决方案：切换到 Paraformer-v2

### Paraformer-v2 的优势

| 特性 | SenseVoice | Paraformer-v2 | 说明 |
|------|------------|---------------|------|
| **输出格式** | 带标签的文本流 | 结构化 JSON | Paraformer 输出更清晰 |
| **时间戳** | 不明确 | 毫秒级精确 | `begin_time`, `end_time` |
| **分句** | 较差 | 优秀 | 自动分句，更符合语义 |
| **说话人分离** | ❌ 不支持 | ✅ 支持 | `speaker_id` 字段 |
| **词级时间戳** | ❌ 不支持 | ✅ 支持 | `words` 数组 |
| **适用场景** | 多语言混合 | 中文录音 | Paraformer 专注中文 |

### Paraformer-v2 输出示例

```json
{
    "transcripts": [
        {
            "channel_id": 0,
            "text": "Hello world, 这里是阿里巴巴语音实验室。",
            "sentences": [
                {
                    "begin_time": 100,
                    "end_time": 3820,
                    "text": "Hello world, 这里是阿里巴巴语音实验室。",
                    "sentence_id": 1,
                    "speaker_id": 0,
                    "words": [
                        {
                            "begin_time": 100,
                            "end_time": 596,
                            "text": "Hello ",
                            "punctuation": ""
                        },
                        {
                            "begin_time": 596,
                            "end_time": 844,
                            "text": "world",
                            "punctuation": ", "
                        }
                    ]
                }
            ]
        }
    ]
}
```

**优势：**
- ✅ 清晰的 JSON 结构
- ✅ 精确的毫秒级时间戳
- ✅ 说话人 ID (`speaker_id`)
- ✅ 句子和词级别的信息
- ✅ 自动添加标点符号

---

## 使用指南

### 1. 导入 Paraformer 服务

```python
from app.services.paraformer_service import paraformer_service
```

### 2. 转录音频

```python
# 使用 OSS URL 转录
result = await paraformer_service.transcribe_file(
    audio_url="https://your-oss-url.com/audio.wav",
    language="auto",
    enable_diarization=True  # 启用说话人分离
)
```

### 3. 处理结果

```python
if result:
    print(f"完整文本: {result.full_text}")
    print(f"说话人数: {result.speaker_count}")
    print(f"置信度: {result.confidence:.2%}")
    
    # 遍历句子段落
    for segment in result.segments:
        print(f"[{segment.start_time:.2f}s - {segment.end_time:.2f}s]")
        print(f"  {segment.text}")
```

---

## 运行测试

### 快速测试

```bash
# 进入测试目录
cd backend/app/tests

# 添加执行权限
chmod +x run_paraformer_test.sh

# 运行测试
./run_paraformer_test.sh
```

### 环境变量

确保设置了 API Key：

```bash
export TRANSCRIPT_SERVICE_API_KEY='your-dashscope-api-key'
# 或
export QWEN_API_KEY='your-api-key'
# 或
export DASHSCOPE_API_KEY='your-api-key'
```

---

## Paraformer 配置选项

### 1. 说话人分离

```python
result = await paraformer_service.transcribe_file(
    audio_url=audio_url,
    enable_diarization=True  # 开启说话人分离
)
```

**注意：**
- 仅适用于**单声道**音频
- 多声道音频不支持说话人分离
- 结果中会包含 `speaker_id` 字段

### 2. 音频要求

使用 `paraformer_service` 时，音频会自动转换为：
- **采样率**: 16kHz
- **声道**: 单声道 (mono)
- **编码**: PCM 16-bit
- **格式**: WAV

---

## 迁移指南

### 从 SenseVoice 迁移到 Paraformer

**步骤 1：替换导入**

```python
# 旧代码
from app.services.speech_service import speech_service

# 新代码
from app.services.paraformer_service import paraformer_service
```

**步骤 2：更新调用**

```python
# 旧代码 (SenseVoice)
result = await speech_service.transcribe_file(
    audio_url=audio_url,
    language="zh"
)

# 新代码 (Paraformer)
result = await paraformer_service.transcribe_file(
    audio_url=audio_url,
    language="auto",
    enable_diarization=True  # 新增：说话人分离
)
```

**步骤 3：处理新字段**

```python
# Paraformer 新增字段
result.full_text        # 完整文本
result.speaker_count    # 说话人数量
```

---

## 最佳实践

### 1. 选择合适的模型

| 场景 | 推荐模型 | 原因 |
|------|---------|------|
| 中文会议录音 | **Paraformer-v2** | 说话人分离，准确分句 |
| 多语言混合 | SenseVoice | 支持多语言 |
| 英文播客 | Paraformer-v2 | 同样支持英文 |
| 实时字幕 | SenseVoice | 更快的响应 |

### 2. 优化音频质量

```python
# ffmpeg 转换命令 (Paraformer 优化)
ffmpeg -i input.mp4 \
    -vn \                      # 不处理视频
    -acodec pcm_s16le \        # PCM 16-bit
    -ar 16000 \                # 16kHz
    -ac 1 \                    # 单声道
    -f wav \                   # WAV 格式
    output.wav
```

### 3. 启用说话人分离

适用场景：
- ✅ 多人对话
- ✅ 会议录音
- ✅ 访谈节目
- ✅ 播客对话

不适用：
- ❌ 多声道音频
- ❌ 单人独白（不需要）

---

## 常见问题

### Q1: Paraformer 支持哪些语言？

**A:** 主要支持中文，同时也支持英文和中英混合。

### Q2: 如何判断说话人？

**A:** 启用 `enable_diarization=True` 后，每个句子会包含 `speaker_id`，相同 ID 表示同一个说话人。

### Q3: 时间戳精度如何？

**A:** Paraformer 提供**毫秒级**精度，比 SenseVoice 更准确。

### Q4: 为什么我的结果没有 speaker_id？

**A:** 可能原因：
1. 未启用说话人分离 (`enable_diarization=False`)
2. 音频是多声道（仅支持单声道）

---

## 参考资料

- [Paraformer Python SDK 官方文档](https://help.aliyun.com/zh/model-studio/paraformer-recorded-speech-recognition-python-sdk)
- [说话人分离功能说明](https://help.aliyun.com/zh/model-studio/paraformer-recorded-speech-recognition-python-sdk#spm=a2c4g.11186623.help-menu-2400256.d_2_6_3_2_1)

---

## 总结

### ✅ 使用 Paraformer-v2 的优势

1. **结构化输出** - 清晰的 JSON 格式，无乱码
2. **说话人分离** - 自动识别不同说话人
3. **精确时间戳** - 毫秒级别的时间信息
4. **优秀分句** - 语义合理的句子切分
5. **词级信息** - 提供每个词的时间和标点

### 🔄 何时仍使用 SenseVoice

- 需要多语言混合识别
- 需要识别小语种
- 实时性要求高

---

**更新日期**: 2025-10-24  
**文档版本**: v1.0
