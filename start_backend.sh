#!/bin/bash
# 后端服务统一启动脚本 - 支持 FastAPI 和 Gradio 两种模式

set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

print_banner() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  YouTube 视频分析平台 - 后端服务${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
}

print_help() {
    echo "使用方法: $0 [模式] [选项]"
    echo ""
    echo "模式:"
    echo "  api      - 启动 FastAPI REST API 服务 (推荐用于生产)"
    echo "  gradio   - 启动 Gradio Web 界面 (推荐用于快速测试)"
    echo "  both     - 同时启动 API 和 Gradio (需要两个终端)"
    echo ""
    echo "选项:"
    echo "  --api-port PORT     设置 API 端口 (默认: 8000)"
    echo "  --gradio-port PORT  设置 Gradio 端口 (默认: 7860)"
    echo "  --no-reload         禁用热重载"
    echo "  -h, --help          显示此帮助"
    echo ""
    echo "示例:"
    echo "  $0 api                    # 启动 FastAPI 服务"
    echo "  $0 gradio                 # 启动 Gradio 界面"
    echo "  $0 api --api-port 8080    # 在 8080 端口启动 API"
    echo ""
}

# 默认配置
MODE="api"
API_PORT=8000
GRADIO_PORT=7860
RELOAD="--reload"

# 解析参数
if [ $# -eq 0 ]; then
    echo -e "${YELLOW}⚠️  未指定模式，使用默认模式: api${NC}"
    echo -e "${BLUE}提示: 使用 '$0 --help' 查看所有选项${NC}"
    echo ""
fi

while [[ $# -gt 0 ]]; do
    case $1 in
        api|gradio|both)
            MODE="$1"
            shift
            ;;
        --api-port)
            API_PORT="$2"
            shift 2
            ;;
        --gradio-port)
            GRADIO_PORT="$2"
            shift 2
            ;;
        --no-reload)
            RELOAD=""
            shift
            ;;
        -h|--help)
            print_help
            exit 0
            ;;
        *)
            echo -e "${RED}未知参数: $1${NC}"
            print_help
            exit 1
            ;;
    esac
done

print_banner

# 环境准备
echo -e "${BLUE}📦 准备环境...${NC}"

# 加载环境变量
if [ -f ".env" ]; then
    echo -e "${GREEN}✅ 加载环境变量: .env${NC}"
    set -a
    . .env
    set +a
else
    echo -e "${YELLOW}⚠️  未找到 .env 文件${NC}"
fi

# 配置代理
export https_proxy=http://127.0.0.1:33210
export http_proxy=http://127.0.0.1:33210
export all_proxy=socks5://127.0.0.1:33211
echo -e "${GREEN}✅ 网络代理已配置${NC}"

# 进入 backend 目录
cd backend

echo ""

# 根据模式启动服务
case $MODE in
    api)
        echo -e "${GREEN}🚀 启动 FastAPI 服务...${NC}"
        echo -e "${BLUE}访问地址:${NC}"
        echo -e "  - API 文档 (Swagger): ${GREEN}http://127.0.0.1:$API_PORT/docs${NC}"
        echo -e "  - API 文档 (ReDoc):   ${GREEN}http://127.0.0.1:$API_PORT/redoc${NC}"
        echo -e "  - 健康检查:           ${GREEN}http://127.0.0.1:$API_PORT/health${NC}"
        echo ""
        echo -e "${YELLOW}按 Ctrl+C 停止服务器${NC}"
        echo ""
        
        python -m uvicorn app.main:app --host 0.0.0.0 --port $API_PORT $RELOAD
        ;;
        
    gradio)
        echo -e "${GREEN}🚀 启动 Gradio Web 界面...${NC}"
        echo -e "${BLUE}访问地址:${NC}"
        echo -e "  - Gradio 界面: ${GREEN}http://127.0.0.1:$GRADIO_PORT${NC}"
        echo ""
        echo -e "${YELLOW}按 Ctrl+C 停止服务器${NC}"
        echo ""
        
        export GRADIO_PORT=$GRADIO_PORT
        python gradio_app.py
        ;;
        
    both)
        echo -e "${YELLOW}⚠️  同时启动两个服务需要在不同终端运行:${NC}"
        echo ""
        echo -e "${BLUE}终端 1 (FastAPI):${NC}"
        echo "  ./start_backend.sh api --api-port $API_PORT"
        echo ""
        echo -e "${BLUE}终端 2 (Gradio):${NC}"
        echo "  ./start_backend.sh gradio --gradio-port $GRADIO_PORT"
        echo ""
        exit 0
        ;;
esac
