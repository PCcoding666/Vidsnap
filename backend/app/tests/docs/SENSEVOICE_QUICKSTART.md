# 快速开始: SenseVoice 音频转录

## 🚀 一分钟快速启动

### 1. 安装依赖
```bash
cd /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend
pip install dashscope>=1.14.0 oss2>=2.18.0 pytest pytest-asyncio
```

### 2. 设置环境变量
```bash
# 必需
export QWEN_API_KEY="your_qwen_api_key"
export ALIYUN_ACCESS_KEY_ID="your_access_key_id"
export ALIYUN_ACCESS_KEY_SECRET="your_access_key_secret"
export ALIYUN_OSS_ENDPOINT="oss-cn-hangzhou.aliyuncs.com"
export ALIYUN_OSS_BUCKET="your_bucket_name"
```

### 3. 运行测试
```bash
./run_transcription_test.sh
```

## 📝 主要命令

### 运行完整测试
```bash
cd /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend
./run_transcription_test.sh
```

### 仅运行特定测试
```bash
# 测试服务可用性
pytest app/tests/test_video_to_transcription_pipeline.py::TestVideoToTranscriptionPipeline::test_dashscope_service_availability -v -s

# 测试完整流程
pytest app/tests/test_video_to_transcription_pipeline.py::TestVideoToTranscriptionPipeline::test_full_pipeline_youtube_to_transcription -v -s
```

### 查看测试报告
```bash
cat TEST_TRANSCRIPTION_RESULTS.md
```

### 查看测试日志
```bash
cat test_output.log
```

## 🔍 快速检查

### 检查环境配置
```bash
# 检查 DashScope API Key
python3 -c "import os; from dotenv import load_dotenv; load_dotenv('.env'); print('QWEN_API_KEY:', 'SET' if os.getenv('QWEN_API_KEY') else 'NOT SET')"

# 检查 OSS 配置
python3 -c "from app.core.config import settings; print('OSS可用:', settings.oss_available)"
```

### 检查服务可用性
```bash
# 检查 SenseVoice 服务
python3 -c "from app.services.speech_service import speech_service; print('SenseVoice可用:', speech_service.is_available())"

# 检查 OSS 服务
python3 -c "from app.services.oss_service import oss_service; print('OSS可用:', oss_service.is_available())"
```

## 💡 使用示例

### Python 代码示例

```python
import asyncio
from app.services.speech_service import speech_service
from app.services.oss_service import oss_service

async def transcribe_audio():
    # 1. 上传音频到 OSS
    audio_path = "/path/to/audio.wav"
    video_id = "test_video"
    audio_oss_url = await oss_service.upload_audio(audio_path, video_id)
    
    # 2. 转录音频
    result = await speech_service.transcribe_file(audio_oss_url, language="auto")
    
    # 3. 显示结果
    print(f"语言: {result.language}")
    print(f"置信度: {result.confidence:.2%}")
    for i, seg in enumerate(result.segments):
        print(f"[{i+1}] {seg.start_time:.1f}s - {seg.end_time:.1f}s: {seg.text}")

# 运行
asyncio.run(transcribe_audio())
```

### 从视频提取音频并转录

```python
import asyncio
from app.services.speech_service import speech_service

async def transcribe_video():
    video_path = "/path/to/video.mp4"
    video_id = "my_video"
    
    # 一步完成: 提取音频 + 上传OSS + 转录
    result = await speech_service.extract_and_transcribe_audio(video_path, video_id)
    
    if result:
        print(f"转录成功: {len(result.segments)} 个段落")
        print(f"OSS URL: {result.audio_oss_url}")

asyncio.run(transcribe_video())
```

## ⚠️ 常见问题

### Q: 测试失败,提示 QWEN_API_KEY 未设置?
**A**: 确保已在 .env 文件中设置或导出环境变量:
```bash
export QWEN_API_KEY="your_api_key"
```

### Q: OSS 服务不可用?
**A**: 检查所有 OSS 配置:
```bash
echo $ALIYUN_ACCESS_KEY_ID
echo $ALIYUN_ACCESS_KEY_SECRET
echo $ALIYUN_OSS_ENDPOINT
echo $ALIYUN_OSS_BUCKET
```

### Q: 转录超时?
**A**: 
- 转录可能需要较长时间,默认超时为 180 秒
- 检查网络连接
- 尝试使用更短的音频测试

### Q: 如何查看详细日志?
**A**: 测试时使用 `-s` 参数:
```bash
pytest app/tests/test_video_to_transcription_pipeline.py -v -s
```

## 📊 预期结果

成功运行后应该看到:
- ✅ 所有测试通过
- ✅ 生成 `TEST_TRANSCRIPTION_RESULTS.md` 报告
- ✅ 显示转录内容示例
- ✅ 显示性能指标 (下载、提取、上传、转录时间)

## 📁 重要文件

- `app/services/speech_service.py` - SenseVoice 服务实现
- `app/tests/test_video_to_transcription_pipeline.py` - 集成测试
- `run_transcription_test.sh` - 自动化测试脚本
- `TEST_TRANSCRIPTION_RESULTS.md` - 测试报告 (自动生成)
- `SENSEVOICE_INTEGRATION_GUIDE.md` - 完整集成指南
- `.env.example` - 环境变量示例

## 🎯 下一步

1. 查看完整文档: `SENSEVOICE_INTEGRATION_GUIDE.md`
2. 运行测试验证集成
3. 根据需要调整配置
4. 集成到您的应用中

---

**需要帮助?** 查看 `SENSEVOICE_INTEGRATION_GUIDE.md` 获取详细说明。
