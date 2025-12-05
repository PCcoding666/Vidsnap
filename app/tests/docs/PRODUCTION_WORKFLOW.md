# 生产环境部署与日志管理工作流

## 当前问题
在服务器上运行服务时，无法像本地开发那样实时查看日志，难以追踪错误和调试问题。

## 解决方案

### 1. 日志系统配置

后端已配置完整的日志系统 (`backend/app/core/logging.py`):
- ✅ 结构化JSON日志
- ✅ 请求追踪 (request_id)
- ✅ 性能监控
- ✅ 彩色控制台输出

### 2. 生产环境部署方式

#### 方式A: 使用systemd服务 (推荐生产环境)

**优点**:
- 开机自动启动
- 自动重启故障服务
- 统一的日志管理
- 系统级别的进程管理

**步骤**:

```bash
# 1. 复制service文件
sudo cp /root/my_youtube_summarizer/app/tests/docs/vidsnap-backend.service /etc/systemd/system/

# 2. 创建日志目录
mkdir -p /root/my_youtube_summarizer/backend/logs

# 3. 重新加载systemd
sudo systemctl daemon-reload

# 4. 启动服务
sudo systemctl start vidsnap-backend

# 5. 设置开机自启动
sudo systemctl enable vidsnap-backend

# 6. 查看服务状态
sudo systemctl status vidsnap-backend

# 7. 查看实时日志
sudo journalctl -u vidsnap-backend -f

# 8. 查看最近的错误
sudo journalctl -u vidsnap-backend -p err -n 50
```

#### 方式B: 使用tmux/screen (当前使用)

**优点**:
- 快速开发调试
- 可以attach查看实时输出
- 灵活性高

**步骤**:

```bash
# 1. 停止当前服务 (如果在后台运行)
# 找到进程ID
ps aux | grep uvicorn
# 杀掉进程
kill -9 <PID>

# 2. 使用tmux启动
tmux new -s backend
cd /root/my_youtube_summarizer/backend
/root/my_youtube_summarizer/app/tests/run_backend_production.sh

# 3. 分离tmux会话: Ctrl+B, 然后按 D

# 4. 重新连接查看日志
tmux attach -t backend

# 5. 杀掉tmux会话
tmux kill-session -t backend
```

### 3. 查看日志的方法

#### 3.1 使用自定义日志查看器 (推荐)

```bash
# 实时跟踪所有日志
/root/my_youtube_summarizer/app/tests/view_logs.sh -f

# 查看最近100条错误
/root/my_youtube_summarizer/app/tests/view_logs.sh -e -n 100

# 搜索特定关键词
/root/my_youtube_summarizer/app/tests/view_logs.sh -s "video upload"

# 按request_id查看特定请求的所有日志
/root/my_youtube_summarizer/app/tests/view_logs.sh -r abc12345

# 只看今天的日志
/root/my_youtube_summarizer/app/tests/view_logs.sh -t -n 200
```

#### 3.2 直接使用tail命令

```bash
# 实时跟踪应用日志
tail -f /root/my_youtube_summarizer/backend/logs/app.log

# 查看最近50行
tail -n 50 /root/my_youtube_summarizer/backend/logs/app.log

# 查看错误日志
tail -f /root/my_youtube_summarizer/backend/logs/error.log
```

#### 3.3 使用jq格式化JSON日志

```bash
# 格式化显示JSON日志
tail -n 20 /root/my_youtube_summarizer/backend/logs/app.log | jq '.'

# 只显示错误级别的日志
cat /root/my_youtube_summarizer/backend/logs/app.log | jq 'select(.level=="ERROR")'

# 显示特定request_id的所有日志
cat /root/my_youtube_summarizer/backend/logs/app.log | jq 'select(.request_id=="abc12345")'
```

### 4. 推荐的开发-生产工作流

#### 开发阶段
```bash
# 使用后台进程启动,可以通过BashOutput查看
cd /root/my_youtube_summarizer/backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &

# 或使用前台启动，直接看到输出
./app/tests/run_fastapi.sh
```

#### 测试阶段
```bash
# 使用tmux启动，方便随时查看
tmux new -s backend
/root/my_youtube_summarizer/app/tests/run_backend_production.sh
```

#### 生产环境
```bash
# 使用systemd服务
sudo systemctl restart vidsnap-backend
sudo journalctl -u vidsnap-backend -f
```

### 5. 调试错误的完整流程

当用户报告错误（如视频上传失败）时:

```bash
# 1. 查看最近的错误日志
/root/my_youtube_summarizer/app/tests/view_logs.sh -e -n 50

# 2. 如果知道大概时间，查看那段时间的日志
tail -n 500 /root/my_youtube_summarizer/backend/logs/app.log | grep "video"

# 3. 如果前端返回了request_id，直接追踪
/root/my_youtube_summarizer/app/tests/view_logs.sh -r <request_id>

# 4. 查看完整的异常堆栈
cat /root/my_youtube_summarizer/backend/logs/app.log | jq 'select(.exception != null)'

# 5. 修复代码后重启服务
sudo systemctl restart vidsnap-backend
# 或
tmux attach -t backend  # Ctrl+C 停止, 然后重新运行
```

### 6. 日志轮转配置

为避免日志文件过大，建议配置logrotate:

```bash
# 创建logrotate配置
sudo cat > /etc/logrotate.d/vidsnap << 'EOF'
/root/my_youtube_summarizer/backend/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 644 root root
    postrotate
        systemctl reload vidsnap-backend > /dev/null 2>&1 || true
    endscript
}
EOF
```

### 7. 监控告警

可以添加简单的监控脚本:

```bash
#!/bin/bash
# /root/my_youtube_summarizer/app/tests/check_errors.sh
ERROR_COUNT=$(tail -n 1000 /root/my_youtube_summarizer/backend/logs/app.log | grep -c '"level":"ERROR"')

if [ $ERROR_COUNT -gt 10 ]; then
    echo "警告: 最近1000条日志中有 $ERROR_COUNT 个错误"
    # 可以发送邮件或钉钉通知
fi
```

添加到crontab每5分钟检查一次:
```bash
*/5 * * * * /root/my_youtube_summarizer/app/tests/check_errors.sh
```

### 8. 常用命令速查

```bash
# 查看服务状态
sudo systemctl status vidsnap-backend

# 重启服务
sudo systemctl restart vidsnap-backend

# 实时日志
tail -f /root/my_youtube_summarizer/backend/logs/app.log

# 错误日志
/root/my_youtube_summarizer/app/tests/view_logs.sh -e

# 搜索日志
/root/my_youtube_summarizer/app/tests/view_logs.sh -s "关键词"

# 查看特定请求
/root/my_youtube_summarizer/app/tests/view_logs.sh -r <request_id>
```

## 总结

现在你有以下工具来管理生产环境:

1. **日志查看器**: `/root/my_youtube_summarizer/app/tests/view_logs.sh`
2. **生产启动脚本**: `/root/my_youtube_summarizer/app/tests/run_backend_production.sh`  
3. **Systemd服务**: `/etc/systemd/system/vidsnap-backend.service`
4. **日志文件位置**: `/root/my_youtube_summarizer/backend/logs/`

建议工作流:
- **开发时**: 直接运行 `./app/tests/run_fastapi.sh` 看实时输出
- **测试时**: 使用tmux运行生产脚本，可以随时查看
- **生产时**: 使用systemd服务，通过日志文件和journalctl查看
