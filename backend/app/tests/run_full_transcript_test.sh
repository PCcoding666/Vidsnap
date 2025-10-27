#!/bin/bash

# 测试完整转录文本传递功能
# 验证聊天服务不再使用关键词检索，而是传递完整文本给LLM

set -e

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}测试完整转录文本传递功能${NC}"
echo -e "${BLUE}========================================${NC}"

# 进入项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "\n${YELLOW}项目路径:${NC} $PROJECT_ROOT"

# 加载环境变量
if [ -f ".env" ]; then
    echo -e "${GREEN}✓${NC} 加载 .env 文件"
    export $(cat .env | grep -v '^#' | xargs)
elif [ -f "backend/.env" ]; then
    echo -e "${GREEN}✓${NC} 加载 backend/.env 文件"
    export $(cat backend/.env | grep -v '^#' | xargs)
else
    echo -e "${YELLOW}警告: 未找到 .env 文件${NC}"
fi

# 检查API密钥
if [ -z "$QWEN_API_KEY" ] && [ -z "$DASHSCOPE_API_KEY" ]; then
    echo -e "${YELLOW}警告: 未设置 QWEN_API_KEY 或 DASHSCOPE_API_KEY${NC}"
    echo "注意: 测试将使用模拟数据，不会调用实际的LLM服务"
fi

# 设置代理
export https_proxy=http://127.0.0.1:33210
export http_proxy=http://127.0.0.1:33210
export all_proxy=socks5://127.0.0.1:33211

echo -e "${GREEN}✓${NC} 代理已设置"

# 检查Python环境
if command -v python3 &> /dev/null; then
    PYTHON_CMD=python3
elif command -v python &> /dev/null; then
    PYTHON_CMD=python
else
    echo -e "${YELLOW}错误: 未找到Python${NC}"
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}✓${NC} Python版本: $PYTHON_VERSION"

# 检查是否在虚拟环境中
if [ -n "$CONDA_DEFAULT_ENV" ]; then
    echo -e "${GREEN}✓${NC} Conda环境: $CONDA_DEFAULT_ENV"
elif [ -n "$VIRTUAL_ENV" ]; then
    echo -e "${GREEN}✓${NC} 虚拟环境: $VIRTUAL_ENV"
else
    echo -e "${YELLOW}警告: 未检测到虚拟环境${NC}"
fi

echo -e "\n${BLUE}----------------------------------------${NC}"
echo -e "${BLUE}运行测试${NC}"
echo -e "${BLUE}----------------------------------------${NC}"

# 运行测试
$PYTHON_CMD backend/app/tests/test_chat_full_transcript.py

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}测试完成！${NC}"
echo -e "${GREEN}========================================${NC}"
