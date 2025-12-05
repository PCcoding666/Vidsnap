# 视频上传处理失败诊断方案 - 主索引

> **版本**: v1.0  
> **更新日期**: 2025-01-15  
> **适用环境**: YouTube 视频智能总结系统 (FastAPI + React + 阿里云)

---

## 📋 快速导航

| 文档 | 用途 | 适用场景 |
|------|------|---------|
| [VIDEO_UPLOAD_FLOW.md](./VIDEO_UPLOAD_FLOW.md) | 完整链路梳理 | 理解系统架构，定位故障环节 |
| [LOGGING_STRATEGY.md](./LOGGING_STRATEGY.md) | 日志策略设计 | 增强日志记录，追踪问题根源 |
| [SERVER_CHECKLIST.md](./SERVER_CHECKLIST.md) | 服务器环境检查清单 | 验证部署环境配置 |
| [MINIMAL_TEST_CASES.md](./MINIMAL_TEST_CASES.md) | 最小化测试用例 | 隔离测试，快速定位问题 |
| [DIAGNOSTIC_TOOLS.md](./DIAGNOSTIC_TOOLS.md) | 诊断工具与监控 | 实时监控，性能分析 |

---

## 🎯 诊断流程决策树

```
┌─────────────────────────────────┐
│   视频上传处理失败问题          │
└─────────────────────────────────┘
                │
                ▼
        问题症状分类?
                │
    ┌───────────┼───────────┬──────────────┐
    │           │           │              │
    ▼           ▼           ▼              ▼
 上传中断    处理失败    超时错误      偶发性失败
    │           │           │              │
    ▼           ▼           ▼              ▼
 网络层       存储层      配置层         综合诊断
 诊断         诊断        诊断           流程
```

### 问题分类与定位指南

#### 1️⃣ **上传中断** (文件未完整到达服务器)
- **症状**: 
  - 前端显示上传进度条停止
  - 后端日志无接收记录或仅部分接收
  - 浏览器控制台显示网络错误
  
- **优先检查**:
  1. [SERVER_CHECKLIST.md](./SERVER_CHECKLIST.md) → **4.3 反向代理配置**
  2. [DIAGNOSTIC_TOOLS.md](./DIAGNOSTIC_TOOLS.md) → **6.1 网络层诊断**
  3. [MINIMAL_TEST_CASES.md](./MINIMAL_TEST_CASES.md) → **5.1 大文件上传测试**

- **常见原因**:
  - Nginx `client_max_body_size` 限制过小
  - 上传超时设置不足
  - 网络不稳定（代理、防火墙）

#### 2️⃣ **处理失败** (文件已到达但处理异常)
- **症状**:
  - 后端日志显示接收成功但后续步骤失败
  - FastAPI 返回 500 错误
  - 临时文件存在但无法读取或损坏
  
- **优先检查**:
  1. [VIDEO_UPLOAD_FLOW.md](./VIDEO_UPLOAD_FLOW.md) → **2.3 管道处理阶段**
  2. [LOGGING_STRATEGY.md](./LOGGING_STRATEGY.md) → **3.2 关键节点日志**
  3. [SERVER_CHECKLIST.md](./SERVER_CHECKLIST.md) → **4.1 文件系统检查**

- **常见原因**:
  - 磁盘空间不足
  - 临时目录权限问题
  - OSS 上传失败（凭证、网络）
  - 视频格式不支持或损坏

#### 3️⃣ **超时错误** (处理时间过长)
- **症状**:
  - 前端显示 "Request Timeout"
  - 后端日志显示处理中但未返回
  - 网关 502/504 错误
  
- **优先检查**:
  1. [SERVER_CHECKLIST.md](./SERVER_CHECKLIST.md) → **4.2 Web 服务器配置**
  2. [VIDEO_UPLOAD_FLOW.md](./VIDEO_UPLOAD_FLOW.md) → **2.5 异常点分析**
  3. [DIAGNOSTIC_TOOLS.md](./DIAGNOSTIC_TOOLS.md) → **6.3 性能分析**

- **常见原因**:
  - Nginx `proxy_read_timeout` 不足
  - 大视频文件处理时间超过限制
  - AI 服务响应慢（Paraformer-v2/Qwen3-VL）
  - 网络代理延迟

