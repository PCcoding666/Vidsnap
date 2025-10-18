# Gradio 应用快速启动指南

## 🚀 一键启动

### 1. 安装依赖（首次运行）

```bash
cd backend
pip install -r requirements.txt
```

### 2. 确保环境变量已配置

检查项目根目录的 `.env` 文件是否包含：

```bash
# 必需配置
OSS_ACCESS_KEY_ID=your_key
OSS_ACCESS_KEY_SECRET=your_secret
OSS_BUCKET=your_bucket
OSS_ENDPOINT=oss-cn-beijing.aliyuncs.com

# API 密钥（至少一个）
QWEN_API_KEY=your_api_key
```

### 3. 启动应用

```bash
cd backend
./run_gradio.sh
```

或者使用 Python 直接运行：

```bash
cd backend
export https_proxy=http://127.0.0.1:33210
export http_proxy=http://127.0.0.1:33210
export all_proxy=socks5://127.0.0.1:33211
python3 gradio_app.py
```

### 4. 访问界面

在浏览器中打开：**http://127.0.0.1:7860**

---

## 📖 使用流程

### YouTube 视频分析

1. 选择"YouTube URL"模式
2. 粘贴视频链接（例如：`https://www.youtube.com/watch?v=xxxxx`）
3. 选择参数：
   - 语言：自动检测
   - 粒度：标准
   - 关键帧：10
4. 点击"🚀 开始分析"
5. 等待处理完成（约 2-5 分钟）
6. 在"结果展示"标签页查看：
   - 📝 简要总结
   - 📖 标准总结
   - 🎤 音频转录
   - 🖼️ 关键帧

### 本地视频上传

1. 选择"本地视频上传"模式
2. 点击上传区域选择文件（支持 MP4/AVI/MOV/MKV）
3. 配置参数
4. 点击"🚀 开始分析"
5. 查看结果

---

## 🎯 推荐配置

### 快速测试（短视频 < 5分钟）
- **粒度**: 简要
- **关键帧**: 5-8
- **预计耗时**: 1-2 分钟

### 日常使用（中等视频 5-15分钟）
- **粒度**: 标准
- **关键帧**: 10-12
- **预计耗时**: 3-5 分钟

### 深度分析（长视频或会议）
- **粒度**: 详细
- **关键帧**: 15-20
- **预计耗时**: 5-10 分钟

---

## ⚠️ 常见问题

### Q: 启动时提示 "Gradio 未安装"？
**A**: 运行 `pip install gradio>=4.0.0 httpx[socks]>=0.24.0`

### Q: 处理失败提示 "API 密钥无效"？
**A**: 检查 `.env` 文件中的 `QWEN_API_KEY` 是否正确

### Q: YouTube 视频下载失败？
**A**: 
- 检查视频链接是否正确
- 确认视频不是私有或地区限制
- 检查代理设置

### Q: 端口被占用？
**A**: 使用自定义端口：`./run_gradio.sh --port 8080`

---

## 📚 详细文档

完整使用指南请参考：[GRADIO_USER_GUIDE.md](./GRADIO_USER_GUIDE.md)

---

**享受智能视频分析！** 🎉
