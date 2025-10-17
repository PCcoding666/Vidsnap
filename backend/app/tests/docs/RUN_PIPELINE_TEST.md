# YouTube到OSS完整流程集成测试指南

## 📋 测试概述

本测试验证从YouTube下载视频到阿里云OSS存储的完整流程：

```
YouTube URL → 视频下载 → 场景关键帧提取 → OSS上传 → URL可访问性验证 → 临时文件清理
```

## ✅ 前置条件

### 1. 环境变量配置

创建或编辑 `backend/.env` 文件，添加以下配置：

```bash
# 阿里云OSS配置（必需）
ALIYUN_ACCESS_KEY_ID=your_access_key_id
ALIYUN_ACCESS_KEY_SECRET=your_access_key_secret
ALIYUN_OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
ALIYUN_OSS_BUCKET=your_bucket_name

# OpenAI配置（可选，本测试不需要）
OPENAI_API_KEY=your_openai_api_key

# 临时目录（可选）
TEMP_DIR=/tmp/video_analysis
```

### 2. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

确保安装了以下关键依赖：
- `pytest>=7.4.0`
- `pytest-asyncio>=0.21.0`
- `yt-dlp>=2024.10.7`
- `ffmpeg-python>=0.2.0`
- `oss2>=2.18.0`
- `requests>=2.31.0`

### 3. 系统工具

确保系统已安装：
- **ffmpeg**: `brew install ffmpeg` (macOS) 或 `apt-get install ffmpeg` (Linux)
- **yt-dlp**: 已包含在requirements.txt中

## 🚀 运行测试

### 方法1：使用pytest命令（推荐）

```bash
cd backend

# 运行完整测试套件
pytest app/tests/test_video_to_oss_pipeline.py -v -s

# 运行特定测试用例
pytest app/tests/test_video_to_oss_pipeline.py::test_full_pipeline_youtube_to_oss -v -s

# 生成详细的测试报告
pytest app/tests/test_video_to_oss_pipeline.py -v -s --tb=long
```

### 方法2：直接运行Python脚本

```bash
cd backend
python -m app.tests.test_video_to_oss_pipeline
```

### 方法3：使用快捷脚本

```bash
cd backend
chmod +x run_pipeline_test.sh
./run_pipeline_test.sh
```

## 📊 测试内容

### 测试1：OSS服务可用性检查
- 验证阿里云OSS配置是否完整
- 验证OSS服务连接是否正常

### 测试2：完整流程测试
- **阶段1**：从YouTube下载视频
  - URL: https://www.youtube.com/watch?v=1PaoWKvcJP0
  - 超时设置：120秒
- **阶段2**：场景关键帧提取
  - 使用ffmpeg场景检测
  - 提取1-10个关键帧
- **阶段3**：OSS上传验证
  - 验证视频上传到OSS
  - 验证所有关键帧上传到OSS
  - 验证URL格式正确性

### 测试3：URL可访问性验证
- 对每个关键帧的OSS URL发起HTTP HEAD请求
- 验证HTTP状态码为200
- 计算可访问率

### 测试4：临时文件清理
- 验证下载的视频文件已清理
- 验证提取的关键帧文件已清理
- 验证临时目录已删除

## 📝 测试报告

测试完成后会自动生成两份报告：

1. **控制台输出**：实时显示测试进度和结果
2. **Markdown报告**：`backend/TEST_OSS_PIPELINE_RESULTS.md`

报告内容包括：
- ✅ 测试概览（总体状态、耗时、视频ID）
- 🔄 各阶段执行情况（成功/失败、耗时、详情）
- 🖼️ 关键帧信息表格
- 🌐 URL可访问性统计
- 🧹 清理操作结果
- ⚠️ 错误日志（如有）
- 📝 测试结论

## ⚙️ 配置选项

可在测试文件中修改以下常量：

