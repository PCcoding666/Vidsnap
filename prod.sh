#!/bin/bash
# ============================================================
# 生产模式部署脚本 (nohup 后台运行)
# - 前端: 8080 端口 + vidsnap-test.space 域名
# - 后端: 8000 端口
# - Celery Worker & Beat: 后台任务处理
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
SSL_CERT="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"
SSL_KEY="/etc/letsencrypt/live/$DOMAIN/privkey.pem"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  VidSnap 生产模式部署 (nohup)${NC}"
echo -e "${BLUE}  域名: https://$DOMAIN${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 停止生产模式所有服务（确保彻底重启）
stop_services() {
    echo -e "${YELLOW}🛑 停止生产模式所有服务...${NC}"
    
    # 停止生产后端 (8000) - 彻底清理
    pkill -f "uvicorn.*8000[^0-9]" 2>/dev/null || true
    pkill -f "uvicorn.*--port 8000" 2>/dev/null || true
    pkill -9 -f "uvicorn.*8000" 2>/dev/null || true
    systemctl stop vidsnap-backend 2>/dev/null || true
    fuser -k 8000/tcp 2>/dev/null || true
    
    # 强制释放 8000 端口
    for pid in $(lsof -t -i:8000 2>/dev/null); do
        echo "  杀掉占用 8000 端口的进程: $pid"
        kill -9 $pid 2>/dev/null || true
    done
    
    # 停止所有 Celery 进程
    echo -e "${YELLOW}  停止 Celery 服务...${NC}"
    pkill -f "celery.*app.core.celery_app.*worker" 2>/dev/null || true
    pkill -f "celery.*app.core.celery_app.*beat" 2>/dev/null || true
    pkill -9 -f "celery.*app.core.celery_app" 2>/dev/null || true
    
    # 停止前端静态服务
    pkill -f "serve.*8080" 2>/dev/null || true
    pkill -f "python.*http.server.*8080" 2>/dev/null || true
    fuser -k 8080/tcp 2>/dev/null || true
    
    sleep 2
    
    # 验证端口已释放
    if ss -tlnp | grep -q ":8000 \|:8080 "; then
        echo -e "${RED}⚠️ 警告：端口可能未完全释放${NC}"
        ss -tlnp | grep -E ":8000 |:8080 "
    else
        echo -e "${GREEN}✅ 所有生产服务已完全停止，端口已释放${NC}"
    fi
}

# 检查配置和依赖
check_config() {
    echo -e "${BLUE}🔍 检查配置和依赖...${NC}"
    
    local has_error=false
    
    # 检查 Deno
    if command -v deno &> /dev/null; then
        DENO_VERSION=$(deno --version | head -1 | awk '{print $2}')
        echo -e "  Deno: ${GREEN}✅ v${DENO_VERSION}${NC}"
    else
        echo -e "  Deno: ${RED}❌ 未安装 (YouTube 下载将失败)${NC}"
        has_error=true
    fi
    
    # 检查 FFmpeg
    if command -v ffmpeg &> /dev/null; then
        echo -e "  FFmpeg: ${GREEN}✅ 已安装${NC}"
    else
        echo -e "  FFmpeg: ${RED}❌ 未安装 (视频处理将失败)${NC}"
        has_error=true
    fi
    
    # 检查 Cookies 文件
    COOKIES_FILE="$PROJECT_DIR/backend/youtube_cookies.txt"
    if [ -f "$COOKIES_FILE" ]; then
        COOKIES_SIZE=$(stat -c%s "$COOKIES_FILE" 2>/dev/null || stat -f%z "$COOKIES_FILE" 2>/dev/null)
        if [ "$COOKIES_SIZE" -gt 1000 ]; then
            echo -e "  YouTube Cookies: ${GREEN}✅ 已配置 (${COOKIES_SIZE} bytes)${NC}"
        else
            echo -e "  YouTube Cookies: ${YELLOW}⚠️ 文件过小 (${COOKIES_SIZE} bytes)${NC}"
        fi
    else
        echo -e "  YouTube Cookies: ${RED}❌ 未配置 (YouTube 下载将失败)${NC}"
        has_error=true
    fi
    
    # 检查 .env 文件
    if [ -f "$PROJECT_DIR/backend/.env" ]; then
        echo -e "  环境变量: ${GREEN}✅ .env 文件存在${NC}"
        
        # 检查关键配置
        if grep -q "QWEN_API_KEY" "$PROJECT_DIR/backend/.env"; then
            echo -e "    - QWEN_API_KEY: ${GREEN}✅${NC}"
        else
            echo -e "    - QWEN_API_KEY: ${RED}❌ 未配置${NC}"
            has_error=true
        fi
        
        if grep -q "SUPABASE_URL" "$PROJECT_DIR/backend/.env"; then
            echo -e "    - SUPABASE_URL: ${GREEN}✅${NC}"
        else
            echo -e "    - SUPABASE_URL: ${RED}❌ 未配置${NC}"
            has_error=true
        fi
    else
        echo -e "  环境变量: ${RED}❌ .env 文件不存在${NC}"
        has_error=true
    fi
    
    # 检查 Redis (Celery 需要)
    if command -v redis-cli &> /dev/null; then
        if redis-cli ping &> /dev/null; then
            echo -e "  Redis: ${GREEN}✅ 运行中${NC}"
        else
            echo -e "  Redis: ${YELLOW}⚠️ 已安装但未运行${NC}"
        fi
    else
        echo -e "  Redis: ${YELLOW}⚠️ 未安装 (频道监控功能不可用)${NC}"
    fi
    
    echo ""
    
    if [ "$has_error" = true ]; then
        echo -e "${RED}❌ 发现配置问题，请修复后再运行！${NC}"
        exit 1
    fi
}

