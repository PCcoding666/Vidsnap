#!/bin/bash
#
# Clash 代理服务 - 阿里云 Linux 服务器部署脚本
# 适用于: Alibaba Cloud Linux 3.2104 LTS 64位
#
# 使用方法:
#   chmod +x deploy_clash_proxy.sh
#   sudo ./deploy_clash_proxy.sh
#

set -e

# ============ 配置区域 ============
# SakuraCat 订阅链接
SUBSCRIBE_URL="https://sakuracat1203.xn--3iq226gfdb94q.com/api/v1/client/subscribe?token=05ace4d5443787dfed563b4c4ff99e14"

# Clash 配置
CLASH_VERSION="v1.18.0"  # Clash Premium 版本
CLASH_DIR="/opt/clash"
CLASH_CONFIG="${CLASH_DIR}/config.yaml"
HTTP_PORT=7890
SOCKS_PORT=7891
CONTROLLER_PORT=9090

# ============ 颜色输出 ============
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ============ 检查 root 权限 ============
check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "请使用 root 权限运行此脚本"
        log_info "运行: sudo $0"
        exit 1
    fi
}

# ============ 安装依赖 ============
install_dependencies() {
    log_info "安装必要依赖..."
    yum install -y wget curl unzip gzip tar || dnf install -y wget curl unzip gzip tar
}

# ============ 下载 Clash Premium ============
download_clash() {
    log_info "下载 Clash Premium..."
    
    mkdir -p ${CLASH_DIR}
    cd ${CLASH_DIR}
    
    # 检测架构
    ARCH=$(uname -m)
    case ${ARCH} in
        x86_64) CLASH_ARCH="amd64" ;;
        aarch64) CLASH_ARCH="arm64" ;;
        *) log_error "不支持的架构: ${ARCH}"; exit 1 ;;
    esac
    
    # 下载 Clash Premium (使用镜像源)
    CLASH_URL="https://github.com/Dreamacro/clash/releases/download/${CLASH_VERSION}/clash-linux-${CLASH_ARCH}-${CLASH_VERSION}.gz"
    
    log_info "下载地址: ${CLASH_URL}"
    
    if wget -O clash.gz "${CLASH_URL}" 2>/dev/null; then
        gzip -d -f clash.gz
        chmod +x clash
        log_info "Clash Premium 下载成功"
    else
        # 备用方案：下载 Clash Meta (mihomo)
        log_warn "Clash Premium 下载失败，尝试下载 Clash Meta..."
        MIHOMO_URL="https://github.com/MetaCubeX/mihomo/releases/latest/download/mihomo-linux-${CLASH_ARCH}.gz"
        
        if wget -O clash.gz "${MIHOMO_URL}" 2>/dev/null; then
            gzip -d -f clash.gz
            chmod +x clash
            log_info "Clash Meta 下载成功"
        else
            log_error "Clash 下载失败，请检查网络连接"
            exit 1
        fi
    fi
    
    # 验证安装
    ./clash -v && log_info "Clash 安装验证成功"
}

# ============ 下载订阅配置 ============
download_config() {
    log_info "下载订阅配置..."
    
    # 添加 Clash 订阅参数
    FULL_URL="${SUBSCRIBE_URL}&flag=clash"
    
    if curl -sL "${FULL_URL}" -o ${CLASH_CONFIG}; then
        # 检查配置文件是否有效
        if grep -q "proxies:" ${CLASH_CONFIG}; then
            log_info "订阅配置下载成功"
        else
            log_error "配置文件无效，可能需要手动设置"
            create_minimal_config
        fi
    else
        log_error "订阅下载失败"
        exit 1
    fi
    
    # 修改配置文件中的端口设置
    update_config_ports
}

# ============ 更新配置端口 ============
update_config_ports() {
    log_info "更新配置端口..."
    
    # 使用 sed 更新端口配置
    sed -i "s/^port:.*/port: ${HTTP_PORT}/" ${CLASH_CONFIG}
    sed -i "s/^socks-port:.*/socks-port: ${SOCKS_PORT}/" ${CLASH_CONFIG}
    sed -i "s/^external-controller:.*/external-controller: 127.0.0.1:${CONTROLLER_PORT}/" ${CLASH_CONFIG}
    
    # 确保 allow-lan 为 false (安全考虑)
    sed -i "s/^allow-lan:.*/allow-lan: false/" ${CLASH_CONFIG}
    
    log_info "端口配置已更新: HTTP=${HTTP_PORT}, SOCKS=${SOCKS_PORT}"
}

# ============ 创建最小配置 ============
create_minimal_config() {
    log_warn "创建最小配置文件..."
    cat > ${CLASH_CONFIG} << 'EOF'
port: 7890
socks-port: 7891
allow-lan: false
mode: Rule
log-level: info
external-controller: 127.0.0.1:9090

proxies: []
proxy-groups: []
rules:
  - MATCH,DIRECT
EOF
    log_warn "已创建最小配置，请手动更新订阅"
}

