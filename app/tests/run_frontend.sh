#!/bin/bash

set -e

echo "启动前端开发服务器..."

# 切换到frontend目录
cd "$(dirname "$0")/../../frontend"

# 检查依赖是否安装
if [ ! -d "node_modules" ]; then
    echo "未检测到node_modules，正在安装依赖..."
    npm install
fi

# 启动开发服务器
echo "服务器将在 http://localhost:8080 启动"
npm run dev
