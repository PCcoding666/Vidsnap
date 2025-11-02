#!/bin/bash
# FastAPI 后端服务启动脚本

set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  FastAPI 后端服务启动器${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 检查当前目录
if [ ! -f "app/main.py" ]; then
    echo -e "${YELLOW}⚠️  请在 backend 目录下运行此脚本${NC}"
    exit 1
fi

# 加载环境变量
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$ROOT_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    ENV_FILE="$SCRIPT_DIR/.env"
fi

if [ -f "$ENV_FILE" ]; then
    echo -e "${GREEN}✅ 加载环境变量: $ENV_FILE${NC}"
    set -a
    . "$ENV_FILE"
    set +a
else
    echo -e "${YELLOW}⚠️  未找到 .env 文件${NC}"
fi

# 配置代理
echo -e "${BLUE}🌐 配置网络代理...${NC}"
export https_proxy=http://127.0.0.1:33210
export http_proxy=http://127.0.0.1:33210
export all_proxy=socks5://127.0.0.1:33211

# 默认配置
PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"
RELOAD="${RELOAD:-true}"

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --port)
            PORT="$2"
            shift 2
            ;;
        --host)
            HOST="$2"
            shift 2
            ;;
        --no-reload)
            RELOAD="false"
            shift
            ;;
        *)
            echo -e "${YELLOW}未知参数: $1${NC}"
            shift
            ;;
    esac
done

echo ""
echo -e "${GREEN}📋 服务配置:${NC}"
echo -e "  主机: $HOST"
echo -e "  端口: $PORT"
echo -e "  热重载: $RELOAD"
echo ""

echo -e "${GREEN}🚀 启动 FastAPI 服务...${NC}"
echo -e "${BLUE}访问地址:${NC}"
echo -e "  - API文档 (Swagger): ${GREEN}http://127.0.0.1:$PORT/docs${NC}"
echo -e "  - API文档 (ReDoc):   ${GREEN}http://127.0.0.1:$PORT/redoc${NC}"
echo -e "  - 健康检查:          ${GREEN}http://127.0.0.1:$PORT/health${NC}"
echo ""
echo -e "${YELLOW}按 Ctrl+C 停止服务器${NC}"
echo ""

# 启动服务
if [ "$RELOAD" = "true" ]; then
    python -m uvicorn app.main:app --host "$HOST" --port "$PORT" --reload
else
    python -m uvicorn app.main:app --host "$HOST" --port "$PORT"
fi
