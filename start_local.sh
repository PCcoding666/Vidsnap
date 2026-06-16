#!/bin/bash
# ============================================================
# 本地开发启动脚本 (macOS/Linux)
# ============================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

# 本地开发端口
BACKEND_PORT=8000
FRONTEND_PORT=8081

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  VidSnap 本地开发环境${NC}"
echo -e "${BLUE}  前端: http://localhost:${FRONTEND_PORT}${NC}"
echo -e "${BLUE}  后端: http://localhost:${BACKEND_PORT}${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 停止现有服务
stop_services() {
    echo -e "${YELLOW}🛑 停止现有服务...${NC}"
    pkill -f "uvicorn app.main:app" 2>/dev/null || true
    pkill -f "npm run dev" 2>/dev/null || true
    pkill -f "vite" 2>/dev/null || true
    sleep 2
    echo -e "${GREEN}✅ 服务已停止${NC}"
}

# 检查配置
check_config() {
    echo -e "${BLUE}🔍 检查配置...${NC}"
    
    # 检查 .env 文件
    if [ -f "$PROJECT_DIR/backend/.env" ]; then
        echo -e "  环境变量: ${GREEN}✅ .env 文件存在${NC}"
    else
        echo -e "  环境变量: ${RED}❌ .env 文件不存在${NC}"
        exit 1
    fi
    
    # 检查 Docker
    if docker ps > /dev/null 2>&1; then
        echo -e "  Docker: ${GREEN}✅ 运行中${NC}"
    else
        echo -e "  Docker: ${RED}❌ 未运行，请启动 Docker Desktop${NC}"
        exit 1
    fi
    
    echo ""
}

# 启动数据库
start_database() {
    echo -e "${GREEN}🚀 启动数据库服务...${NC}"
    cd "$PROJECT_DIR"
    docker-compose up -d
    sleep 3
    echo -e "${GREEN}✅ 数据库已启动${NC}"
}

# 启动后端
start_backend() {
    echo -e "${GREEN}🚀 启动后端服务 (端口 ${BACKEND_PORT})...${NC}"
    
    cd "$PROJECT_DIR/backend"
    
    # 可选代理：优先使用显式配置；其次读取 macOS 系统代理；最后兜底常见本地代理端口。
    SYSTEM_HTTP_PROXY=""
    SYSTEM_HTTPS_PROXY=""
    if command -v scutil >/dev/null 2>&1 && command -v nc >/dev/null 2>&1; then
        http_enabled="$(scutil --proxy | awk -F': ' '/HTTPEnable/{print $2; exit}')"
        http_host="$(scutil --proxy | awk -F': ' '/HTTPProxy/{print $2; exit}')"
        http_port="$(scutil --proxy | awk -F': ' '/HTTPPort/{print $2; exit}')"
        https_enabled="$(scutil --proxy | awk -F': ' '/HTTPSEnable/{print $2; exit}')"
        https_host="$(scutil --proxy | awk -F': ' '/HTTPSProxy/{print $2; exit}')"
        https_port="$(scutil --proxy | awk -F': ' '/HTTPSPort/{print $2; exit}')"

        if [ "$http_enabled" = "1" ] && [ -n "$http_host" ] && [ -n "$http_port" ] && nc -z "$http_host" "$http_port" >/dev/null 2>&1; then
            SYSTEM_HTTP_PROXY="http://${http_host}:${http_port}"
        fi
        if [ "$https_enabled" = "1" ] && [ -n "$https_host" ] && [ -n "$https_port" ] && nc -z "$https_host" "$https_port" >/dev/null 2>&1; then
            SYSTEM_HTTPS_PROXY="http://${https_host}:${https_port}"
        fi
    fi

    if [ -n "${VIDSNAP_HTTP_PROXY:-}" ]; then
        export http_proxy="$VIDSNAP_HTTP_PROXY"
        export https_proxy="${VIDSNAP_HTTPS_PROXY:-$VIDSNAP_HTTP_PROXY}"
        if [ -n "${VIDSNAP_ALL_PROXY:-}" ]; then
            export all_proxy="$VIDSNAP_ALL_PROXY"
        fi
        echo -e "  代理: ${GREEN}✅ 使用 VIDSNAP_*_PROXY 配置${NC}"
    elif [ -n "$SYSTEM_HTTP_PROXY" ] || [ -n "$SYSTEM_HTTPS_PROXY" ]; then
        export http_proxy="${SYSTEM_HTTP_PROXY:-$SYSTEM_HTTPS_PROXY}"
        export https_proxy="${SYSTEM_HTTPS_PROXY:-$SYSTEM_HTTP_PROXY}"
        echo -e "  代理: ${GREEN}✅ 使用 macOS 系统代理${NC}"
    elif command -v nc >/dev/null 2>&1 && nc -z 127.0.0.1 33210 >/dev/null 2>&1; then
        export https_proxy=http://127.0.0.1:33210
        export http_proxy=http://127.0.0.1:33210
        if nc -z 127.0.0.1 33211 >/dev/null 2>&1; then
            export all_proxy=socks5://127.0.0.1:33211
        fi
        echo -e "  代理: ${GREEN}✅ 检测到本地代理 127.0.0.1:33210${NC}"
    else
        echo -e "  代理: ${YELLOW}未检测到本地代理，后端将直连外部服务${NC}"
    fi
    export no_proxy="${no_proxy:+$no_proxy,}localhost,127.0.0.1,::1"
    export NO_PROXY="${NO_PROXY:+$NO_PROXY,}localhost,127.0.0.1,::1"
    
    # 后台启动
    nohup uvicorn app.main:app --host 0.0.0.0 --port ${BACKEND_PORT} --reload \
        > "$LOG_DIR/backend.log" 2>&1 &
    
    echo $! > "$LOG_DIR/backend.pid"
    echo -e "${GREEN}✅ 后端 PID: $(cat $LOG_DIR/backend.pid)${NC}"
    sleep 3
}

