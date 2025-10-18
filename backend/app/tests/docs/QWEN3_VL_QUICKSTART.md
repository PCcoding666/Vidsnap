# Qwen3-VL-Flash 快速开始指南

## 5 分钟快速上手

### 第 1 步: 配置环境变量

编辑 `backend/.env` 文件：

```bash
# 阿里云 OSS 配置
ALIYUN_ACCESS_KEY_ID=your_access_key_id
ALIYUN_ACCESS_KEY_SECRET=your_access_key_secret
ALIYUN_OSS_ENDPOINT=oss-cn-beijing.aliyuncs.com
ALIYUN_OSS_BUCKET=your_bucket_name

# Qwen API 密钥
QWEN_API_KEY=sk-your-qwen-api-key
```

### 第 2 步: 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 第 3 步: 测试服务可用性

```bash
cd app/tests
./run_complete_pipeline_test.sh
```

### 第 4 步: 使用 API

#### Python 示例

```python
from app.services.pipeline_service import pipeline

# 处理 YouTube 视频
result = await pipeline.process_video_with_summary(
    youtube_url="https://www.youtube.com/watch?v=Gdzm0-8_61c",
    granularity="standard"
)

print(result["video_summary"]["brief_summary"])
```

#### cURL 示例

```bash
curl -X POST "http://localhost:8000/analysis/summarize" \
  -H "Content-Type: application/json" \
  -d '{
    "youtube_url": "https://www.youtube.com/watch?v=Gdzm0-8_61c",
    "granularity": "standard"
  }'
```

## 总结粒度说明

### brief (简要)
- 1-2 句话总结
- 适合快速浏览
- 耗时: ~5 秒

### standard (标准)
- 100-200 字段落
- 包含主要内容要点
- 耗时: ~15 秒

### detailed (详细)
- 300-500 字分段总结
- 完整的内容解析
- 耗时: ~30 秒

## 常用命令

```bash
# 检查服务状态
curl http://localhost:8000/analysis/services/status

# 运行单元测试
python -m pytest app/tests/test_complete_pipeline.py -v

# 查看日志
tail -f logs/video_analysis.log
```

## 故障排查

### 问题: API 密钥无效

```bash
# 检查环境变量
echo $QWEN_API_KEY

# 重新加载环境变量
source backend/.env
```

### 问题: OSS 访问失败

```bash
# 测试 OSS 连接
python -c "from app.services.oss_service import oss_service; print(oss_service.is_available())"
```

### 问题: 测试失败

```bash
# 查看详细错误
python -m pytest app/tests/test_complete_pipeline.py -v -s --tb=long
```

## 文件位置速查

| 文件类型 | 路径 |
|---------|------|
| LLM 服务 | `app/services/llm_service.py` |
| 数据模型 | `app/models/analysis.py` |
| 管道服务 | `app/services/pipeline_service.py` |
| API 路由 | `app/api/routes/analysis.py` |
| 集成测试 | `app/tests/test_complete_pipeline.py` |
| 测试脚本 | `app/tests/run_complete_pipeline_test.sh` |
| 完整文档 | `app/tests/docs/QWEN3_VL_INTEGRATION_GUIDE.md` |

## 下一步

1. ✅ 阅读完整文档: `QWEN3_VL_INTEGRATION_GUIDE.md`
2. ✅ 运行端到端测试验证集成
3. ✅ 尝试不同的总结粒度
4. ✅ 自定义提示词优化总结质量
5. ✅ 集成到前端界面

---

**帮助**: 查看 `QWEN3_VL_INTEGRATION_GUIDE.md` 获取详细信息
