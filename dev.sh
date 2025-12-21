#!/bin/bash
# ============================================================
# 开发模式启动脚本 (热重载) - 与生产模式端口隔离
# - 前端: https://vidsnap-test.space:8081 (热重载)
# - 后端: 8001 端口 (热重载)
# - 生产模式: 8000 端口 (不冲突)
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

DOMAIN="vidsnap-test.space"

# 开发模式专用端口
DEV_BACKEND_PORT=8001
DEV_FRONTEND_PORT=8082
DEV_NGINX_PORT=8081

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  VidSnap 开发模式 (热重载)${NC}"
echo -e "${BLUE}  前端: https://${DOMAIN}:${DEV_NGINX_PORT}${NC}"
echo -e "${BLUE}  后端: http://127.0.0.1:${DEV_BACKEND_PORT}${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "${YELLOW}  ⚠️ 不影响生产环境 (8000/443)${NC}"
echo ""

# 停止开发模式服务（确保彻底重启）
stop_dev_services() {
    echo -e "${YELLOW}🛑 停止开发模式服务...${NC}"
    
    # 停止开发前端 (8082) - 彻底清理
    pkill -f "vite.*${DEV_FRONTEND_PORT}" 2>/dev/null || true
    pkill -f "vite" 2>/dev/null || true
    fuser -k ${DEV_FRONTEND_PORT}/tcp 2>/dev/null || true
    
    # 停止开发后端 (8001) - 彻底清理所有占用端口的进程
    pkill -f "uvicorn.*${DEV_BACKEND_PORT}" 2>/dev/null || true
    pkill -9 -f "uvicorn.*${DEV_BACKEND_PORT}" 2>/dev/null || true
    fuser -k ${DEV_BACKEND_PORT}/tcp 2>/dev/null || true
    
    # 强制释放端口（确保没有遗留进程）
    for pid in $(lsof -t -i:${DEV_BACKEND_PORT} 2>/dev/null); do
        echo "  杀掉占用 ${DEV_BACKEND_PORT} 端口的进程: $pid"
        kill -9 $pid 2>/dev/null || true
    done
    for pid in $(lsof -t -i:${DEV_FRONTEND_PORT} 2>/dev/null); do
        echo "  杀掉占用 ${DEV_FRONTEND_PORT} 端口的进程: $pid"
        kill -9 $pid 2>/dev/null || true
    done
    
    # 停止开发模式的 Celery (如果有)
    pkill -f "celery.*dev" 2>/dev/null || true
    
    sleep 2
    
    # 验证端口已释放
    if ss -tlnp | grep -q ":${DEV_BACKEND_PORT} \|:${DEV_FRONTEND_PORT} "; then
        echo -e "${RED}⚠️ 警告：端口可能未完全释放${NC}"
        ss -tlnp | grep -E ":${DEV_BACKEND_PORT} |:${DEV_FRONTEND_PORT} "
    else
        echo -e "${GREEN}✅ 开发服务已完全停止，端口已释放${NC}"
    fi
}

# 检查配置
check_config() {
    echo -e "${BLUE}🔍 检查配置...${NC}"
    
    # 检查 Deno
    if command -v deno &> /dev/null; then
        DENO_VERSION=$(deno --version | head -1 | awk '{print $2}')
        echo -e "  Deno: ${GREEN}✅ v${DENO_VERSION}${NC}"
    else
        echo -e "  Deno: ${YELLOW}⚠️ 未安装 (YouTube 下载可能失败)${NC}"
    fi
    
    # 检查 FFmpeg
    if command -v ffmpeg &> /dev/null; then
        echo -e "  FFmpeg: ${GREEN}✅ 已安装${NC}"
    else
        echo -e "  FFmpeg: ${YELLOW}⚠️ 未安装 (视频处理将失败)${NC}"
    fi
    
    # 检查 Cookies 文件
    COOKIES_FILE="$PROJECT_DIR/backend/youtube_cookies.txt"
    if [ -f "$COOKIES_FILE" ]; then
        COOKIES_SIZE=$(stat -c%s "$COOKIES_FILE" 2>/dev/null || stat -f%z "$COOKIES_FILE" 2>/dev/null)
        if [ "$COOKIES_SIZE" -gt 1000 ]; then
            echo -e "  YouTube Cookies: ${GREEN}✅ 已配置 (${COOKIES_SIZE} bytes)${NC}"
        else
            echo -e "  YouTube Cookies: ${YELLOW}⚠️ 文件过小，可能无效${NC}"
        fi
    else
        echo -e "  YouTube Cookies: ${YELLOW}⚠️ 未配置 (YouTube 下载可能失败)${NC}"
    fi
    
    # 检查 .env 文件
    if [ -f "$PROJECT_DIR/backend/.env" ]; then
        echo -e "  环境变量: ${GREEN}✅ .env 文件存在${NC}"
    else
        echo -e "  环境变量: ${RED}❌ .env 文件不存在${NC}"
    fi
    
    echo ""
}

