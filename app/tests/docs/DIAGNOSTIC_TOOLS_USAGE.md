# 视频上传诊断工具使用指南

> 完整的视频上传故障诊断工具系统，帮助快速定位和解决上传失败问题

---

## 📋 工具清单

本诊断系统包含以下工具：

| 工具 | 文件 | 功能 |
|------|------|------|
| 🔍 服务器环境检查 | `check_server_environment.sh` | 检查服务器配置、资源、网络等 |
| 🧪 上传测试 | `test_upload_diagnostics.sh` | 测试不同场景的视频上传功能 |
| 🩺 综合诊断 | `diagnose_upload_failure.sh` | 综合故障诊断和定位 |
| 📊 日志分析 | `analyze_upload_logs.py` | 分析日志文件，提取失败模式 |
| 📡 实时监控 | `monitor_upload_realtime.sh` | 实时监控上传过程和系统资源 |

---

## 🚀 快速开始

### 1. 快速诊断（推荐第一步）

如果遇到上传失败问题，首先运行综合诊断工具：

```bash
bash app/tests/diagnose_upload_failure.sh
```

这会自动检查：
- ✅ 服务器环境配置
- ✅ 网络连接状态
- ✅ Python 环境和依赖
- ✅ 配置文件完整性
- ✅ FastAPI 服务状态
- ✅ 实际上传测试（full 模式）

**示例输出：**
```
╔═══════════════════════════════════════════════════════════════╗
║         视频上传故障综合诊断工具 v1.0                          ║
╚═══════════════════════════════════════════════════════════════╝

=== 步骤 1: 服务器环境检查 ===
[✓] /tmp 可用空间: 25GB
[✓] /tmp 目录可写
[✓] 可用内存: 8GB

=== 步骤 2: 网络连通性检查 ===
[✓] OSS 连接正常 (HTTP 200)
[✓] DashScope 连接正常 (HTTP 200)

系统健康度: 95%
系统状态: 优秀
```

---

### 2. 详细环境检查

如果需要更详细的服务器环境报告：

```bash
# 基本检查
bash app/tests/check_server_environment.sh

# JSON 格式输出
bash app/tests/check_server_environment.sh --json

# 保存到日志文件
bash app/tests/check_server_environment.sh --log server_check.log

# 详细输出
bash app/tests/check_server_environment.sh --verbose
```

**检查内容包括：**
- 📁 磁盘空间和 inode 使用率
- 🔐 文件权限检查
- 💾 系统资源限制 (ulimit)
- 🌐 网络连接状态
- 🐍 Python 环境和依赖
- ⚙️ 配置文件完整性
- 🚀 FastAPI 服务状态

---

### 3. 上传功能测试

测试不同场景下的上传功能：

```bash
# 测试小文件上传 (<10MB)
bash app/tests/test_upload_diagnostics.sh small

# 测试中等文件 (10-100MB)
bash app/tests/test_upload_diagnostics.sh medium

# 测试大文件 (>100MB)
bash app/tests/test_upload_diagnostics.sh large

# 测试并发上传
bash app/tests/test_upload_diagnostics.sh concurrent

# 运行所有测试
bash app/tests/test_upload_diagnostics.sh all

# 保留测试文件用于分析
bash app/tests/test_upload_diagnostics.sh all --keep-files

# 指定API地址
bash app/tests/test_upload_diagnostics.sh small --api-url http://server:8000
```

**测试报告示例：**
```
========== 上传结果 ==========
HTTP 状态码: 200
上传耗时: 2.35秒
上传速度: 4.26MB/s

========== API 响应 ==========
{
  "status": "success",
  "video_id": "abc123",
  "message": "视频处理完成"
}

[✓ PASS] 小文件上传 - 上传成功
```

---

### 4. 日志分析

分析历史日志，查找失败模式：

```bash
# 分析日志文件
python3 app/tests/analyze_upload_logs.py --log-file /var/log/app.log

# 分析最近12小时的日志
python3 app/tests/analyze_upload_logs.py --time-range 12

# JSON格式输出
python3 app/tests/analyze_upload_logs.py --format json --output report.json

# HTML报告
python3 app/tests/analyze_upload_logs.py --format html --output report.html

# 详细输出
python3 app/tests/analyze_upload_logs.py --verbose
```

