---
trigger: manual
alwaysApply: false
---

---
description: "SenseVoice录音语音识别Python SDK使用指南"
---
# SenseVoice录音语音识别Python SDK使用指南

## 概述
SenseVoice是一个语音识别大模型，支持50多种语言的识别，具备情感分析和音频事件检测功能。

## 前置条件
- 已开通服务并获取API Key
- 配置API Key到环境变量（不要硬编码）
- 安装最新版DashScope SDK

## 模型信息
- **模型名称**: `sensevoice-v1`
- **功能特性**:
  - 支持50+种语言识别
  - 情感分析
  - 音频事件检测
  - 标点符号预测
  - 逆文本正则化（ITN）

## 约束条件

### 音频文件要求
- **文件大小**: 不超过2GB
- **时长**: 无限制
- **格式**: aac, amr, avi, flac, flv, m4a, mkv, mov, mp3, mp4, mpeg, ogg, opus, wav, webm, wma, wmv
- **批处理**: 单次请求最多支持100个文件URL
- **访问方式**: 必须是可通过公网访问的HTTP/HTTPS URL

### 语言识别
- 每次只支持识别一种语言
- 不要在`language_hints`参数中指定多个语言代码

## 使用方法

### 方式一：异步提交 + 同步等待

from http import HTTPStatus
from dashscope.audio.asr import Transcription
import json

# 提交任务
transcribe_response = Transcription.async_call(
    model='sensevoice-v1',
    file_urls=['https://your-audio-file-url.wav'],
    language_hints=['zh'],  # 中文
)

# 等待任务完成
transcribe_response = Transcription.wait(task=transcribe_response.output.task_id)

if transcribe_response.status_code == HTTPStatus.OK:
    print(json.dumps(transcribe_response.output, indent=4, ensure_ascii=False))

### 方式二：异步提交 + 轮询查询

from http import HTTPStatus
from dashscope.audio.asr import Transcription
import json

# 提交任务
transcribe_response = Transcription.async_call(
    model='sensevoice-v1',
    file_urls=['https://your-audio-file-url.wav'],
    language_hints=['en'],  # 英文
)

# 轮询查询结果
while True:
    if transcribe_response.output.task_status in ['SUCCEEDED', 'FAILED']:
        break
    transcribe_response = Transcription.fetch(task=transcribe_response.output.task_id)

if transcribe_response.status_code == HTTPStatus.OK:
    print(json.dumps(transcribe_response.output, indent=4, ensure_ascii=False))

## 请求参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| model | str | 是 | - | 固定为`sensevoice-v1` |
| file_urls | list[str] | 是 | - | 音频文件URL列表，最多100个 |
| channel_id | list[int] | 否 | [0] | 多音轨文件中需要识别的音轨索引 |
| disfluency_removal_enabled | bool | 否 | False | 是否过滤语气词 |
| language_hints | list[str] | 否 | ["auto"] | 语言代码，只支持一个语种 |

## 响应结果

### 重要字段说明

| 字段 | 说明 |
|------|------|
| status_code | HTTP请求状态码 |
| code | 错误码 |
| message | 错误信息 |
| task_id | 任务ID |
| task_status | 任务状态：PENDING/RUNNING/SUCCEEDED/FAILED |
| subtask_status | 子任务状态 |
| file_url | 被识别音频的URL |
| transcription_url | 识别结果JSON文件的下载URL（24小时有效期） |

### 识别结果JSON结构

{
  "audio_format": "wav",
  "channels": [0],
  "original_sampling_rate": 16000,
  "original_duration_in_milliseconds": 5000,
  "channel_id": 0,
  "content_duration_in_milliseconds": 4800,
  "transcript": "完整的识别文本",
  "sentences": [
    {
      "begin_time": 0,
      "end_time": 2000,
      "text": "句子级别的识别结果"
    }
  ]
}

## 特殊功能

### 情感识别
支持4种情绪标记：
- `|ANGRY|` - 生气
- `|HAPPY|` - 高兴
- `|SAD|` - 伤心
- `|NEUTRAL|` - 中性

示例：`"今天天气好棒啊！|HAPPY|"`

### 音频事件检测
支持4种音频事件：
- `|Applause|...|/Applause|` - 掌声
- `|BGM|...|/BGM|` - 背景音乐
- `|Laughter|...|/Laughter|` - 笑声
- `|Speech|...|/Speech|` - 人声

示例：`"|Applause|今天|/Applause|天气好棒啊！"`

## 支持的语言代码

### 重点支持语言（Top 10）
| 语言 | 代码 |
|------|------|
| 中文 | zh |
| 英文 | en |
| 粤语 | yue |
| 日语 | ja |
| 韩语 | ko |
| 俄语 | ru |
| 法语 | fr |
| 意大利语 | it |
| 德语 | de |
| 西班牙语 | es |

### 其他支持语言
加泰罗尼亚语(ca), 印度尼西亚语(id), 泰语(th), 荷兰语(nl), 葡萄牙语(pt), 捷克语(cs), 波兰语(pl), 希腊语(el), 马来语(ms), 塔加洛语(tl), 保加利亚语(bg), 克罗地亚语(hr), 丹麦语(da), 土耳其语(tr), 越南语(vi), 希伯来语(he), 匈牙利语(hu), 乌克兰语(uk), 爪哇语(jw), 乌兹别克语(uz), 挪威语(no), 罗马尼亚语(ro), 瑞典语(sv), 波斯语(fa), 泰米尔语(ta), 阿塞拜疆语(az), 孟加拉语(bn), 缅甸语(my), 高棉语(km), 印地语(hi), 卡纳达语(kn), 老挝语(lo), 马拉雅拉姆语(ml), 马拉地语(mr), 蒙古语(mn), 尼泊尔语(ne), 旁遮普语(pa), 僧伽罗语(si), 斯瓦希里语(sw), 泰卢固语(te), 乌尔都语(ur), 豪萨语(ha)

## 常见错误码

| 错误代码 | 错误信息 | 说明 |
|---------|---------|------|
| InvalidFile.DecodeFailed | The audio file cannot be decoded | 文件解码失败，请检查文件格式和编码 |

## 注意事项
- 识别结果和下载链接有效期为24小时
- 任务提交后进入PENDING状态，排队时间取决于队列长度
- 计费基于AI识别出的有效语音时长，非语音段落不计费
- 不支持本地文件直传，必须使用可公网访问的URL

---