# 构建前端
build_frontend() {
    echo -e "${BLUE}📦 构建前端...${NC}"
    cd "$PROJECT_DIR/frontend"
    
    # 安装依赖（如果需要）
    if [ ! -d "node_modules" ]; then
        echo -e "${YELLOW}安装前端依赖...${NC}"
        npm install
    fi
    
    # 构建生产版本
    npm run build
    
    echo -e "${GREEN}✅ 前端构建完成${NC}"
}

# 配置 Nginx
setup_nginx() {
    echo -e "${BLUE}🔧 配置 Nginx...${NC}"
    
    # 检查 SSL 证书是否存在
    if [ -f "$SSL_CERT" ] && [ -f "$SSL_KEY" ]; then
        echo -e "${GREEN}✅ 发现 SSL 证书，配置 HTTPS${NC}"
        HAS_SSL=true
    else
        echo -e "${YELLOW}⚠️ 未找到 SSL 证书，仅配置 HTTP${NC}"
        HAS_SSL=false
    fi
    
    # 域名配置 (vidsnap-test.space)
    if [ "$HAS_SSL" = true ]; then
        cat > /www/server/panel/vhost/nginx/vidsnap-test.space.conf << EOF
# HTTP 重定向到 HTTPS
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;
    return 301 https://\$server_name\$request_uri;
}

# HTTPS 配置
server {
    listen 443 ssl;
    http2 on;
    server_name $DOMAIN www.$DOMAIN;
    
    # SSL 证书
    ssl_certificate $SSL_CERT;
    ssl_certificate_key $SSL_KEY;
    
    # SSL 安全配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    
    # 前端静态文件
    root $PROJECT_DIR/frontend/dist;
    index index.html;
    
    # 前端路由（SPA）
    location / {
        try_files \$uri \$uri/ /index.html;
    }
    
    # 后端 API 代理
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 60s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
        client_max_body_size 500M;
    }
    
    # API 文档
    location /docs {
        proxy_pass http://127.0.0.1:8000/docs;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
    
    location /openapi.json {
        proxy_pass http://127.0.0.1:8000/openapi.json;
        proxy_set_header Host \$host;
    }
    
    # 静态资源缓存
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)\$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
    
    # Gzip 压缩
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml text/javascript;
    gzip_min_length 1000;
    
    access_log /www/wwwlogs/vidsnap-test.space.log;
    error_log /www/wwwlogs/vidsnap-test.space.error.log;
}
EOF
    else
        cat > /www/server/panel/vhost/nginx/vidsnap-test.space.conf << EOF
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;
    
    root $PROJECT_DIR/frontend/dist;
    index index.html;
    
    location / {
        try_files \$uri \$uri/ /index.html;
    }
    
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        client_max_body_size 500M;
    }
    
    location /docs {
        proxy_pass http://127.0.0.1:8000/docs;
    }
    
    location /openapi.json {
        proxy_pass http://127.0.0.1:8000/openapi.json;
    }
    
    access_log /www/wwwlogs/vidsnap-test.space.log;
    error_log /www/wwwlogs/vidsnap-test.space.error.log;
}
EOF
    fi

    # 8080 端口配置（IP 访问）
    cat > /www/server/panel/vhost/nginx/vidsnap-prod-8080.conf << EOF
