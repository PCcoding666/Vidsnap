# YouTube 视频转录集成测试报告

## 测试时间
- 测试时间: 2025-10-17 19:33:17
- 总耗时: 65 秒

## 测试环境

- Python 版本: 
Python 3.10.16

- DashScope SDK 版本:
  - dashscope: 未知版本

## 测试结果

✅ **状态**: 全部通过

## 测试详情

请查看 `test_output.log` 获取完整的测试输出。

### 测试用例

1. **test_dashscope_service_availability**: 检查 DashScope 服务可用性
2. **test_full_pipeline_youtube_to_transcription**: 完整流程测试
   - YouTube 视频下载
   - 音频提取 (ffmpeg)
   - 音频上传到 OSS
   - SenseVoice 音频转录
   - 转录结果验证
3. **test_transcription_segments_format**: 转录段落格式验证
4. **test_cleanup_after_processing**: 临时文件清理测试

### 关键指标

从测试输出中提取关键指标...

**转录语言**: zh
**段落数量**: 1
**总体置信度**: 0.90


### 性能数据

- **视频下载**: 51.43秒
- **音频提取**: 0.18秒
- **OSS上传**: 0.67秒
- **SenseVoice转录**: 12.43秒

## OSS 资源

测试过程中上传的文件:

### 音频文件

- https://yt-summerizer-aliyun.oss-cn-hangzhou.aliyuncs.com/videos/20251017/78c0dff6-0414-42bb-986a-4d41a69a3ef4/audio/78c0dff6-0414-42bb-986a-4d41a69a3ef4_audio.wav
- https://yt-summerizer-aliyun.oss-cn-hangzhou.aliyuncs.com/videos/20251017/78c0dff6-0414-42bb-986a-4d41a69a3ef4/audio/78c0dff6-0414-42bb-986a-4d41a69a3ef4_audio.wav


## 转录示例

从测试输出提取的转录内容:

```
2025-10-17 19:33:17,281 - video_analysis - INFO -         文本: . . <|Speech|>andit'Spacked with new features<|BGM|>.I'Lpass it to bill for more details.<|/Speech|><|/BGM|>. <|BGM|><|Speech|>sora2is also the state of the art for motion<|/BGM|>physics 。IQ and body mechanics<|BGM|> marking a giant leap forward in realism<|/Speech|><|/BGM|>.. <|BGM|><|Speech|>andwe're introducing cameo,giving you the power to step into any world or scene and letting your friends cast you and theirs<|/BGM|><|/Speech|>.<|BGM|><|Speech|>onthe path to agi,the gains aren'Tjust about productivity.it'Sabout creating new possibilities.it'Salso about creativity and joy.<|/BGM|><|/Speech|>. . 
INFO     video_analysis:test_video_to_transcription_pipeline.py:181         文本: . . <|Speech|>andit'Spacked with new features<|BGM|>.I'Lpass it to bill for more details.<|/Speech|><|/BGM|>. <|BGM|><|Speech|>sora2is also the state of the art for motion<|/BGM|>physics 。IQ and body mechanics<|BGM|> marking a giant leap forward in realism<|/Speech|><|/BGM|>.. <|BGM|><|Speech|>andwe're introducing cameo,giving you the power to step into any world or scene and letting your friends cast you and theirs<|/BGM|><|/Speech|>.<|BGM|><|Speech|>onthe path to agi,the gains aren'Tjust about productivity.it'Sabout creating new possibilities.it'Salso about creativity and joy.<|/BGM|><|/Speech|>. . 
2025-10-17 19:33:17,281 - video_analysis - INFO -         置信度: 90.00%
INFO     video_analysis:test_video_to_transcription_pipeline.py:182         置信度: 90.00%
2025-10-17 19:33:17,281 - video_analysis - INFO -   - 平均置信度: 90.00% (合格)
INFO     video_analysis:test_video_to_transcription_pipeline.py:197   - 平均置信度: 90.00% (合格)
```


## 错误日志

无错误

---
*报告生成时间: 2025-10-17 19:33:17*
