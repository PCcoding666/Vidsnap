#!/bin/bash
# 开发环境一键启动脚本 - 同时启动前后端服务

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  开发环境启动${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 检查 tmux 是否安装
if ! command -v tmux &> /dev/null; then
    echo -e "${YELLOW}⚠️  未检测到 tmux${NC}"
    echo ""
    echo "本脚本需要 tmux 来同时管理前后端服务"
    echo "请手动在两个终端分别运行："
    echo ""
    echo -e "${BLUE}终端 1 (后端):${NC}"
    echo "  ./start_backend.sh api"
    echo ""
    echo -e "${BLUE}终端 2 (前端):${NC}"
    echo "  cd frontend && npm run dev"
    echo ""
    exit 1
fi

# 创建 tmux 会话
SESSION_NAME="youtube_analyzer"

# 如果会话已存在，先删除
tmux kill-session -t $SESSION_NAME 2>/dev/null || true

echo -e "${GREEN}🚀 创建 tmux 会话: $SESSION_NAME${NC}"
echo ""

# 创建新会话并启动后端
tmux new-session -d -s $SESSION_NAME -n "backend"
tmux send-keys -t $SESSION_NAME:backend "cd $(pwd) && ./start_backend.sh api" C-m

# 创建新窗口并启动前端
tmux new-window -t $SESSION_NAME -n "frontend"
tmux send-keys -t $SESSION_NAME:frontend "cd $(pwd)/frontend && npm run dev" C-m

# 创建日志窗口
tmux new-window -t $SESSION_NAME -n "logs"
tmux send-keys -t $SESSION_NAME:logs "echo '日志监控窗口'" C-m

echo -e "${GREEN}✅ 服务已在 tmux 会话中启动${NC}"
echo ""
echo -e "${BLUE}使用说明:${NC}"
echo "  1. 查看服务: tmux attach -t $SESSION_NAME"
echo "  2. 切换窗口: Ctrl+B 然后按数字键 (0=后端, 1=前端, 2=日志)"
echo "  3. 退出查看: Ctrl+B 然后按 d"
echo "  4. 停止服务: tmux kill-session -t $SESSION_NAME"
echo ""
echo -e "${GREEN}访问地址:${NC}"
echo "  - 后端 API: http://localhost:8000"
echo "  - API 文档: http://localhost:8000/docs"
echo "  - 前端界面: http://localhost:8080"
echo ""
echo -e "${YELLOW}等待 10 秒让服务启动...${NC}"
sleep 10

# 自动打开浏览器（可选）
if command -v open &> /dev/null; then
    echo -e "${GREEN}🌐 打开浏览器...${NC}"
    open http://localhost:8080
fi

echo ""
echo -e "${GREEN}✨ 开发环境已就绪！${NC}"
echo ""

# 提供选项：是否自动连接到 tmux 会话
read -p "是否连接到 tmux 会话查看服务？(y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    tmux attach -t $SESSION_NAME
fi
