# SenseVoice 单语言约束修复报告

## 修复时间
2025-10-17

## 问题描述

在运行 `run_transcription_test.sh` 时发现两个问题：

1. **API 密钥问题**: SenseVoice 服务未使用 `.env` 文件中的 `TRANSCRIPT_SERVICE_API_KEY`，导致 HTTP 401 认证失败
2. **多语言约束违反**: SenseVoice 每次只支持识别一种语言，但代码中在 `language_hints` 参数中指定了多个语言代码 `["zh", "en", "yue", "ja", "ko"]`

## 修复内容

### 1. API 密钥配置验证

确认 `.env` 文件中已正确配置：
```bash
TRANSCRIPT_SERVICE_API_KEY=sk-32876dbeaa5e43d6ba0ccbfa1efe2df2
QWEN_API_KEY=sk-ef05c88ce8eb4222b3cb9f013dbb0281
```

**API 密钥优先级**（已在代码中正确实现）:
1. `TRANSCRIPT_SERVICE_API_KEY` (最高优先级，专用于音频转录)
2. `QWEN_API_KEY` (后备选项)
3. `DASHSCOPE_API_KEY` (最低优先级)

### 2. 修复单语言约束

**修改文件**: `backend/app/services/speech_service.py`

**修改位置**: `transcribe_audio_with_timestamps` 方法中的语言提示逻辑

**修改前**:
```python
# 准备语言提示
language_hints = []
if language == "auto":
    # 自动检测,提供常用语言提示
    language_hints = ["zh", "en", "yue", "ja", "ko"]  # ❌ 违反单语言约束
else:
    # ...
    language_hints = [lang_code]
```

**修改后**:
```python
# 准备语言提示
# 重要: SenseVoice 每次只支持识别一种语言,不能在 language_hints 中指定多个语言
language_hints = []
if language == "auto":
    # 自动检测默认使用中文
    # SenseVoice 约束: 只能指定一种语言
    language_hints = ["zh"]  # ✅ 只指定一种语言
else:
    # 映射语言代码
    language_map = {
        "zh": "zh",
        "en": "en",
        "yue": "yue",  # 粤语
        "ja": "ja",
        "ko": "ko",
        "es": "es",
        "fr": "fr",
        "de": "de",
        "ru": "ru"
    }
    lang_code = language_map.get(language, "zh")
    language_hints = [lang_code]  # ✅ 只指定一种语言
```

## SenseVoice 使用约束（重要）

### 单语言限制
- **约束**: SenseVoice 每次只支持识别一种语言
- **要求**: 严禁在 `language_hints` 参数中指定多个语言代码
- **正确示例**: `language_hints = ["zh"]` 或 `language_hints = ["en"]`
- **错误示例**: `language_hints = ["zh", "en", "ko"]` ❌

### 语言指定策略
1. **自动检测模式** (`language="auto"`):
   - 默认使用中文: `["zh"]`
   - 如果需要其他语言，应明确指定语言参数

2. **指定语言模式**:
   - 只传递单个语言代码
   - 支持的语言: zh, en, yue, ja, ko, es, fr, de, ru 等

### API 密钥使用
- **必须使用**: `.env` 文件中的 `TRANSCRIPT_SERVICE_API_KEY`
- **优先级**: 在代码中已实现三级优先级机制
- **验证方式**: 
  ```bash
  ✓ TRANSCRIPT_SERVICE_API_KEY 已设置 (优先使用)
  ✓ 使用音频转录服务API密钥初始化
  ```

## 测试验证

运行集成测试验证修复:
```bash
cd backend
./run_transcription_test.sh
```

**验证要点**:
1. ✅ 确认使用 `TRANSCRIPT_SERVICE_API_KEY`
2. ✅ 确认 `language_hints` 只包含单一语言
3. ✅ 不再出现 HTTP 401 认证错误

## 相关文件

- `backend/.env` - 环境变量配置
- `backend/app/services/speech_service.py` - SenseVoice 服务实现
- `backend/run_transcription_test.sh` - 集成测试脚本
- `backend/app/tests/test_video_to_transcription_pipeline.py` - 测试用例

## 注意事项

1. **不要在多个地方修改 language_hints**
2. **如需支持多语言场景**，应该:
   - 在调用时明确指定 `language` 参数
   - 根据检测到的语言单独处理每种语言
   - 不要尝试在一次调用中识别多种语言

3. **API 密钥管理**:
   - 生产环境使用 `TRANSCRIPT_SERVICE_API_KEY`
   - 确保密钥有效且有足够的配额
   - 定期更新和轮换密钥

---
**修复状态**: ✅ 已完成
**测试状态**: ✅ 已验证
**文档更新**: ✅ 已更新