**分析报告示例：**
```
📊 日志分析报告
=========================================

📈 基本统计
  分析时间范围: 最近 24 小时
  总日志条目: 1523
  总错误数: 15
  上传相关错误: 5
  受影响的请求: 3

🔴 错误类型分布
  HTTPException              3 ( 60.0%)
  FileNotFoundError          1 ( 20.0%)
  OSError                    1 ( 20.0%)

💬 常见错误信息
  [2次] 视频处理失败: HTTPException - 磁盘空间不足
  [1次] 无法保存临时文件: OSError - Permission denied
```

---

### 5. 实时监控

在上传过程中实时监控系统状态：

```bash
# 启动实时监控（默认2秒刷新）
bash app/tests/monitor_upload_realtime.sh

# 设置刷新间隔为5秒
bash app/tests/monitor_upload_realtime.sh --interval 5

# 监控5分钟后自动停止
bash app/tests/monitor_upload_realtime.sh --duration 300

# 监控指定日志文件
bash app/tests/monitor_upload_realtime.sh --log-file /var/log/app.log
```

**监控界面示例：**
```
╔═══════════════════════════════════════════════════════════════╗
║         视频上传实时监控工具                                   ║
╚═══════════════════════════════════════════════════════════════╝

监控时间: 2025-12-05 17:25:30
刷新间隔: 2秒

=== 磁盘空间 ===
/tmp 目录:
  总空间:   50.00GB
  已使用:   15.00GB (30%)
  可用:     35.00GB
  使用率:   [████████████░░░░░░░░░░░░░░░░░░░░] 30%

=== 系统资源 ===
CPU 使用率: 15.2%
内存使用:
  总内存:   16.00GB
  已使用:   8.50GB (53%)
  可用:     7.50GB
  使用率:   [█████████████████████░░░░░░░░░░░] 53%

=== FastAPI 进程 ===
✓ FastAPI 服务运行中
  PID:      12345
  CPU:      2.5%
  内存:     3.2%
  运行时间: 02:15:30

按 Ctrl+C 停止监控
```

---

## 🔧 高级用法

### 场景 1: 偶发性上传失败

**问题描述：** 上传有时成功，有时失败，不稳定

**诊断步骤：**

1. **运行综合诊断**
   ```bash
   bash app/tests/diagnose_upload_failure.sh --full --report diagnosis.txt
   ```

2. **并发测试**
   ```bash
   bash app/tests/test_upload_diagnostics.sh concurrent --verbose
   ```

3. **实时监控 + 测试**
   ```bash
   # 终端1: 启动监控
   bash app/tests/monitor_upload_realtime.sh
   
   # 终端2: 运行测试
   bash app/tests/test_upload_diagnostics.sh all
   ```

4. **分析日志**
   ```bash
   python3 app/tests/analyze_upload_logs.py --time-range 6 --format html --output report.html
   ```

---

### 场景 2: 大文件上传失败

**问题描述：** 小文件可以上传，大文件总是失败

**诊断步骤：**

1. **检查磁盘空间**
   ```bash
   bash app/tests/check_server_environment.sh | grep -A 5 "磁盘空间"
   ```

2. **测试不同大小文件**
   ```bash
   bash app/tests/test_upload_diagnostics.sh small
   bash app/tests/test_upload_diagnostics.sh medium
   bash app/tests/test_upload_diagnostics.sh large
   ```

3. **监控资源使用**
   ```bash
   bash app/tests/monitor_upload_realtime.sh --interval 1
   ```

---

### 场景 3: 性能问题诊断

**问题描述：** 上传成功但速度很慢

**诊断步骤：**

1. **检查网络连接**
   ```bash
   bash app/tests/check_server_environment.sh | grep -A 10 "网络连接"
   ```

2. **性能测试**
   ```bash
   bash app/tests/test_upload_diagnostics.sh small --verbose
   ```

3. **查看API性能指标**
   ```bash
   curl http://localhost:8000/metrics | jq '.'
   ```

---

## 📊 性能监控 API

系统已集成性能监控中间件，可通过 API 查看实时指标：

```bash
# 获取性能指标
curl http://localhost:8000/metrics

# 美化输出
curl http://localhost:8000/metrics | jq '.'
```

**响应示例：**
```json
{
  "uptime_seconds": 3600,
  "total_requests": 150,
  "total_errors": 5,
  "error_rate": 3.33,
  "avg_response_time": 1.25,
  "requests_per_second": 0.042,
  "status_codes": {
    "200": 140,
    "400": 3,
    "500": 2
  },
  "endpoints": {
    "POST /video/process": {
      "count": 50,
      "avg_time": 2.5,
      "min_time": 1.2,
      "max_time": 5.8,
      "error_rate": 4.0
    }
  },
  "system_resources": {
    "memory_rss_mb": 256.5,
    "cpu_percent": 12.3,
    "num_threads": 8
  }
}
```