```python
# 测试视频URL
TEST_YOUTUBE_URL = "https://www.youtube.com/watch?v=1PaoWKvcJP0"

# 网络超时（秒）
NETWORK_TIMEOUT = 120

# 关键帧数量范围
MIN_KEYFRAMES = 1
MAX_KEYFRAMES = 10

# 测试报告路径
TEST_REPORT_PATH = Path(__file__).parent.parent.parent / "TEST_OSS_PIPELINE_RESULTS.md"
```

## ❌ 常见问题

### 1. OSS配置错误

**错误信息**：
```
缺少以下环境变量: ALIYUN_ACCESS_KEY_ID, ALIYUN_ACCESS_KEY_SECRET
```

**解决方法**：
- 检查 `.env` 文件是否存在
- 确认环境变量名称拼写正确
- 重启终端或重新加载环境变量

### 2. YouTube下载失败

**错误信息**：
```
YouTube视频下载失败: HTTP Error 403
```

**解决方法**：
- 检查网络连接
- 更新yt-dlp: `pip install --upgrade yt-dlp`
- 尝试使用不同的YouTube URL
- 检查是否需要代理

### 3. ffmpeg未安装

**错误信息**：
```
FileNotFoundError: [Errno 2] No such file or directory: 'ffmpeg'
```

**解决方法**：
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get install ffmpeg

# 验证安装
ffmpeg -version
```

### 4. 测试超时

**错误信息**：
```
流程超时 (超过120秒)
```

**解决方法**：
- 增加 `NETWORK_TIMEOUT` 值
- 检查网络速度
- 选择较短的测试视频

### 5. OSS URL不可访问

**错误信息**：
```
关键帧1 URL不可访问: 请求超时
```

**解决方法**：
- 检查OSS Bucket访问权限设置
- 确认Bucket是否设置为公共读
- 检查OSS防火墙规则

## 🔍 调试技巧

### 启用详细日志

编辑 `app/core/logging.py` 设置日志级别为 `DEBUG`：

```python
logger.setLevel(logging.DEBUG)
```

### 跳过特定测试

```bash
# 跳过URL可访问性测试
pytest app/tests/test_video_to_oss_pipeline.py -v -s -k "not accessibility"

# 只运行OSS服务检查
pytest app/tests/test_video_to_oss_pipeline.py::test_oss_service_availability -v -s
```

### 保留临时文件

注释掉清理测试以保留临时文件用于调试：

```bash
pytest app/tests/test_video_to_oss_pipeline.py -v -s -k "not cleanup"
```

## 📈 性能基准

预期性能指标（取决于网络和视频长度）：

| 阶段 | 预期耗时 | 说明 |
|------|---------|------|
| OSS服务检查 | < 1秒 | 快速配置验证 |
| YouTube下载 | 10-60秒 | 取决于视频大小和网络速度 |
| 关键帧提取 | 5-20秒 | 取决于视频长度 |
| OSS上传 | 2-10秒 | 取决于文件大小和网络速度 |
| URL可访问性 | 5-15秒 | 每个URL约1秒 |
| 临时文件清理 | < 1秒 | 快速文件删除 |
| **总计** | **30-120秒** | 完整流程 |

## 🎯 成功标准

测试通过需满足：

✅ OSS服务配置正确且可用  
✅ YouTube视频成功下载  
✅ 提取了1-10个关键帧  
✅ 视频和所有关键帧成功上传到OSS  
✅ 所有OSS URL格式正确  
✅ 所有OSS URL可访问（HTTP 200）  
✅ 临时文件完全清理  

## 📞 获取帮助

如果遇到问题：

1. 查看 `backend/TEST_OSS_PIPELINE_RESULTS.md` 详细报告
2. 检查 `backend/logs/` 目录下的日志文件
3. 运行单元测试确认各模块独立功能：
   ```bash
   pytest app/tests/test_video_service.py -v
   pytest app/tests/test_oss_service.py -v
   ```

---

**祝测试顺利！** 🚀