#### 4️⃣ **偶发性失败** (有时成功有时失败) ⭐ **重点关注**
- **症状**:
  - 相同文件有时上传成功，有时失败
  - 不同时间段成功率不同
  - 无明显规律性
  
- **优先检查**:
  1. [DIAGNOSTIC_TOOLS.md](./DIAGNOSTIC_TOOLS.md) → **6.4 实时监控方案**
  2. [MINIMAL_TEST_CASES.md](./MINIMAL_TEST_CASES.md) → **5.4 环境对比测试**
  3. [LOGGING_STRATEGY.md](./LOGGING_STRATEGY.md) → **3.3 结构化日志格式**

- **常见原因**:
  - 网络波动（特别是代理网络）
  - 服务器资源竞争（并发请求）
  - OSS 服务间歇性不可达
  - 临时目录空间不足但未触发硬限制
  - 依赖服务限流（DashScope API）

---

## 🔍 综合诊断流程（推荐）

### Step 1: 环境验证 (15分钟)
```bash
# 1. 执行服务器检查清单
cd /root/my_youtube_summarizer/backend
bash app/tests/diagnostics_check_server.sh  # 见 SERVER_CHECKLIST.md

# 2. 检查关键服务状态
curl http://localhost:8000/video/status
```
📖 参考: [SERVER_CHECKLIST.md](./SERVER_CHECKLIST.md)

### Step 2: 日志增强 (30分钟)
```bash
# 1. 部署增强日志配置
# 编辑 backend/app/api/routes/video.py 和 pipeline_service.py
# 添加结构化日志（见 LOGGING_STRATEGY.md 第3章）

# 2. 启动实时日志监控
tail -f backend/logs/app.log | grep -E "upload|OSS|pipeline"
```
📖 参考: [LOGGING_STRATEGY.md](./LOGGING_STRATEGY.md)

### Step 3: 最小化测试 (1小时)
```bash
# 1. 执行基础上传测试
cd /root/my_youtube_summarizer/backend
pytest app/tests/test_upload_isolation.py -v  # 见 MINIMAL_TEST_CASES.md

# 2. 执行压力测试（模拟偶发性问题）
python app/tests/stress_test_upload.py --count 20
```
📖 参考: [MINIMAL_TEST_CASES.md](./MINIMAL_TEST_CASES.md)

### Step 4: 持续监控 (24-48小时)
```bash
# 部署监控脚本（自动记录失败情况）
nohup python app/tests/monitor_upload_health.py > monitor.log 2>&1 &
```
📖 参考: [DIAGNOSTIC_TOOLS.md](./DIAGNOSTIC_TOOLS.md)

### Step 5: 数据分析与定位
- 收集监控数据后，分析失败模式
- 对比成功/失败案例的日志差异
- 使用决策树定位具体问题层

---

## 📊 核心概念

### 系统架构简图

```
┌─────────────┐
│   前端 UI   │  React (port 8080)
│  文件上传   │
└──────┬──────┘
       │ HTTP POST (multipart/form-data)
       │
       ▼
┌─────────────────────────────────────────────┐
│            Nginx 反向代理                   │
│  - client_max_body_size                    │
│  - proxy_read_timeout                      │
└──────┬──────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────┐
│         FastAPI 后端 (port 8000)           │
│  /video/process                            │
│    ├─ UploadFile 接收                      │
│    ├─ 临时文件保存 (/tmp/session_xxx)     │
│    └─ AliyunVideoProcessingPipeline       │
└──────┬──────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────┐
│      视频处理管道 (pipeline_service.py)    │
│  1. 视频文件验证                           │
│  2. 关键帧提取 (PySceneDetect)             │
│  3. 音频提取 (ffmpeg)                      │
│  4. 音频转录 (Paraformer-v2)               │
│  5. 视频分析 (Qwen3-VL-Flash)              │
└──────┬──────────────────────────────────────┘
       │
       ├──────────────────┬──────────────────┐
       ▼                  ▼                  ▼
┌─────────────┐  ┌────────────────┐  ┌──────────────┐
│ 阿里云 OSS  │  │ DashScope API  │  │  Supabase DB │
│ 文件存储    │  │ AI 服务        │  │  元数据存储  │
└─────────────┘  └────────────────┘  └──────────────┘
```

