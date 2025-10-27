#!/bin/bash

# 前端开发服务器启动脚本

set -e

# 颜色输出
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   YouTube 视频智能总结系统 - 前端   ${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 检查 Node.js
if ! command -v node &> /dev/null; then
    echo -e "${RED}错误: 未安装 Node.js${NC}"
    echo "请先安装 Node.js: https://nodejs.org/"
    exit 1
fi

echo -e "${GREEN}✓ Node.js 版本:${NC} $(node --version)"

# 检查 npm
if ! command -v npm &> /dev/null; then
    echo -e "${RED}错误: 未安装 npm${NC}"
    exit 1
fi

echo -e "${GREEN}✓ npm 版本:${NC} $(npm --version)"
echo ""

# 检查并安装依赖
if [ ! -d "node_modules" ]; then
    echo -e "${BLUE}首次运行，正在安装依赖...${NC}"
    npm install
    echo -e "${GREEN}✓ 依赖安装完成${NC}"
    echo ""
fi

# 检查环境变量文件
if [ ! -f ".env" ]; then
    echo -e "${BLUE}创建环境变量文件...${NC}"
    cp .env.example .env
    echo -e "${GREEN}✓ 已创建 .env 文件${NC}"
    echo ""
fi

# 解析命令行参数
MODE="dev"
PORT=5173
HOST="localhost"

while [[ $# -gt 0 ]]; do
    case $1 in
        --build)
            MODE="build"
            shift
            ;;
        --preview)
            MODE="preview"
            shift
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --host)
            HOST="$2"
            shift 2
            ;;
        *)
            echo -e "${RED}未知参数: $1${NC}"
            echo "用法: $0 [--build|--preview] [--port PORT] [--host HOST]"
            exit 1
            ;;
    esac
done

# 执行对应模式
case $MODE in
    dev)
        echo -e "${BLUE}启动开发服务器...${NC}"
        echo -e "${GREEN}访问地址: http://${HOST}:${PORT}${NC}"
        echo ""
        npm run dev -- --host $HOST --port $PORT
        ;;
    build)
        echo -e "${BLUE}构建生产版本...${NC}"
        npm run build
        echo -e "${GREEN}✓ 构建完成！${NC}"
        echo "输出目录: dist/"
        ;;
    preview)
        echo -e "${BLUE}预览生产版本...${NC}"
        if [ ! -d "dist" ]; then
            echo -e "${RED}错误: 请先运行构建${NC}"
            echo "运行: $0 --build"
            exit 1
        fi
        echo -e "${GREEN}访问地址: http://${HOST}:${PORT}${NC}"
        echo ""
        npm run preview -- --host $HOST --port $PORT
        ;;
esac
