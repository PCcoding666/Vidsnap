# DashScope API Key Issue Resolution Guide

## 🔍 Issue Summary

**Error**: `HTTP 401 - Invalid API-key provided`

**Location**: SenseVoice transcription API call in `speech_service.py`

**Root Cause**: The audio transcription API key is invalid, expired, or doesn't have permissions for the SenseVoice service.

**Environment Variable**: The service now uses `TRANSCRIPT_SERVICE_API_KEY` (recommended) or falls back to `QWEN_API_KEY` / `DASHSCOPE_API_KEY`.

## 📊 Test Progress Status

| Step | Status | Details |
|------|--------|---------|
| 1. Video Download | ✅ PASS | YouTube video downloaded successfully |
| 2. Audio Extraction | ✅ PASS | Audio extracted with ffmpeg |
| 3. OSS Upload | ✅ PASS | Audio uploaded to Alibaba Cloud OSS |
| 4. **SenseVoice Transcription** | ❌ **FAIL** | **HTTP 401: Invalid API Key** |
| 5. Result Validation | ⏸️ PENDING | Waiting for step 4 |

## 🔧 Solution Steps

### Step 1: Verify Current API Key

Check your current API key:
```bash
cd /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend
grep -E "^(TRANSCRIPT_SERVICE_API_KEY|QWEN_API_KEY)" .env
```

The service prioritizes API keys in this order:
1. **TRANSCRIPT_SERVICE_API_KEY** (recommended - dedicated for audio transcription)
2. **QWEN_API_KEY** (fallback)
3. **DASHSCOPE_API_KEY** (fallback)

### Step 2: Get a Valid DashScope API Key

#### Option A: Alibaba Cloud DashScope Console (Recommended)

1. **Visit the DashScope Console**:
   - URL: https://dashscope.console.aliyun.com/
   - Or: https://help.aliyun.com/zh/dashscope/

2. **Log in**:
   - Use your Alibaba Cloud account credentials
   - If you don't have an account, create one first

3. **Navigate to API Keys**:
   - Find "API Key Management" or "密钥管理"
   - Click "Create API Key" or "创建 API Key"

4. **Configure Permissions**:
   - Ensure the key has access to **SenseVoice** service
   - Enable **Audio Speech Recognition (ASR)** permissions

5. **Copy the API Key**:
   - The key will start with `sk-`
   - It should be around 35-40 characters long
   - **⚠️ Save it immediately - you can only see it once!**

#### Option B: Use Environment Variable (Testing Only)

For testing purposes, you can also export the API key directly:
```bash
export DASHSCOPE_API_KEY=your_valid_key_here
```

### Step 3: Update the .env File

Edit the `.env` file:
```bash
cd /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend
nano .env  # or use your preferred editor
```

Add or update the transcription API key (recommended approach):
```bash
# Dedicated API key for audio transcription service (recommended)
TRANSCRIPT_SERVICE_API_KEY=your_new_valid_api_key_here
```

Or use the fallback approach:
```bash
# Fallback option
QWEN_API_KEY=your_new_valid_api_key_here
```

Example:
```bash
TRANSCRIPT_SERVICE_API_KEY=sk-1234567890abcdef1234567890abcdef123
```

**Important**: Do NOT add quotes around the key value.

### Step 4: Verify the New API Key

