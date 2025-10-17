# Transcript Service API Key Configuration Guide

## 📋 Overview

The audio transcription service now uses a dedicated environment variable `TRANSCRIPT_SERVICE_API_KEY` for better separation of concerns and API key management.

## 🔑 Environment Variable Priority

The speech service checks API keys in the following order:

1. **`TRANSCRIPT_SERVICE_API_KEY`** ✅ **Recommended**
   - Dedicated specifically for audio transcription services
   - Clear purpose and easier to manage
   - Best practice for production deployments

2. **`QWEN_API_KEY`** (Fallback)
   - Legacy variable name
   - Still supported for backward compatibility
   
3. **`DASHSCOPE_API_KEY`** (Fallback)
   - Direct DashScope SDK variable
   - Lowest priority

## ⚙️ Configuration Steps

### Step 1: Add to `.env` File

Edit your `.env` file:
```bash
cd /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend
nano .env
```

Add the following line:
```bash
# Audio Transcription Service API Key (Alibaba Cloud DashScope SenseVoice)
TRANSCRIPT_SERVICE_API_KEY=sk-your-actual-api-key-here
```

### Step 2: Verify Configuration

Test that the API key is loaded correctly:
```bash
python -c "
from dotenv import load_dotenv
from pathlib import Path
import os

load_dotenv(Path('.env'))

transcript_key = os.getenv('TRANSCRIPT_SERVICE_API_KEY')
qwen_key = os.getenv('QWEN_API_KEY')

print(f'TRANSCRIPT_SERVICE_API_KEY: {\"SET (\" + transcript_key[:10] + \"...)\" if transcript_key else \"NOT SET\"}')
print(f'QWEN_API_KEY: {\"SET (\" + qwen_key[:10] + \"...)\" if qwen_key else \"NOT SET\"}')
print()
if transcript_key:
    print('✅ Using TRANSCRIPT_SERVICE_API_KEY (recommended)')
elif qwen_key:
    print('⚠️  Using QWEN_API_KEY (fallback)')
else:
    print('❌ No API key found!')
"
```

Expected output:
```
TRANSCRIPT_SERVICE_API_KEY: SET (sk-1234567...)
QWEN_API_KEY: NOT SET

✅ Using TRANSCRIPT_SERVICE_API_KEY (recommended)
```

### Step 3: Test the Service

Run the test suite:
```bash
./run_transcription_test.sh
```

Or test manually:
```bash
pytest app/tests/test_video_to_transcription_pipeline.py::TestVideoToTranscriptionPipeline::test_dashscope_service_availability -v -s
```

## 📊 Example `.env` Configuration

### Recommended Configuration (New Project)
```bash
# Audio Transcription Service
TRANSCRIPT_SERVICE_API_KEY=sk-your-dashscope-api-key

# Alibaba Cloud OSS Configuration
ALIYUN_ACCESS_KEY_ID=your-access-key-id
ALIYUN_ACCESS_KEY_SECRET=your-access-key-secret
ALIYUN_OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
ALIYUN_OSS_BUCKET=your-bucket-name
```

### Legacy Configuration (Backward Compatible)
```bash
# This still works but TRANSCRIPT_SERVICE_API_KEY is preferred
QWEN_API_KEY=sk-your-dashscope-api-key

# Alibaba Cloud OSS Configuration
ALIYUN_ACCESS_KEY_ID=your-access-key-id
ALIYUN_ACCESS_KEY_SECRET=your-access-key-secret
ALIYUN_OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
ALIYUN_OSS_BUCKET=your-bucket-name
```

## 🔍 How It Works

### In `speech_service.py`

```python
def __init__(self):
    """Initialize Alibaba Cloud SenseVoice Speech Service"""
    # Priority order for API key
    self.api_key = (
        os.getenv("TRANSCRIPT_SERVICE_API_KEY") or  # 1st priority
        os.getenv("QWEN_API_KEY") or                # 2nd priority
        os.getenv("DASHSCOPE_API_KEY")              # 3rd priority
    )
    
    if self.api_key:
        os.environ["DASHSCOPE_API_KEY"] = self.api_key
        dashscope.api_key = self.api_key
        logger.info("Using audio transcription service API key")
```

### In Test Scripts

The test scripts (`run_transcription_test.sh`) now check for both:
```bash
if [ -n "$TRANSCRIPT_SERVICE_API_KEY" ]; then
    echo "✓ TRANSCRIPT_SERVICE_API_KEY set (dedicated for audio transcription)"
elif [ -n "$QWEN_API_KEY" ]; then
    echo "✓ QWEN_API_KEY set (fallback)"
else
    echo "❌ No API key found!"
    exit 1
fi
```

## ✅ Benefits of Using TRANSCRIPT_SERVICE_API_KEY

1. **Clear Purpose**: Immediately indicates this key is for transcription
2. **Better Security**: Separate keys for different services
3. **Easier Rotation**: Can rotate transcription keys without affecting other services
4. **Team Clarity**: New developers understand what this key is for
5. **Production Ready**: Best practice for microservices architecture

## 🔄 Migration Guide

### From QWEN_API_KEY to TRANSCRIPT_SERVICE_API_KEY

If you're currently using `QWEN_API_KEY`:

1. **No immediate action required** - it still works as a fallback
2. **Recommended**: Add `TRANSCRIPT_SERVICE_API_KEY` to your `.env` file
3. The service will automatically prefer the new variable
4. You can remove `QWEN_API_KEY` later if it's only used for transcription

Steps:
```bash
# 1. Copy your existing key
grep "^QWEN_API_KEY" .env

# 2. Add new variable with the same key
echo "TRANSCRIPT_SERVICE_API_KEY=<your-key-here>" >> .env

# 3. Test (optional but recommended)
./run_transcription_test.sh

# 4. Remove old variable (optional)
# You can keep QWEN_API_KEY as backup or remove it
```

## 🐛 Troubleshooting

### Issue: "No API key found"
**Solution**: Ensure you've set `TRANSCRIPT_SERVICE_API_KEY` in your `.env` file

### Issue: "401 Invalid API-key"
**Solution**: 
1. Verify your API key is correct
2. Check it has SenseVoice permissions in DashScope console
3. Ensure the key hasn't expired

### Issue: Service uses QWEN_API_KEY instead of TRANSCRIPT_SERVICE_API_KEY
**Solution**:
1. Check if `TRANSCRIPT_SERVICE_API_KEY` is actually set in `.env`
2. Ensure `.env` file is being loaded (check for `.env` in backend directory)
3. Restart your application/test to reload environment variables

## 📚 Related Documentation

- [API_KEY_ISSUE_RESOLUTION.md](./API_KEY_ISSUE_RESOLUTION.md) - Detailed troubleshooting guide
- [FIX_SUMMARY.md](./FIX_SUMMARY.md) - Recent fixes and changes
- [DashScope Console](https://dashscope.console.aliyun.com/) - Get your API key

---

**Last Updated**: 2025-10-17
**Status**: ✅ Active
