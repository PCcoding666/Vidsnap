#!/bin/bash
# 完整系统集成测试执行脚本

set -e  # 遇到错误立即退出

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}======================================================================${NC}"
echo -e "${GREEN}  完整系统集成测试${NC}"
echo -e "${GREEN}======================================================================${NC}"
echo ""

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"

echo -e "${YELLOW}项目根目录: $PROJECT_ROOT${NC}"
echo -e "${YELLOW}后端目录: $BACKEND_DIR${NC}"
echo ""

# 检查环境变量
echo -e "${YELLOW}1. 检查环境变量配置...${NC}"

if [ -f "$PROJECT_ROOT/.env" ]; then
    echo -e "${GREEN}✅ 找到 .env 文件: $PROJECT_ROOT/.env${NC}"
    source "$PROJECT_ROOT/.env"
elif [ -f "$BACKEND_DIR/.env" ]; then
    echo -e "${GREEN}✅ 找到 .env 文件: $BACKEND_DIR/.env${NC}"
    source "$BACKEND_DIR/.env"
else
    echo -e "${RED}❌ 未找到 .env 文件${NC}"
    echo -e "${YELLOW}请在项目根目录或 backend 目录创建 .env 文件，并配置以下变量：${NC}"
    echo "  - SUPABASE_URL"
    echo "  - SUPABASE_ANON_KEY"
    echo "  - SUPABASE_SERVICE_KEY"
    exit 1
fi

# 检查必需的环境变量
if [ -z "$SUPABASE_URL" ]; then
    echo -e "${RED}❌ SUPABASE_URL 未设置${NC}"
    exit 1
fi

if [ -z "$SUPABASE_ANON_KEY" ]; then
    echo -e "${RED}❌ SUPABASE_ANON_KEY 未设置${NC}"
    exit 1
fi

if [ -z "$SUPABASE_SERVICE_KEY" ]; then
    echo -e "${RED}❌ SUPABASE_SERVICE_KEY 未设置${NC}"
    exit 1
fi

echo -e "${GREEN}✅ 环境变量配置完整${NC}"
echo ""

# 检查 Python 环境
echo -e "${YELLOW}2. 检查 Python 环境...${NC}"

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python3 未安装${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
echo -e "${GREEN}✅ Python 版本: $PYTHON_VERSION${NC}"

# 检查依赖
echo -e "${YELLOW}3. 检查 Python 依赖...${NC}"

cd "$BACKEND_DIR"

if ! python3 -c "import supabase" 2>/dev/null; then
    echo -e "${YELLOW}⚠️  supabase 库未安装，尝试安装...${NC}"
    pip3 install supabase
fi

echo -e "${GREEN}✅ Python 依赖检查完成${NC}"
echo ""

# 运行测试
echo -e "${GREEN}======================================================================${NC}"
echo -e "${GREEN}  开始执行测试...${NC}"
echo -e "${GREEN}======================================================================${NC}"
echo ""

cd "$BACKEND_DIR"
python3 app/tests/test_full_system_integration.py

echo ""
echo -e "${GREEN}======================================================================${NC}"
echo -e "${GREEN}  测试执行完成${NC}"
echo -e "${GREEN}======================================================================${NC}"
