#!/bin/bash

# YouTube 视频智能总结系统 - Gradio 启动脚本
# 功能：环境检查、代理配置、服务启动

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 打印标题
print_banner() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  YouTube 视频智能总结系统${NC}"
    echo -e "${BLUE}  Gradio Web 界面启动器${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
}

# 检查当前目录
check_directory() {
    log_info "检查当前目录..."
    
    if [ ! -f "gradio_app.py" ]; then
        log_error "未找到 gradio_app.py，请在 backend 目录下运行此脚本"
        exit 1
    fi
    
    log_success "目录检查通过"
}

# 检查 Python 版本
check_python_version() {
    log_info "检查 Python 版本..."
    
    if ! command -v python3 &> /dev/null; then
        log_error "未找到 Python3，请先安装 Python 3.8+"
        exit 1
    fi
    
    PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    log_info "当前 Python 版本: $PYTHON_VERSION"
    
    # 检查版本是否 >= 3.8
    REQUIRED_VERSION="3.8"
    if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
        log_error "Python 版本过低，需要 3.8 或更高版本"
        exit 1
    fi
    
    log_success "Python 版本检查通过"
}

# 检查 Conda 环境
check_conda_environment() {
    log_info "检查 Conda 环境..."
    
    if [ -n "$CONDA_DEFAULT_ENV" ]; then
        log_success "当前在 Conda 环境: $CONDA_DEFAULT_ENV"
    else
        log_warning "未检测到 Conda 环境，使用系统 Python"
    fi
}