Test the new API key:
```bash
cd /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend
python -c "
from dotenv import load_dotenv
from pathlib import Path
import os

load_dotenv(Path('.env'))

import dashscope
from dashscope.audio.asr import Transcription

# Set API key (prioritizes TRANSCRIPT_SERVICE_API_KEY)
api_key = os.getenv('TRANSCRIPT_SERVICE_API_KEY') or os.getenv('QWEN_API_KEY')
dashscope.api_key = api_key

print(f'API Key loaded: {api_key[:10]}...' if api_key else 'NOT SET')
print(f'API Key length: {len(api_key)}')
print('Testing API connection...')

# Try a simple call (will fail on invalid URL but should authenticate)
try:
    response = Transcription.async_call(
        model='sensevoice-v1',
        file_urls=['https://dashscope.oss-cn-beijing.aliyuncs.com/samples/audio/paraformer/hello_world_female2.wav'],
        language_hints=['zh']
    )
    if response and hasattr(response, 'output'):
        print('✅ API Key is VALID - Authentication successful!')
        if hasattr(response.output, 'task_id'):
            print(f'Task ID created: {response.output.task_id}')
    else:
        print('⚠️ Unexpected response format')
except Exception as e:
    if '401' in str(e) or 'Invalid API-key' in str(e):
        print('❌ API Key is INVALID')
    else:
        print(f'Response: {e}')
"
```

Expected output with valid key:
```
API Key loaded: sk-1234567...
API Key length: 35
Testing API connection...
✅ API Key is VALID - Authentication successful!
Task ID created: abc-123-def
```

### Step 5: Re-run the Test

Once you have a valid API key, run the test again:
```bash
cd /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend
./run_transcription_test.sh
```

Or directly with pytest:
```bash
pytest app/tests/test_video_to_transcription_pipeline.py::TestVideoToTranscriptionPipeline::test_full_pipeline_youtube_to_transcription -v -s
```

## 🎯 Expected Behavior After Fix

With a valid API key, you should see:
```
2025-10-17 12:XX:XX,XXX - video_analysis - INFO - 发送转录请求到阿里云 SenseVoice...
2025-10-17 12:XX:XX,XXX - video_analysis - INFO - 转录任务已创建,任务ID: xxxxx
2025-10-17 12:XX:XX,XXX - video_analysis - INFO - 任务状态: RUNNING (已等待 5s)
2025-10-17 12:XX:XX,XXX - video_analysis - INFO - 任务状态: SUCCEEDED (已等待 10s)
2025-10-17 12:XX:XX,XXX - video_analysis - INFO - 转录任务成功完成
2025-10-17 12:XX:XX,XXX - video_analysis - INFO - ✓ 音频转录成功
```

## 📝 Common Issues

### Issue 1: "403 Forbidden" Error
**Cause**: API key doesn't have SenseVoice permissions
**Solution**: Enable SenseVoice/ASR permissions in DashScope console

### Issue 2: "400 Bad Request - Invalid file URL"
**Cause**: OSS URL is not publicly accessible
**Solution**: Ensure OSS bucket has public read permissions for the audio files

### Issue 3: "Quota Exceeded" Error
**Cause**: API usage limit reached
**Solution**: Check your DashScope quota and upgrade if needed

### Issue 4: API Key Works in Browser but Not in Code
**Cause**: Caching or environment variable issues
**Solution**: 
1. Restart your Python interpreter
2. Clear environment variables: `unset DASHSCOPE_API_KEY`
3. Re-load .env file
4. Restart the test

## 🔗 Helpful Resources

- **DashScope Console**: https://dashscope.console.aliyun.com/
- **SenseVoice API Documentation**: https://help.aliyun.com/zh/dashscope/developer-reference/api-sensevoice
- **API Key Management**: https://help.aliyun.com/zh/dashscope/developer-reference/activate-dashscope-and-create-an-api-key
- **Pricing**: https://help.aliyun.com/zh/dashscope/product-overview/billing-methods

## ✅ Checklist

Before running the test again, ensure:

- [ ] You have a valid Alibaba Cloud account
- [ ] You have created a DashScope API key
- [ ] The API key has SenseVoice/ASR permissions enabled
- [ ] The API key is correctly set in `.env` file (no quotes, no spaces)
- [ ] The `.env` file is in the correct location (`backend/.env`)
- [ ] You have tested the API key with the verification script above
- [ ] Your account has sufficient quota/credits

---

**Last Updated**: 2025-10-17
**Status**: ⚠️ Waiting for Valid API Key