server {
    listen 8080;
    server_name _;
    
    root $PROJECT_DIR/frontend/dist;
    index index.html;
    
    location / {
        try_files \$uri \$uri/ /index.html;
    }
    
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        client_max_body_size 500M;
    }
    
    location /docs {
        proxy_pass http://127.0.0.1:8000/docs;
    }
    
    location /openapi.json {
        proxy_pass http://127.0.0.1:8000/openapi.json;
    }
}
EOF

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
    
    echo -e "${GREEN}✅ Nginx 配置完成${NC}"
}

# 启动后端
start_backend() {
    echo -e "${GREEN}🚀 启动后端服务...${NC}"
    
    cd "$PROJECT_DIR/backend"
    source venv/bin/activate
    
    # 设置 Deno 环境变量
    export DENO_INSTALL="$HOME/.deno"
    export PATH="$DENO_INSTALL/bin:$PATH"
    
    nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 \
        > "$LOG_DIR/backend-prod.log" 2>&1 &
    
    echo $! > "$LOG_DIR/backend-prod.pid"
    echo -e "${GREEN}✅ 后端 PID: $(cat $LOG_DIR/backend-prod.pid)${NC}"
    
    # 等待后端启动并检查配置
    echo -e "${YELLOW}⏳ 等待后端初始化...${NC}"
    sleep 8
    
    # 检查配置加载状态
    if grep -q "YouTube Cookies 已启用" "$LOG_DIR/backend-prod.log" 2>/dev/null; then
        echo -e "  ${GREEN}✅ YouTube Cookies 已加载${NC}"
    else
        echo -e "  ${RED}❌ YouTube Cookies 未加载（检查日志）${NC}"
    fi
    
    if grep -q "代理" "$LOG_DIR/backend-prod.log" 2>/dev/null; then
        if grep -q "YouTube 代理已启用" "$LOG_DIR/backend-prod.log"; then
            PROXY_URL=$(grep "YouTube 代理已启用" "$LOG_DIR/backend-prod.log" | tail -1 | cut -d: -f3-)
            echo -e "  ${GREEN}✅ 代理已启用:${PROXY_URL}${NC}"
        else
            echo -e "  ${YELLOW}ℹ️  使用直连（未配置代理）${NC}"
        fi
    fi
}

# 检查并启动 Redis
check_redis() {
    echo -e "${BLUE}🔍 检查 Redis 服务...${NC}"
    
    if command -v redis-server &> /dev/null; then
        if pgrep redis-server > /dev/null; then
            echo -e "${GREEN}✅ Redis 已运行${NC}"
        else
            echo -e "${YELLOW}启动 Redis...${NC}"
            redis-server --daemonize yes
            sleep 2
            echo -e "${GREEN}✅ Redis 已启动${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️ Redis 未安装，频道监控功能将不可用${NC}"
        echo -e "${YELLOW}   安装命令: yum install redis 或 apt install redis-server${NC}"
        return 1
    fi
    return 0
}

# 启动 Celery Worker 和 Beat
start_celery() {
    echo -e "${GREEN}🚀 启动 Celery 服务...${NC}"
    
    # 检查 Redis 是否可用
    if ! check_redis; then
        echo -e "${YELLOW}⚠️ 跳过 Celery 启动${NC}"
        return
    fi
    
    cd "$PROJECT_DIR/backend"
    source venv/bin/activate
    
    # 设置 Deno 环境变量
    export DENO_INSTALL="$HOME/.deno"
    export PATH="$DENO_INSTALL/bin:$PATH"
    
    # 启动 Celery Worker
    echo -e "${YELLOW}启动 Celery Worker...${NC}"
    nohup celery -A app.core.celery_app worker \
        --loglevel=info \
        --concurrency=2 \
        -Q default,monitor,analysis \
        > "$LOG_DIR/celery-worker.log" 2>&1 &
    
    echo $! > "$LOG_DIR/celery-worker.pid"
    echo -e "${GREEN}✅ Celery Worker PID: $(cat $LOG_DIR/celery-worker.pid)${NC}"
    
    # 启动 Celery Beat (定时任务调度器)
    echo -e "${YELLOW}启动 Celery Beat...${NC}"
    nohup celery -A app.core.celery_app beat \
        --loglevel=info \
        > "$LOG_DIR/celery-beat.log" 2>&1 &
    
    echo $! > "$LOG_DIR/celery-beat.pid"
    echo -e "${GREEN}✅ Celery Beat PID: $(cat $LOG_DIR/celery-beat.pid)${NC}"
    
    # 等待 Celery 初始化
    echo -e "${YELLOW}⏳ 等待 Celery 初始化...${NC}"
    sleep 5
    
    # 检查 Celery Worker 的配置加载
    if grep -q "YouTube Cookies 已启用" "$LOG_DIR/celery-worker.log" 2>/dev/null; then
        echo -e "  ${GREEN}✅ Celery Worker 已加载 Cookies${NC}"
    else
        echo -e "  ${YELLOW}⚠️ Celery Worker Cookies 状态未知（检查日志）${NC}"
    fi
}