### 关键术语表

| 术语 | 说明 |
|------|------|
| **video_id** | 每个上传任务的唯一标识符 (UUID) |
| **session_temp_dir** | 临时会话目录，格式: `/tmp/aliyun_video_service/session_{video_id}` |
| **UploadFile** | FastAPI 的文件上传对象，包含文件名、大小、内容流 |
| **OSS (Object Storage Service)** | 阿里云对象存储服务 |
| **Paraformer-v2** | 阿里云 DashScope 语音转录模型 |
| **Qwen3-VL-Flash** | 阿里云 DashScope 视频理解模型 |
| **pipeline** | 视频处理管道，协调所有处理步骤 |
| **metadata** | 视频元数据，包含转录、关键帧、总结等信息 |

### 故障等级定义

| 等级 | 影响范围 | 响应时间 | 示例 |
|------|---------|---------|------|
| **P0 - 紧急** | 100% 用户无法上传 | 立即 (< 1h) | 服务器宕机、OSS 不可用 |
| **P1 - 严重** | 50%+ 用户受影响 | 4 小时内 | 偶发性失败率 > 50% |
| **P2 - 重要** | < 50% 用户受影响 | 24 小时内 | 特定文件格式失败 |
| **P3 - 一般** | 个别用户反馈 | 72 小时内 | 特殊边界条件 |

---

## 🛠️ 快速工具链接

### 直接可执行的诊断命令

```bash
# 检查服务状态
curl http://localhost:8000/video/status

# 查看最近的错误日志
tail -100 backend/logs/app.log | grep -i "error\|fail"

# 测试 OSS 连接
python -c "from backend.app.services.oss_service import oss_service; print(oss_service.is_available())"

# 测试临时目录权限
touch /tmp/aliyun_video_service/test_file && rm /tmp/aliyun_video_service/test_file && echo "OK"

# 检查磁盘空间
df -h /tmp

# 检查网络到阿里云的连通性
curl -I https://oss-cn-beijing.aliyuncs.com
```

### 推荐的监控指标

| 指标 | 正常值 | 告警阈值 | 监控方法 |
|------|--------|---------|---------|
| 上传成功率 | > 95% | < 90% | 日志统计 |
| 平均处理时间 | < 60s (小文件) | > 180s | 日志时间戳差 |
| OSS 上传成功率 | > 98% | < 95% | oss_service 日志 |
| 磁盘空间 (/tmp) | > 10GB | < 5GB | `df -h` |
| 并发上传数 | < 5 | > 10 | 进程监控 |

---

## 📞 常见问题速查

### Q1: 如何确认问题出现在哪个环节？
**A**: 按照以下顺序检查日志关键字：
1. `收到视频处理请求` - FastAPI 是否收到请求
2. `开始保存上传的视频文件` - 文件是否开始保存
3. `已保存上传的视频文件` - 文件是否完整保存
4. `开始处理视频管道` - 管道是否启动
5. `开始上传视频文件` (OSS) - 是否开始云存储

### Q2: 偶发性失败如何复现？
**A**: 使用压力测试模拟：
```bash
# 并发上传 20 次相同文件
for i in {1..20}; do
  curl -X POST http://localhost:8000/video/process \
    -F "video_file=@test.mp4" &
done
wait
```

### Q3: 如何区分是网络问题还是服务器问题？
**A**: 执行对比测试：
1. 本地环境测试（localhost）
2. 服务器环境无代理测试
3. 服务器环境有代理测试
4. 对比成功率差异

### Q4: 日志中看到 "OSS服务不可用" 怎么办？
**A**: 检查顺序：
1. 验证 `.env` 文件中 OSS 配置是否正确
2. 测试网络到 OSS endpoint 的连通性
3. 验证 AccessKey 权限
4. 查看 OSS 控制台是否有异常

---

## 📚 文档版本历史

| 版本 | 日期 | 变更说明 |
|------|------|---------|
| v1.0 | 2025-01-15 | 初始版本，包含完整诊断流程 |

---

## 📝 反馈与改进

如发现文档不足或有改进建议，请：
1. 记录实际诊断过程中遇到的问题
2. 补充新的故障案例到对应文档
3. 更新决策树和快速导航

**文档维护**: 每次重大故障解决后更新对应章节
