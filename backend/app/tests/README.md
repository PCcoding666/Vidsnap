# 测试目录结构说明

## 目录结构

```
app/tests/
├── README.md                              # 本文件
├── __init__.py                           # Python包初始化文件
├── docs/                                 # 测试文档目录
│   ├── API_KEY_ISSUE_RESOLUTION.md       # API密钥问题解决方案
│   ├── CHANGES_QWEN_API_KEY.md          # Qwen API密钥变更说明
│   ├── ERROR_ANALYSIS_NETWORK_ISSUE.md  # 网络问题错误分析
│   ├── FILES_CHANGED.md                 # 文件变更记录
│   ├── FIX_SUMMARY.md                   # 修复总结
│   ├── IMPLEMENTATION_COMPLETE.md        # 实现完成文档
│   ├── QUICK_REFERENCE.md               # 快速参考指南
│   ├── README.md                        # 项目README
│   ├── RUN_PIPELINE_TEST.md             # Pipeline测试运行指南
│   ├── SENSEVOICE_*.md                  # SenseVoice相关文档
│   ├── TESTING_SUMMARY.md               # 测试总结
│   ├── TEST_OSS_PIPELINE_RESULTS.md     # OSS Pipeline测试结果
│   ├── TEST_PIPELINE_README.md          # Pipeline测试README
│   ├── TEST_RESULTS.md                  # 测试结果
│   ├── TEST_TRANSCRIPTION_RESULTS.md    # 转录测试结果
│   ├── TRANSCRIPTION_*.md               # 转录相关文档
│   └── TRANSCRIPT_*.md                  # 转录服务相关文档
├── run_pipeline_test.sh                 # OSS Pipeline测试脚本
├── run_transcription_test.sh            # 转录测试脚本
├── quick_test.py                        # 快速测试脚本
├── test_oss_service.py                  # OSS服务测试
├── test_pipeline_service.py             # Pipeline服务测试
├── test_speech_service.py               # 语音服务测试
├── test_video_service.py                # 视频服务测试
├── test_video_to_oss_pipeline.py        # 视频到OSS完整流程测试
├── test_video_to_transcription_pipeline.py  # 视频到转录完整流程测试
└── test_youtube_download.py             # YouTube下载测试
```

## 测试脚本使用说明

### 1. OSS Pipeline 测试

运行完整的YouTube视频到OSS存储的端到端测试：

```bash
cd /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend
./app/tests/run_pipeline_test.sh
```

或者从tests目录直接运行：

```bash
cd /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend/app/tests
./run_pipeline_test.sh
```

### 2. 转录服务测试

运行YouTube视频到音频转录的端到端测试：

```bash
cd /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend
./app/tests/run_transcription_test.sh
```

或者从tests目录直接运行：

```bash
cd /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend/app/tests
./run_transcription_test.sh
```

### 3. 单独运行特定测试

使用pytest运行特定测试文件：

```bash
cd /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend
python3 -m pytest app/tests/test_oss_service.py -v
```

## 测试报告

所有测试报告均保存在 `docs/` 目录下：

- **TEST_OSS_PIPELINE_RESULTS.md**: OSS Pipeline测试结果报告
- **TEST_TRANSCRIPTION_RESULTS.md**: 转录测试结果报告
- **TEST_RESULTS.md**: 通用测试结果

## 环境要求

运行测试前请确保：

1. 已配置 `.env` 文件（在backend目录下）
2. 安装了所有依赖：`pip install -r requirements.txt`
3. 已配置必要的API密钥和OSS凭证

详细配置说明请参考 `docs/` 目录下的相关文档。

## 文档分类

### API密钥相关
- API_KEY_ISSUE_RESOLUTION.md
- CHANGES_QWEN_API_KEY.md
- TRANSCRIPT_SERVICE_API_KEY_GUIDE.md
- TRANSCRIPT_API_KEY_UPDATE_SUMMARY.md

### SenseVoice相关
- SENSEVOICE_IMPLEMENTATION_SUMMARY.md
- SENSEVOICE_INTEGRATION_GUIDE.md
- SENSEVOICE_QUICKSTART.md
- SENSEVOICE_README.md
- SENSEVOICE_SINGLE_LANGUAGE_FIX.md

### 测试相关
- TESTING_SUMMARY.md
- TEST_OSS_PIPELINE_RESULTS.md
- TEST_PIPELINE_README.md
- TEST_RESULTS.md
- TEST_TRANSCRIPTION_RESULTS.md
- RUN_PIPELINE_TEST.md

### 问题修复和变更
- ERROR_ANALYSIS_NETWORK_ISSUE.md
- FILES_CHANGED.md
- FIX_SUMMARY.md
- TRANSCRIPTION_DISPLAY_UPDATE.md
- TRANSCRIPTION_URL_FIX.md

### 实现和指南
- IMPLEMENTATION_COMPLETE.md
- QUICK_REFERENCE.md
- README.md

---

*最后更新: 2025-10-17*
