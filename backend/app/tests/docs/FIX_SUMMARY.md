# Test Fix Summary

## Issue Fixed

**Error**: `AttributeError: 'AliyunVideoService' object has no attribute 'download_youtube_video'`

## Root Cause

The test file `test_video_to_transcription_pipeline.py` was calling a non-existent method `download_youtube_video()` on the `AliyunVideoService` class.

### Why It Happened

The `AliyunVideoService` class in `video_service.py` was refactored to use:
- `process_video_dual_source()` - Main method that handles both YouTube URLs and uploaded files
- `_download_from_youtube()` - Private method for YouTube downloads (internal use only)

But the test file was still using the old API `download_youtube_video()` which no longer exists.

## Changes Made

### 1. Fixed Method Call in Test File ✅

**File**: `app/tests/test_video_to_transcription_pipeline.py`

**Changed from**:
```python
download_result = await video_service.download_youtube_video(TEST_YOUTUBE_URL)
```

**Changed to**:
```python
download_result = await video_service.process_video_dual_source(youtube_url=TEST_YOUTUBE_URL)
```

### 2. Updated Result Handling ✅

The `process_video_dual_source()` method returns a **dictionary**, not an object with attributes.

**Changed from**:
```python
video_id = download_result.video_id
video_path = download_result.file_path
video_metadata = download_result.metadata
```

**Changed to**:
```python
video_id = download_result.get("video_id")
session_temp_dir = download_result.get("session_temp_dir")
video_metadata = download_result.get("video_metadata", {})

# Find the downloaded video file in the session directory
if session_temp_dir and os.path.exists(session_temp_dir):
    for file in os.listdir(session_temp_dir):
        if file.endswith(('.mp4', '.avi', '.mov', '.mkv')):
            video_path = os.path.join(session_temp_dir, file)
            break
```

### 3. Fixed Cleanup Logic ✅

Updated the cleanup to remove the entire session temporary directory instead of individual files:

**Changed from**:
```python
finally:
    if video_path and os.path.exists(video_path):
        os.remove(video_path)
```

**Changed to**:
```python
finally:
    if 'download_result' in locals() and download_result:
        session_temp_dir = download_result.get("session_temp_dir")
        if session_temp_dir and os.path.exists(session_temp_dir):
            import shutil
            shutil.rmtree(session_temp_dir)
```

### 4. Fixed API Key Configuration ✅

**File**: `app/services/speech_service.py`

Added import and direct API key setting for DashScope:

**Added**:
```python
import dashscope

# In __init__ method:
if self.api_key:
    # Method 1: Set environment variable
    os.environ["DASHSCOPE_API_KEY"] = self.api_key
    # Method 2: Set dashscope.api_key directly (recommended)
    dashscope.api_key = self.api_key
```

This ensures the DashScope SDK can find the API key using either method.

## Test Results

### Before Fix
```
FAILED - AttributeError: 'AliyunVideoService' object has no attribute 'download_youtube_video'
```

### After Fix
✅ Test now properly calls the correct method
✅ Video download works successfully
✅ Audio extraction works
✅ OSS upload works
✅ Proper cleanup of temporary files
⚠️ **New Issue Found**: DashScope API Key Invalid

### Current Issue: Invalid API Key

The test now progresses further but fails at the transcription step with:
```
ERROR - 转录API调用失败: HTTP 401 - Invalid API-key provided.
```

**Root Cause**: The `QWEN_API_KEY` in the `.env` file is invalid or expired.

**Solution Required**:
1. Get a valid DashScope API key from [Alibaba Cloud DashScope Console](https://dashscope.console.aliyun.com/)
2. Update the `.env` file:
   ```bash
   QWEN_API_KEY=your_valid_api_key_here
   ```
3. The API key should start with `sk-` and be approximately 35 characters long

**How to Get a Valid API Key**:
1. Visit https://dashscope.console.aliyun.com/
2. Log in with your Alibaba Cloud account
3. Navigate to API Keys section
4. Create a new API key or use an existing valid one
5. Ensure the key has permissions for SenseVoice service

## Files Modified

1. `app/tests/test_video_to_transcription_pipeline.py` - Updated test to use correct API
2. `app/services/speech_service.py` - Enhanced API key configuration

## Verification

Run the test with:
```bash
cd /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend
./run_transcription_test.sh
```

Or run directly with pytest:
```bash
pytest app/tests/test_video_to_transcription_pipeline.py::TestVideoToTranscriptionPipeline::test_full_pipeline_youtube_to_transcription -v -s
```

## Summary

The error was caused by **API mismatch** between the test file and the actual service implementation. The fix updates the test to use the current `process_video_dual_source()` method and properly handles its dictionary return value.

---
**Fixed Date**: 2025-10-17
**Status**: ✅ Complete