# 检查服务状态
check_status() {
    sleep 3
    echo ""
    echo -e "${BLUE}📊 服务状态:${NC}"
    
    # 后端
    if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/docs | grep -q "200"; then
        echo -e "  后端 (8000): ${GREEN}✅ 运行中${NC}"
    else
        echo -e "  后端 (8000): ${RED}❌ 启动失败（检查日志）${NC}"
    fi
    
    # 前端 8080
    if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/ | grep -q "200"; then
        echo -e "  前端 (8080): ${GREEN}✅ 运行中${NC}"
    else
        echo -e "  前端 (8080): ${YELLOW}⏳ 启动中...${NC}"
    fi
    
    # 域名
    if curl -s -o /dev/null -w "%{http_code}" -H "Host: $DOMAIN" http://127.0.0.1/ | grep -q "200"; then
        echo -e "  域名 ($DOMAIN): ${GREEN}✅ 运行中${NC}"
    else
        echo -e "  域名 ($DOMAIN): ${YELLOW}⏳ 检查中...${NC}"
    fi
    
    # Nginx
    if pgrep nginx > /dev/null; then
        echo -e "  Nginx: ${GREEN}✅ 运行中${NC}"
    else
        echo -e "  Nginx: ${RED}❌ 未运行${NC}"
    fi
    
    # Redis
    if pgrep redis-server > /dev/null; then
        echo -e "  Redis: ${GREEN}✅ 运行中${NC}"
    else
        echo -e "  Redis: ${YELLOW}⚠️ 未运行 (频道监控不可用)${NC}"
    fi
    
    # Celery Worker
    if pgrep -f "celery.*worker" > /dev/null; then
        echo -e "  Celery Worker: ${GREEN}✅ 运行中${NC}"
    else
        echo -e "  Celery Worker: ${YELLOW}⚠️ 未运行${NC}"
    fi
    
    # Celery Beat
    if pgrep -f "celery.*beat" > /dev/null; then
        echo -e "  Celery Beat: ${GREEN}✅ 运行中${NC}"
    else
        echo -e "  Celery Beat: ${YELLOW}⚠️ 未运行${NC}"
    fi
}

# 主流程
check_config
stop_services

echo -e "${YELLOW}步骤 1/4: 构建前端${NC}"
build_frontend
echo ""

echo -e "${YELLOW}步骤 2/4: 配置 Nginx${NC}"
setup_nginx
echo ""

echo -e "${YELLOW}步骤 3/4: 启动后端${NC}"
start_backend
echo ""

echo -e "${YELLOW}步骤 4/4: 启动 Celery (频道监控 + 视频分析)${NC}"
start_celery

check_status

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  🎉 生产部署完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}访问地址:${NC}"
if [ -f "$SSL_CERT" ]; then
    echo -e "  🌐 网站:     ${GREEN}https://$DOMAIN${NC}"
    echo -e "  📚 API 文档: ${GREEN}https://$DOMAIN/docs${NC}"
else
    echo -e "  🌐 网站:     ${GREEN}http://$DOMAIN${NC}"
    echo -e "  📚 API 文档: ${GREEN}http://$DOMAIN/docs${NC}"
fi
echo ""
echo -e "${BLUE}日志文件:${NC}"
echo "  后端日志:       tail -f $LOG_DIR/backend-prod.log"
echo "  Celery Worker:  tail -f $LOG_DIR/celery-worker.log"
echo "  Celery Beat:    tail -f $LOG_DIR/celery-beat.log"
echo "  Nginx 日志:     tail -f /www/wwwlogs/vidsnap-test.space.log"
echo ""
echo -e "${BLUE}停止服务:${NC}"
echo "  pkill -f 'uvicorn.*8000'         # 停止后端"
echo "  pkill -f 'celery.*app.core'     # 停止 Celery"
echo "  或直接重新运行此脚本会自动重启所有服务"
echo ""
echo -e "${YELLOW}💡 所有服务已使用最新配置启动${NC}"
echo -e "${YELLOW}💡 YouTube 下载功能已配置 Cookies${NC}"
echo -e "${YELLOW}💡 Celery 服务负责频道监控和视频分析${NC}"