# 启动前端
start_frontend() {
    echo -e "${GREEN}🚀 启动前端服务 (端口 ${FRONTEND_PORT})...${NC}"
    
    cd "$PROJECT_DIR/frontend"
    
    # 后台启动
    nohup npm run dev -- --port ${FRONTEND_PORT} --host 0.0.0.0 \
        > "$LOG_DIR/frontend.log" 2>&1 &
    
    echo $! > "$LOG_DIR/frontend.pid"
    echo -e "${GREEN}✅ 前端 PID: $(cat $LOG_DIR/frontend.pid)${NC}"
    sleep 3
}

# 检查服务状态
check_status() {
    echo ""
    echo -e "${BLUE}📊 服务状态检查:${NC}"
    
    # 后端
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:${BACKEND_PORT}/health 2>/dev/null | grep -q "200"; then
        echo -e "  后端 API: ${GREEN}✅ 运行中${NC}"
    else
        echo -e "  后端 API: ${YELLOW}⏳ 启动中...${NC}"
    fi
    
    # 前端
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:${FRONTEND_PORT}/ 2>/dev/null | grep -q "200"; then
        echo -e "  前端服务: ${GREEN}✅ 运行中${NC}"
    else
        echo -e "  前端服务: ${YELLOW}⏳ 启动中...${NC}"
    fi
    
    # 数据库
    if docker ps | grep -q "vidsnap-postgres"; then
        echo -e "  PostgreSQL: ${GREEN}✅ 运行中${NC}"
    else
        echo -e "  PostgreSQL: ${RED}❌ 未运行${NC}"
    fi
    
    if docker ps | grep -q "vidsnap-redis"; then
        echo -e "  Redis: ${GREEN}✅ 运行中${NC}"
    else
        echo -e "  Redis: ${RED}❌ 未运行${NC}"
    fi
}

# 主流程
check_config
stop_services
start_database
start_backend
start_frontend
check_status

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  🎉 服务启动完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}访问地址:${NC}"
echo -e "  🌐 前端: ${GREEN}http://localhost:${FRONTEND_PORT}${NC}"
echo -e "  📡 后端 API: ${GREEN}http://localhost:${BACKEND_PORT}${NC}"
echo -e "  📚 API 文档: ${GREEN}http://localhost:${BACKEND_PORT}/docs${NC}"
echo ""
echo -e "${BLUE}日志文件:${NC}"
echo -e "  后端日志: tail -f $LOG_DIR/backend.log"
echo -e "  前端日志: tail -f $LOG_DIR/frontend.log"
echo ""
echo -e "${BLUE}停止服务:${NC}"
echo -e "  ./stop_local.sh"
echo -e "  或手动执行: pkill -f 'uvicorn' && pkill -f 'vite'"
echo ""
echo -e "${YELLOW}💡 修改代码后会自动热重载！${NC}"