# 配置 Nginx 开发代理 (HTTPS)
setup_nginx_dev() {
    echo -e "${BLUE}🔧 配置 Nginx 开发代理 (HTTPS:${DEV_NGINX_PORT} -> ${DEV_FRONTEND_PORT})...${NC}"
    
    # 检查 SSL 证书
    if [ ! -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]; then
        echo -e "${RED}❌ SSL 证书不存在，使用 HTTP 模式${NC}"
        cat > /www/server/panel/vhost/nginx/vidsnap-dev-${DEV_NGINX_PORT}.conf << EOF
# 开发模式 HTTP - vidsnap-test.space:${DEV_NGINX_PORT} -> 内部 ${DEV_FRONTEND_PORT}
server {
    listen ${DEV_NGINX_PORT};
    server_name ${DOMAIN} www.${DOMAIN} _;
    
    # Vite HMR WebSocket
    location / {
        proxy_pass http://127.0.0.1:${DEV_FRONTEND_PORT};
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$http_host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 86400;
    }
    
    # API 代理到开发后端 (8001)
    location /api/ {
        proxy_pass http://127.0.0.1:${DEV_BACKEND_PORT}/api/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        client_max_body_size 500M;
    }
}
EOF
    else
        echo -e "${GREEN}✅ 发现 SSL 证书，配置 HTTPS 开发模式${NC}"
        cat > /www/server/panel/vhost/nginx/vidsnap-dev-${DEV_NGINX_PORT}.conf << EOF
# 开发模式 HTTPS - vidsnap-test.space:${DEV_NGINX_PORT} -> 内部 ${DEV_FRONTEND_PORT}
# 后端 API 代理到 ${DEV_BACKEND_PORT} (与生产 8000 隔离)
server {
    listen ${DEV_NGINX_PORT} ssl;
    http2 on;
    server_name ${DOMAIN} www.${DOMAIN} _;
    
    # SSL 证书
    ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
    
    # SSL 安全配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;
    
    # Vite HMR WebSocket
    location / {
        proxy_pass http://127.0.0.1:${DEV_FRONTEND_PORT};
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$http_host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 86400;
    }
    
    # API 代理到开发后端 (8001，与生产 8000 隔离)
    location /api/ {
        proxy_pass http://127.0.0.1:${DEV_BACKEND_PORT}/api/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        client_max_body_size 500M;
    }
}
EOF
    fi

    # 测试 Nginx 配置
    nginx -t
    
    # 安全重载 Nginx（检查主进程是否存活）
    NGINX_PID_FILE="/www/server/nginx/logs/nginx.pid"
    if [ -f "$NGINX_PID_FILE" ] && kill -0 $(cat "$NGINX_PID_FILE") 2>/dev/null; then
        # 主进程存活，安全 reload
        /www/server/nginx/sbin/nginx -s reload
    else
        # 主进程不存在，清理并重启
        echo -e "${YELLOW}Nginx 主进程不存在，正在重启...${NC}"
        pkill -9 nginx 2>/dev/null || true
        rm -f "$NGINX_PID_FILE" 2>/dev/null || true
        sleep 1
        nginx
    fi
    
    echo -e "${GREEN}✅ Nginx 开发代理配置完成${NC}"
}

# 启动开发后端 (8001 端口)
start_backend() {
    echo -e "${GREEN}🚀 启动开发后端服务 (端口 ${DEV_BACKEND_PORT}, 热重载)...${NC}"
    
    cd "$PROJECT_DIR/backend"
    source venv/bin/activate
    
    # 设置 Deno 环境变量
    export DENO_INSTALL="$HOME/.deno"
    export PATH="$DENO_INSTALL/bin:$PATH"
    
    nohup uvicorn app.main:app --host 0.0.0.0 --port ${DEV_BACKEND_PORT} --reload \
        > "$LOG_DIR/backend-dev.log" 2>&1 &
    
    echo $! > "$LOG_DIR/backend-dev.pid"
    echo -e "${GREEN}✅ 开发后端 PID: $(cat $LOG_DIR/backend-dev.pid)${NC}"
    
    # 等待后端启动并检查配置加载
    echo -e "${YELLOW}⏳ 等待后端初始化...${NC}"
    sleep 5
    
    # 检查 Cookies 加载状态
    if grep -q "YouTube Cookies 已启用" "$LOG_DIR/backend-dev.log" 2>/dev/null; then
        echo -e "  ${GREEN}✅ YouTube Cookies 已加载${NC}"
    else
        echo -e "  ${YELLOW}⚠️ YouTube Cookies 未加载（检查日志）${NC}"
    fi
}