# 检查依赖包
check_dependencies() {
    log_info "检查必要的依赖包..."
    
    REQUIRED_PACKAGES=("gradio" "fastapi" "oss2" "dashscope")
    MISSING_PACKAGES=()
    
    for package in "${REQUIRED_PACKAGES[@]}"; do
        if ! python3 -c "import $package" &> /dev/null; then
            MISSING_PACKAGES+=("$package")
        fi
    done
    
    if [ ${#MISSING_PACKAGES[@]} -gt 0 ]; then
        log_warning "缺少以下依赖包: ${MISSING_PACKAGES[*]}"
        log_info "尝试安装依赖..."
        
        if [ -f "requirements.txt" ]; then
            pip install -r requirements.txt
            log_success "依赖安装完成"
        else
            log_error "未找到 requirements.txt"
            exit 1
        fi
    else
        log_success "所有依赖包已安装"
    fi
}

# 检查环境变量
check_environment_variables() {
    log_info "检查环境变量配置..."
    
    # 查找并加载根目录 .env 文件（优先），其次为 backend/.env
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    ROOT_DIR="$(dirname "$SCRIPT_DIR")"
    ENV_FILE="$ROOT_DIR/.env"
    if [ ! -f "$ENV_FILE" ]; then
        ENV_FILE="$SCRIPT_DIR/.env"
    fi

    if [ -f "$ENV_FILE" ]; then
        log_success "找到环境配置文件: $ENV_FILE"
        # 加载环境变量（兼容引号与空格）
        set -a
        # 过滤掉注释与空行，只保留符合 KEY=VAL 的行
        # shellcheck disable=SC1090
        . "$ENV_FILE"
        set +a

        # 环境变量兼容映射：如果仅设置了 QWEN_API_KEY，则映射到 DASHSCOPE_API_KEY（保持兼容）
        if [ -n "$QWEN_API_KEY" ] && [ -z "$DASHSCOPE_API_KEY" ]; then
            export DASHSCOPE_API_KEY="$QWEN_API_KEY"
            log_info "已根据 QWEN_API_KEY 设置 DASHSCOPE_API_KEY（兼容映射）"
        fi
    else
        log_warning "未找到 .env 文件，请确保环境变量已配置（期望路径：$ROOT_DIR/.env 或 $SCRIPT_DIR/.env）"
    fi
    
    # 检查关键 API 密钥
    REQUIRED_VARS=("ALIYUN_ACCESS_KEY_ID" "ALIYUN_ACCESS_KEY_SECRET" "ALIYUN_OSS_ENDPOINT" "ALIYUN_OSS_BUCKET")
    MISSING_VARS=()
    
    for var in "${REQUIRED_VARS[@]}"; do
        if [ -z "${!var}" ]; then
            MISSING_VARS+=("$var")
        fi
    done
    
    # 检查至少有一个 API 密钥
    if [ -z "$QWEN_API_KEY" ] && [ -z "$DASHSCOPE_API_KEY" ] && [ -z "$TRANSCRIPT_SERVICE_API_KEY" ]; then
        MISSING_VARS+=("QWEN_API_KEY/DASHSCOPE_API_KEY/TRANSCRIPT_SERVICE_API_KEY")
    fi
    
    if [ ${#MISSING_VARS[@]} -gt 0 ]; then
        log_warning "缺少以下环境变量: ${MISSING_VARS[*]}"
        log_warning "将继续启动 Gradio 界面，但涉及 OSS 的功能可能无法正常使用（如上传/下载、元数据保存）。"
    else
        log_success "环境变量检查通过"
    fi
}

# 配置代理
setup_proxy() {
    log_info "配置网络代理..."
    
    export https_proxy=http://127.0.0.1:33210
    export http_proxy=http://127.0.0.1:33210
    export all_proxy=socks5://127.0.0.1:33211
    
    log_success "代理配置完成"
    log_info "  - HTTP/HTTPS: http://127.0.0.1:33210"
    log_info "  - SOCKS5: socks5://127.0.0.1:33211"
}

# 解析命令行参数
parse_arguments() {
    SHARE_MODE=false
    PORT=7860
    HOST="0.0.0.0"
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --share)
                SHARE_MODE=true
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
            -h|--help)
                echo "使用方法: $0 [选项]"
                echo ""
                echo "选项:"
                echo "  --share          生成公网链接（通过 Gradio）"
                echo "  --port PORT      指定端口（默认: 7860）"
                echo "  --host HOST      指定主机（默认: 0.0.0.0）"
                echo "  -h, --help       显示此帮助信息"
                exit 0
                ;;
            *)
                log_error "未知参数: $1"
                echo "使用 -h 或 --help 查看帮助"
                exit 1
                ;;
        esac
    done
}

# 启动 Gradio 应用
start_gradio() {
    log_info "启动 Gradio 应用..."
    echo ""
    
    log_info "服务配置:"
    log_info "  - 主机: $HOST"
    log_info "  - 端口: $PORT"
    log_info "  - 公网分享: $([ "$SHARE_MODE" = true ] && echo "启用" || echo "禁用")"
    
    echo ""
    log_success "🚀 正在启动服务器..."
    echo ""
    log_info "访问地址:"
    log_info "  - 本地: http://127.0.0.1:$PORT"
    log_info "  - 网络: http://$HOST:$PORT"
    
    if [ "$SHARE_MODE" = true ]; then
        log_info "  - 公网链接将在启动后显示"
    fi
    
    echo ""
    log_warning "按 Ctrl+C 停止服务器"
    echo ""
    echo "========================================"
    echo ""
    
    # 将参数注入为环境变量，供 gradio_app.py 使用
    export GRADIO_HOST="$HOST"
    export GRADIO_PORT="$PORT"
    export GRADIO_SHARE="$([ "$SHARE_MODE" = true ] && echo "true" || echo "false")"
    # 启动应用
    python3 gradio_app.py
}

# 主函数
main() {
    print_banner
    
    # 解析参数
    parse_arguments "$@"
    
    # 执行检查
    check_directory
    check_python_version
    check_conda_environment
    check_dependencies
    check_environment_variables
    setup_proxy
    
    echo ""
    log_success "所有检查通过，准备启动应用..."
    echo ""
    
    # 启动服务
    start_gradio
}

# 运行主函数
main "$@"
