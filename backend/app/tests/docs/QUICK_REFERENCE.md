# 🚀 快速命令参考

## 运行完整测试

### 推荐方式（Shell脚本）
```bash
cd backend
./run_pipeline_test.sh
```

### Python方式
```bash
cd backend
python run_test.py
```

### Pytest直接运行
```bash
cd backend
pytest app/tests/test_video_to_oss_pipeline.py -v -s
```

## 运行特定测试

```bash
# 只运行OSS服务检查
pytest app/tests/test_video_to_oss_pipeline.py::test_oss_service_availability -v -s

# 只运行完整流程测试
pytest app/tests/test_video_to_oss_pipeline.py::test_full_pipeline_youtube_to_oss -v -s

# 只运行URL可访问性测试
pytest app/tests/test_video_to_oss_pipeline.py::test_keyframe_oss_urls_accessibility -v -s

# 跳过清理测试（保留临时文件用于调试）
pytest app/tests/test_video_to_oss_pipeline.py -v -s -k "not cleanup"
```

## 环境配置

### 创建.env文件
```bash
cd backend
cat > .env << EOF
ALIYUN_ACCESS_KEY_ID=your_access_key_id
ALIYUN_ACCESS_KEY_SECRET=your_access_key_secret
ALIYUN_OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
ALIYUN_OSS_BUCKET=your_bucket_name
EOF
```

### 安装依赖
```bash
cd backend
pip install -r requirements.txt
```

### 安装系统工具
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get install ffmpeg
```

## 查看测试报告

```bash
# 查看报告
cat backend/TEST_OSS_PIPELINE_RESULTS.md

# 使用Markdown预览器（如果已安装）
open backend/TEST_OSS_PIPELINE_RESULTS.md
```

## 调试技巧

### 查看详细日志
```bash
pytest app/tests/test_video_to_oss_pipeline.py -v -s --log-cli-level=DEBUG
```

### 失败时进入调试器
```bash
pytest app/tests/test_video_to_oss_pipeline.py -v -s --pdb
```

### 只运行上次失败的测试
```bash
pytest app/tests/test_video_to_oss_pipeline.py -v -s --lf
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `app/tests/test_video_to_oss_pipeline.py` | 主测试文件 |
| `run_pipeline_test.sh` | Shell运行脚本 |
| `run_test.py` | Python运行脚本 |
| `RUN_PIPELINE_TEST.md` | 详细测试指南 |
| `TESTING_SUMMARY.md` | 项目总结文档 |
| `TEST_OSS_PIPELINE_RESULTS.md` | 测试报告（自动生成） |

## 预期输出

```
========================================
测试1：验证OSS服务可用性
========================================
✅ OSS服务可用 (耗时: 0.12s)
   Bucket: your-bucket-name

========================================
测试2：完整流程测试
========================================

[阶段1] YouTube视频下载...
✅ 视频下载成功 (耗时: 25.34s)
   视频ID: abc123-def456
   标题: Test Video
   时长: 120.50s

[阶段2] 关键帧提取验证...
✅ 关键帧提取成功 (耗时: 12.56s)
   关键帧数量: 8

[阶段3] OSS上传验证...
✅ OSS上传验证成功 (耗时: 5.67s)
   视频OSS URL: https://...
   关键帧OSS URL数量: 8

✅ 完整流程测试通过！总耗时: 43.57s

========================================
测试3：OSS URL可访问性验证
========================================
   ✅ 关键帧1: 可访问 (HTTP 200)
   ✅ 关键帧2: 可访问 (HTTP 200)
   ...
✅ URL可访问性检查完成 (耗时: 8.23s)
   可访问: 8/8 (100.0%)

========================================
测试4：临时文件清理
========================================
✅ 临时文件清理成功 (耗时: 0.15s)

✅ 测试报告已保存到: TEST_OSS_PIPELINE_RESULTS.md
```

## 常见问题快速修复

### ❌ ModuleNotFoundError: No module named 'pytest'
```bash
pip install pytest pytest-asyncio
```

### ❌ FileNotFoundError: ffmpeg
```bash
brew install ffmpeg  # macOS
```

### ❌ 缺少环境变量
```bash
# 检查.env文件
cat backend/.env

# 手动导出
export $(cat backend/.env | xargs)
```

### ❌ YouTube下载失败
```bash
pip install --upgrade yt-dlp
```

---
**快速开始**: `cd backend && ./run_pipeline_test.sh`
