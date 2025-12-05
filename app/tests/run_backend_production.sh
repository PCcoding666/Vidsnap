#!/bin/bash

set -e

echo "启动生产环境后端服务..."

# 切换到backend目录
cd "$(dirname "$0")/../../backend"

# 创建logs目录
mkdir -p logs

# 加载环境变量
if [ -f "../.env" ]; then
    source <(cat ../.env | sed 's/^/export /')
fi

# 配置代理（如果需要）
export https_proxy=http://127.0.0.1:33210
export http_proxy=http://127.0.0.1:33210
export all_proxy=socks5://127.0.0.1:33211

# 设置日志级别和文件
export LOG_LEVEL=${LOG_LEVEL:-INFO}
export LOG_FILE="logs/app.log"

# 启动服务器（生产模式，带日志）
echo "服务器将在 http://0.0.0.0:8000 启动"
echo "日志文件: $LOG_FILE"
echo "----------------------------------------"

uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level info \
    --access-log \
    --log-config logging.conf 2>&1 | tee -a logs/uvicorn.log
