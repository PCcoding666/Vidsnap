#!/bin/bash

set -e

echo "启动 FastAPI 服务器..."

# 切换到backend目录
cd "$(dirname "$0")/../../backend"

# 加载环境变量
if [ -f "../.env" ]; then
    export $(cat ../.env | grep -v '^#' | xargs)
fi

# 配置代理（如果需要）
export https_proxy=http://127.0.0.1:33210
export http_proxy=http://127.0.0.1:33210
export all_proxy=socks5://127.0.0.1:33211

# 启动服务器
echo "服务器将在 http://0.0.0.0:8000 启动"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
