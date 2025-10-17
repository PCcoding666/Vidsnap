#!/bin/bash

###############################################################################
# YouTube到OSS完整流程集成测试运行脚本
# 
# 功能：
#   - 检查环境配置
#   - 运行完整的端到端集成测试
#   - 生成详细的测试报告
#
# 使用方法：
#   chmod +x run_pipeline_test.sh
#   ./run_pipeline_test.sh
###############################################################################

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印函数
print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# 脚本开始
print_header "YouTube到OSS完整流程集成测试"

# 1. 检查当前目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="$( cd "$SCRIPT_DIR/../../.." && pwd )"

if [ ! -f "$BACKEND_DIR/requirements.txt" ]; then
    print_error "无法找到backend目录或requirements.txt文件"
    print_info "脚本位置: $SCRIPT_DIR"
    print_info "Backend目录: $BACKEND_DIR"
    exit 1
fi

# 切换到backend目录
cd "$BACKEND_DIR"

print_success "当前目录正确"

# 2. 检查Python环境
print_info "检查Python环境..."
if ! command -v python3 &> /dev/null; then
    print_error "未找到python3，请先安装Python 3.8+"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
print_success "Python版本: $PYTHON_VERSION"

# 3. 检查虚拟环境（推荐但不强制）
if [ -z "$VIRTUAL_ENV" ] && [ -z "$CONDA_DEFAULT_ENV" ]; then
    print_warning "未检测到虚拟环境，建议使用虚拟环境运行测试"
    read -p "是否继续？(y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "已取消"
        exit 0
    fi
elif [ -n "$CONDA_DEFAULT_ENV" ]; then
    print_success "检测到Conda环境: $CONDA_DEFAULT_ENV"
else
    print_success "检测到虚拟环境: $VIRTUAL_ENV"
fi

# 4. 检查必需的系统工具
print_info "检查系统工具..."

if ! command -v ffmpeg &> /dev/null; then
    print_error "未找到ffmpeg，请先安装: brew install ffmpeg (macOS) 或 apt-get install ffmpeg (Linux)"
    exit 1
fi
print_success "ffmpeg已安装"

if ! command -v ffprobe &> /dev/null; then
    print_error "未找到ffprobe，请先安装ffmpeg完整包"
    exit 1
fi
print_success "ffprobe已安装"

# 5. 检查.env文件
print_info "检查环境配置..."

if [ ! -f ".env" ]; then
    print_warning ".env文件不存在"
    print_info "请创建.env文件并配置以下环境变量："
    echo "  ALIYUN_ACCESS_KEY_ID=your_access_key_id"
    echo "  ALIYUN_ACCESS_KEY_SECRET=your_access_key_secret"
    echo "  ALIYUN_OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com"
    echo "  ALIYUN_OSS_BUCKET=your_bucket_name"
    exit 1
fi

# 加载.env文件
export $(cat .env | grep -v '^#' | xargs)

# 检查必需的环境变量
REQUIRED_VARS=("ALIYUN_ACCESS_KEY_ID" "ALIYUN_ACCESS_KEY_SECRET" "ALIYUN_OSS_ENDPOINT" "ALIYUN_OSS_BUCKET")
MISSING_VARS=()

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        MISSING_VARS+=("$var")
    fi
done

if [ ${#MISSING_VARS[@]} -ne 0 ]; then
    print_error "缺少以下环境变量："
    for var in "${MISSING_VARS[@]}"; do
        echo "  - $var"
    done
    exit 1
fi

print_success "环境配置完整"

# 6. 检查Python依赖
print_info "检查Python依赖..."

REQUIRED_PACKAGES=("pytest" "pytest-asyncio" "yt-dlp" "ffmpeg-python" "oss2" "requests")
MISSING_PACKAGES=()

for package in "${REQUIRED_PACKAGES[@]}"; do
    if ! python3 -c "import $package" 2>/dev/null; then
        # 处理包名不一致的情况
        if [ "$package" = "pytest-asyncio" ]; then
            if ! python3 -c "import pytest_asyncio" 2>/dev/null; then
                MISSING_PACKAGES+=("$package")
            fi
        elif [ "$package" = "ffmpeg-python" ]; then
            if ! python3 -c "import ffmpeg" 2>/dev/null; then
                MISSING_PACKAGES+=("$package")
            fi
        elif [ "$package" = "yt-dlp" ]; then
            if ! python3 -c "import yt_dlp" 2>/dev/null; then
                MISSING_PACKAGES+=("$package")
            fi
        else
            MISSING_PACKAGES+=("$package")
        fi
    fi
done

if [ ${#MISSING_PACKAGES[@]} -ne 0 ]; then
    print_warning "缺少以下Python包："
    for package in "${MISSING_PACKAGES[@]}"; do
        echo "  - $package"
    done
    
    read -p "是否自动安装缺失的包？(y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "安装依赖..."
        pip install -r requirements.txt
        print_success "依赖安装完成"
    else
        print_error "请手动安装依赖: pip install -r requirements.txt"
        exit 1
    fi
else
    print_success "所有依赖已安装"
fi

# 7. 运行测试
print_header "开始运行测试"

print_info "测试文件: $BACKEND_DIR/app/tests/test_video_to_oss_pipeline.py"
print_info "测试视频: https://www.youtube.com/watch?v=1PaoWKvcJP0"
print_info "超时设置: 120秒"
print_info "预计耗时: 30-120秒"
echo ""

# 运行pytest
cd "$BACKEND_DIR"
python3 -m pytest app/tests/test_video_to_oss_pipeline.py \
    -v \
    -s \
    --tb=short \
    --asyncio-mode=auto \
    --color=yes

TEST_EXIT_CODE=$?

# 8. 显示测试结果
echo ""
print_header "测试完成"

if [ $TEST_EXIT_CODE -eq 0 ]; then
    print_success "所有测试通过！"
else
    print_error "部分测试失败，请查看上方详细信息"
fi

# 9. 检查测试报告
REPORT_FILE="$BACKEND_DIR/app/tests/docs/TEST_OSS_PIPELINE_RESULTS.md"

if [ -f "$REPORT_FILE" ]; then
    print_success "测试报告已生成: $REPORT_FILE"
    
    # 询问是否打开报告
    if command -v cat &> /dev/null; then
        read -p "是否查看测试报告？(y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo ""
            print_header "测试报告内容"
            cat "$REPORT_FILE"
        fi
    fi
else
    print_warning "未找到测试报告文件"
fi

# 10. 退出
echo ""
if [ $TEST_EXIT_CODE -eq 0 ]; then
    print_success "测试流程成功完成！"
    exit 0
else
    print_error "测试流程失败，退出码: $TEST_EXIT_CODE"
    exit $TEST_EXIT_CODE
fi