# ============ 创建 systemd 服务 ============
create_systemd_service() {
    log_info "创建 systemd 服务..."
    
    cat > /etc/systemd/system/clash.service << EOF
[Unit]
Description=Clash Proxy Service
After=network.target

[Service]
Type=simple
User=root
ExecStart=${CLASH_DIR}/clash -d ${CLASH_DIR}
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    log_info "systemd 服务创建成功"
}

# ============ 创建订阅更新脚本 ============
create_update_script() {
    log_info "创建订阅更新脚本..."
    
    cat > ${CLASH_DIR}/update_subscription.sh << EOF
#!/bin/bash
# 更新 Clash 订阅配置

SUBSCRIBE_URL="${SUBSCRIBE_URL}&flag=clash"
CONFIG_FILE="${CLASH_CONFIG}"

echo "正在更新订阅..."
curl -sL "\${SUBSCRIBE_URL}" -o \${CONFIG_FILE}.tmp

if grep -q "proxies:" \${CONFIG_FILE}.tmp; then
    mv \${CONFIG_FILE}.tmp \${CONFIG_FILE}
    
    # 更新端口配置
    sed -i "s/^port:.*/port: ${HTTP_PORT}/" \${CONFIG_FILE}
    sed -i "s/^socks-port:.*/socks-port: ${SOCKS_PORT}/" \${CONFIG_FILE}
    sed -i "s/^external-controller:.*/external-controller: 127.0.0.1:${CONTROLLER_PORT}/" \${CONFIG_FILE}
    sed -i "s/^allow-lan:.*/allow-lan: false/" \${CONFIG_FILE}
    
    echo "订阅更新成功，正在重启 Clash..."
    systemctl restart clash
    echo "完成!"
else
    rm -f \${CONFIG_FILE}.tmp
    echo "订阅更新失败，保持原配置"
fi
EOF

    chmod +x ${CLASH_DIR}/update_subscription.sh
    log_info "更新脚本创建成功: ${CLASH_DIR}/update_subscription.sh"
}

# ============ 设置定时更新 ============
setup_cron_update() {
    log_info "设置每日自动更新订阅..."
    
    # 每天凌晨 4 点更新订阅
    (crontab -l 2>/dev/null | grep -v "update_subscription"; echo "0 4 * * * ${CLASH_DIR}/update_subscription.sh >> /var/log/clash_update.log 2>&1") | crontab -
    
    log_info "已设置每日 04:00 自动更新订阅"
}

# ============ 启动服务 ============
start_service() {
    log_info "启动 Clash 服务..."
    
    systemctl enable clash
    systemctl start clash
    
    sleep 2
    
    if systemctl is-active --quiet clash; then
        log_info "Clash 服务启动成功!"
    else
        log_error "Clash 服务启动失败"
        journalctl -u clash -n 20
        exit 1
    fi
}

# ============ 测试代理 ============
test_proxy() {
    log_info "测试代理连接..."
    
    sleep 3
    
    # 测试 HTTP 代理
    if curl -x http://127.0.0.1:${HTTP_PORT} -s --connect-timeout 10 https://www.google.com > /dev/null 2>&1; then
        log_info "✅ 代理测试成功! 可以访问 Google"
    else
        log_warn "⚠️ 代理测试失败，请检查节点配置"
        log_info "可以使用以下命令手动测试:"
        log_info "  curl -x http://127.0.0.1:${HTTP_PORT} https://www.google.com"
    fi
}

# ============ 打印使用说明 ============
print_usage() {
    echo ""
    echo "=============================================="
    echo -e "${GREEN}Clash 代理服务部署完成!${NC}"
    echo "=============================================="
    echo ""
    echo "代理配置:"
    echo "  HTTP 代理:  http://127.0.0.1:${HTTP_PORT}"
    echo "  SOCKS 代理: socks5://127.0.0.1:${SOCKS_PORT}"
    echo "  控制面板:   http://127.0.0.1:${CONTROLLER_PORT}"
    echo ""
    echo "在应用中使用代理 (yt-dlp 示例):"
    echo "  yt-dlp --proxy http://127.0.0.1:${HTTP_PORT} [YouTube_URL]"
    echo ""
    echo "服务管理命令:"
    echo "  启动:   systemctl start clash"
    echo "  停止:   systemctl stop clash"
    echo "  重启:   systemctl restart clash"
    echo "  状态:   systemctl status clash"
    echo "  日志:   journalctl -u clash -f"
    echo ""
    echo "更新订阅:"
    echo "  ${CLASH_DIR}/update_subscription.sh"
    echo ""
    echo "配置文件位置:"
    echo "  ${CLASH_CONFIG}"
    echo ""
    echo "=============================================="
}

# ============ 主流程 ============
main() {
    echo ""
    echo "=============================================="
    echo "  Clash 代理服务部署脚本"
    echo "  适用于: Alibaba Cloud Linux 3"
    echo "=============================================="
    echo ""
    
    check_root
    install_dependencies
    download_clash
    download_config
    create_systemd_service
    create_update_script
    setup_cron_update
    start_service
    test_proxy
    print_usage
}

# 运行主流程
main