---

## 🐛 常见问题排查

### 问题: 磁盘空间不足

**症状：**
```
[✗] /tmp 可用空间不足: 2GB
```

**解决方案：**
```bash
# 清理临时文件
rm -rf /tmp/aliyun_video_service/*

# 清理系统临时文件
sudo rm -rf /tmp/*

# 验证
df -h /tmp
```

---

### 问题: Python 依赖缺失

**症状：**
```
[✗] psutil 未安装
```

**解决方案：**
```bash
cd backend
pip install -r requirements.txt

# 验证
python3 -c "import psutil; print('OK')"
```

---

### 问题: FastAPI 服务未运行

**症状：**
```
[✗] FastAPI 服务未运行 (HTTP 000)
```

**解决方案：**
```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 或使用脚本
bash app/tests/run_fastapi.sh
```

---

### 问题: OSS 连接失败

**症状：**
```
[✗] OSS 连接失败
```

**解决方案：**
```bash
# 检查网络
ping oss-cn-beijing.aliyuncs.com

# 检查代理设置
echo $http_proxy
echo $https_proxy

# 检查配置
grep OSS_ .env
```

---

## 📝 日志增强说明

系统已增强日志功能，现在支持：

### 结构化日志

所有日志包含丰富的上下文信息：
- 📌 请求ID（自动生成，用于追踪）
- 👤 用户ID
- 📁 文件元数据（名称、大小）
- ⏱️ 性能指标（耗时、速度）
- 📊 资源使用（内存、CPU）
- 🔴 错误详情（类型、堆栈）

### 日志格式

**彩色控制台输出：**
```
[2025-12-05T17:30:15] [a3f4b2c1] INFO - 🎬 收到视频处理请求
[2025-12-05T17:30:15] [a3f4b2c1] INFO - 📤 开始保存上传的视频文件
[2025-12-05T17:30:18] [a3f4b2c1] INFO - ⏱️ 性能指标 - 文件上传完成: 3250.50ms
[2025-12-05T17:30:18] [a3f4b2c1] INFO - 📊 资源使用 - 文件上传完成: 内存=245.32MB, CPU=15.2%
```

**JSON格式（文件日志）：**
```json
{
  "timestamp": "2025-12-05T17:30:15",
  "level": "INFO",
  "message": "收到视频处理请求",
  "request_id": "a3f4b2c1",
  "module": "video",
  "extra": {
    "client_host": "192.168.1.100",
    "file_name": "test.mp4",
    "file_size": 10485760
  }
}
```

---

## 🎯 最佳实践

1. **定期检查环境**
   ```bash
   # 每周运行一次环境检查
   bash app/tests/check_server_environment.sh --log weekly_check.log
   ```

2. **监控关键指标**
   ```bash
   # 定期查看性能指标
   curl http://localhost:8000/metrics | jq '.error_rate, .avg_response_time'
   ```

3. **分析历史日志**
   ```bash
   # 每天分析日志趋势
   python3 app/tests/analyze_upload_logs.py --format html --output daily_report.html
   ```

4. **压力测试**
   ```bash
   # 部署前运行完整测试
   bash app/tests/test_upload_diagnostics.sh all --keep-files
   ```

---

## 📞 获取帮助

所有工具都支持 `--help` 参数查看详细帮助：

```bash
bash app/tests/check_server_environment.sh --help
bash app/tests/test_upload_diagnostics.sh --help
bash app/tests/diagnose_upload_failure.sh --help
python3 app/tests/analyze_upload_logs.py --help
bash app/tests/monitor_upload_realtime.sh --help
```

---

## ✅ 验证清单

部署后验证所有工具可正常运行：

- [ ] 环境检查脚本可执行
- [ ] 上传测试脚本可执行
- [ ] 综合诊断工具可执行
- [ ] 日志分析工具可执行
- [ ] 实时监控脚本可执行
- [ ] API性能指标可访问
- [ ] 日志包含请求ID
- [ ] 日志包含性能指标

---

**文档版本:** v1.0  
**最后更新:** 2025-12-05  
**维护者:** 视频分析平台开发团队