# 启动前端（内部 8082 端口，通过 Nginx 8081 访问）
start_frontend() {
    echo -e "${GREEN}🚀 启动开发前端服务 (端口 ${DEV_FRONTEND_PORT}, 热重载)...${NC}"
    
    cd "$PROJECT_DIR/frontend"
    
    nohup npm run dev -- --port ${DEV_FRONTEND_PORT} --host 0.0.0.0 \
        > "$LOG_DIR/frontend-dev.log" 2>&1 &
    
    echo $! > "$LOG_DIR/frontend-dev.pid"
    echo -e "${GREEN}✅ 开发前端 PID: $(cat $LOG_DIR/frontend-dev.pid)${NC}"
}

# 检查服务状态
check_status() {
    echo ""
    echo -e "${YELLOW}⏳ 等待服务启动...${NC}"
    sleep 3
    
    echo ""
    echo -e "${BLUE}📊 开发模式服务状态:${NC}"
    
    # 开发后端
    if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:${DEV_BACKEND_PORT}/docs 2>/dev/null | grep -q "200"; then
        echo -e "  开发后端 (${DEV_BACKEND_PORT}): ${GREEN}✅ 运行中${NC}"
    else
        echo -e "  开发后端 (${DEV_BACKEND_PORT}): ${YELLOW}⏳ 启动中...${NC}"
    fi
    
    # 开发前端内部端口
    if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:${DEV_FRONTEND_PORT}/ 2>/dev/null | grep -q "200"; then
        echo -e "  开发前端 (${DEV_FRONTEND_PORT} 内部): ${GREEN}✅ 运行中${NC}"
    else
        echo -e "  开发前端 (${DEV_FRONTEND_PORT} 内部): ${YELLOW}⏳ 启动中...${NC}"
    fi
    
    # Nginx 代理
    if curl -sk -o /dev/null -w "%{http_code}" https://127.0.0.1:${DEV_NGINX_PORT}/ 2>/dev/null | grep -q "200"; then
        echo -e "  Nginx 代理 (${DEV_NGINX_PORT} HTTPS): ${GREEN}✅ 运行中${NC}"
    else
        echo -e "  Nginx 代理 (${DEV_NGINX_PORT} HTTPS): ${YELLOW}⏳ 启动中...${NC}"
    fi
    
    echo ""
    echo -e "${BLUE}📊 生产模式服务状态:${NC}"
    
    # 生产后端
    if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/docs 2>/dev/null | grep -q "200"; then
        echo -e "  生产后端 (8000): ${GREEN}✅ 运行中${NC}"
    else
        echo -e "  生产后端 (8000): ${YELLOW}⚠️ 未运行${NC}"
    fi
    
    # 生产前端
    if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:443/ 2>/dev/null | grep -q "200"; then
        echo -e "  生产前端 (443): ${GREEN}✅ 运行中${NC}"
    else
        echo -e "  生产前端 (443): ${YELLOW}⚠️ 检查中${NC}"
    fi
}

# 主流程
check_config
stop_dev_services
setup_nginx_dev
start_backend
start_frontend
check_status

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  🎉 开发服务已启动！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}开发环境访问地址:${NC}"
echo -e "  🌐 开发前端: ${GREEN}https://${DOMAIN}:${DEV_NGINX_PORT}${NC} (热重载)"
echo -e "  📡 开发 API: ${GREEN}https://${DOMAIN}:${DEV_NGINX_PORT}/api/${NC}"
echo -e "  📚 API 文档: ${GREEN}http://127.0.0.1:${DEV_BACKEND_PORT}/docs${NC}"
echo ""
echo -e "${BLUE}生产环境访问地址 (不受影响):${NC}"
echo -e "  🌐 生产前端: ${GREEN}https://${DOMAIN}${NC}"
echo -e "  📡 生产 API: ${GREEN}https://${DOMAIN}/api/${NC}"
echo ""
echo -e "${BLUE}日志文件:${NC}"
echo "  后端日志: tail -f $LOG_DIR/backend-dev.log"
echo "  前端日志: tail -f $LOG_DIR/frontend-dev.log"
echo ""
echo -e "${BLUE}停止开发服务:${NC}"
echo "  pkill -f 'vite.*${DEV_FRONTEND_PORT}'      # 停止开发前端"
echo "  pkill -f 'uvicorn.*${DEV_BACKEND_PORT}'   # 停止开发后端"
echo ""
echo -e "${YELLOW}💡 修改前端代码后，浏览器会自动刷新！${NC}"
echo -e "${YELLOW}💡 修改后端代码后，服务会自动重载！${NC}"
echo -e "${YELLOW}💡 开发模式与生产模式完全隔离，互不影响！${NC}"
