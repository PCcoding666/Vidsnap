# SenseVoice 转录文本获取修复

## 问题描述

### 现象
测试通过，但转录文本显示为占位符消息：
```
文本: (请从转录URL获取完整文本)
```

### 根本原因

**SenseVoice API 返回的是 JSON 文件的 URL，而不是直接的转录文本！**

**API 响应结构**:
```python
{
    'file_url': 'https://yt-summerizer-aliyun.oss-cn-hangzhou.aliyuncs.com/.../audio.wav',
    'transcription_url': 'https://dashscope-result-bj.oss-cn-beijing.aliyuncs.com/.../xxx.json',  # ← 实际转录结果在这里
    'subtask_status': 'SUCCEEDED'
}
```

**问题所在**:
- ❌ 代码期望直接从响应中获取 `text` 字段
- ✅ 实际需要下载 `transcription_url` 指向的 JSON 文件并解析

## 修复方案

### 修改文件
[`speech_service.py`](file:///Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend/app/services/speech_service.py) - `_parse_transcription_to_segments` 方法

### 修复逻辑

```python
# 如果没有句子分段，需要从 transcription_url 下载 JSON 获取完整文本
if transcription_url:
    # 1. 下载 JSON 文件
    response = requests.get(transcription_url, timeout=30)
    transcription_data = response.json()
    
    # 2. 解析文本内容（支持多种可能的 JSON 结构）
    if 'transcripts' in transcription_data:
        # 如果有 transcripts 列表
        full_text = ' '.join([t.get('text', '') for t in transcription_data['transcripts']])
    elif 'text' in transcription_data:
        # 直接有 text 字段
        full_text = transcription_data['text']
    elif 'Transcripts' in transcription_data:
        # 大写版本
        full_text = ' '.join([t.get('Text', t.get('text', '')) for t in transcription_data['Transcripts']])
    
    # 3. 创建转录段落
    segments = [TranscriptSegment(text=full_text, ...)]
```

### 关键改进

1. **✅ 自动下载 JSON**: 使用 `requests.get()` 下载转录结果文件
2. **✅ 多格式支持**: 处理多种可能的 JSON 结构
3. **✅ 错误处理**: 捕获并记录下载失败的情况
4. **✅ 详细日志**: 记录下载过程和解析结果

## 工作流程

```
SenseVoice API Response
   ↓
获取 transcription_url
   ↓
HTTP GET 请求下载 JSON
   ↓
解析 JSON 提取文本
   ↓
创建 TranscriptSegment
   ↓
返回完整转录结果
```

## 预期效果

### 修复前
```
文本: (请从转录URL获取完整文本)
置信度: 90.00%
```

### 修复后
```
文本: Sound on for Sora 2. OpenAI's newest video generation model now with audio...
置信度: 90.00%
```

## 测试验证

运行测试查看实际转录文本:
```bash
cd /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend
./run_transcription_test.sh
```

**验证要点**:
1. ✅ 转录文本不再是占位符
2. ✅ 显示实际的英文/中文转录内容
3. ✅ 文本长度 > 10 字符
4. ✅ 终端显示前 20 行转录文本

## 相关文件

- [`speech_service.py`](file:///Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend/app/services/speech_service.py) - 已修复
- [`run_transcription_test.sh`](file:///Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend/run_transcription_test.sh) - 测试脚本
- [`test_output.log`](file:///Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend/test_output.log) - 测试日志

## 技术细节

### SenseVoice JSON 可能的结构

根据阿里云 DashScope 文档，转录结果 JSON 可能包含:

**格式 1**: 带时间戳的句子列表
```json
{
  "transcripts": [
    {
      "text": "Sound on for Sora 2",
      "begin_time": 0,
      "end_time": 1500,
      "confidence": 0.95
    }
  ]
}
```

**格式 2**: 简单文本
```json
{
  "text": "Sound on for Sora 2. OpenAI's newest model..."
}
```

**格式 3**: 大写字段
```json
{
  "Transcripts": [...]
}
```

代码现在支持所有这些格式！

## 调试日志示例

修复后的代码会输出：
```
从转录URL获取完整文本: https://dashscope-result-bj.oss-cn-beijing.aliyuncs.com/.../xxx.json
转录JSON数据: {...}
成功从 URL 获取转录文本，长度: 245 字符
解析完成,共1个段落,总体置信度: 0.90
```

---
**修复状态**: ✅ 已完成  
**测试状态**: 🔄 进行中  
**预计效果**: 能够正确显示完整的转录文本
