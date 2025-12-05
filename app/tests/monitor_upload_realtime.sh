#!/bin/bash

#################################################################################
# 视频上传实时监控脚本
# 
# 功能: 实时监控视频上传过程，包括磁盘空间、资源使用、日志输出
# 
# 使用方法:
#   bash app/tests/monitor_upload_realtime.sh [选项]
# 
# 选项:
#   --interval SECONDS   监控间隔(秒) (默认: 2)
#   --log-file FILE      要监控的日志文件
#   --duration SECONDS   监控持续时间(秒) (默认: 无限制)
#   --help               显示帮助信息
# 
# 示例:
#   bash app/tests/monitor_upload_realtime.sh
#   bash app/tests/monitor_upload_realtime.sh --interval 5
#   bash app/tests/monitor_upload_realtime.sh --duration 300
#################################################################################

set -e

# ==================== 配置参数 ====================
INTERVAL=2
LOG_FILE=""
DURATION=0
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# ==================== 颜色定义 ====================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ==================== 辅助函数 ====================
print_header() {
    clear
    echo -e "${CYAN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║         ${BOLD}视频上传实时监控工具${NC}${CYAN}                              ║${NC}"
    echo -e "${CYAN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "监控时间: ${CYAN}$(date '+%Y-%m-%d %H:%M:%S')${NC}"
    echo -e "刷新间隔: ${YELLOW}${INTERVAL}秒${NC}"
    echo ""
}

format_bytes() {
    local bytes=$1
    if [ "$bytes" -ge 1073741824 ]; then
        echo "$(awk "BEGIN {printf \"%.2f\", $bytes/1073741824}")GB"
    elif [ "$bytes" -ge 1048576 ]; then
        echo "$(awk "BEGIN {printf \"%.2f\", $bytes/1048576}")MB"
    elif [ "$bytes" -ge 1024 ]; then
        echo "$(awk "BEGIN {printf \"%.2f\", $bytes/1024}")KB"
    else
        echo "${bytes}B"
    fi
}

# ==================== 参数解析 ====================
while [[ $# -gt 0 ]]; do
    case $1 in
        --interval)
            INTERVAL="$2"
            shift 2
            ;;
        --log-file)
            LOG_FILE="$2"
            shift 2
            ;;
        --duration)
            DURATION="$2"
            shift 2
            ;;
        --help)
            head -n 20 "$0" | grep "^#" | sed 's/^# //g' | sed 's/^#//g'
            exit 0
            ;;
        *)
            echo "未知选项: $1"
            echo "使用 --help 查看帮助信息"
            exit 1
            ;;
    esac
done

# ==================== 初始化 ====================
START_TIME=$(date +%s)
MONITOR_COUNT=0

# 捕获 Ctrl+C
trap 'echo -e "\n\n${YELLOW}监控已停止${NC}"; exit 0' INT TERM

# ==================== 监控循环 ====================
while true; do
    print_header
    
    # ==================== 1. 磁盘空间监控 ====================
    echo -e "${BLUE}${BOLD}=== 磁盘空间 ===${NC}"
    echo ""
    
    # /tmp 目录
    tmp_total=$(df -B1 /tmp 2>/dev/null | awk 'NR==2 {print $2}' || echo "0")
    tmp_used=$(df -B1 /tmp 2>/dev/null | awk 'NR==2 {print $3}' || echo "0")
    tmp_available=$(df -B1 /tmp 2>/dev/null | awk 'NR==2 {print $4}' || echo "0")
    tmp_percent=$(df /tmp 2>/dev/null | awk 'NR==2 {print $5}' | sed 's/%//' || echo "0")
    
    echo -e "${CYAN}/tmp 目录:${NC}"
    echo -e "  总空间:   $(format_bytes $tmp_total)"
    echo -e "  已使用:   $(format_bytes $tmp_used) (${tmp_percent}%)"
    echo -e "  可用:     ${GREEN}$(format_bytes $tmp_available)${NC}"
    
    # 绘制使用率条形图
    bar_length=40
    filled=$((tmp_percent * bar_length / 100))
    empty=$((bar_length - filled))
    
    if [ "$tmp_percent" -ge 90 ]; then
        bar_color=$RED
    elif [ "$tmp_percent" -ge 70 ]; then
        bar_color=$YELLOW
    else
        bar_color=$GREEN
    fi
    
    printf "  使用率:   ${bar_color}["
    printf "%${filled}s" | tr ' ' '█'
    printf "%${empty}s" | tr ' ' '░'
    printf "]${NC} ${tmp_percent}%%\n"
    
    # 项目临时目录
    echo ""
    TEMP_DIR="/tmp/aliyun_video_service"
    if [ -d "$TEMP_DIR" ]; then
        temp_size=$(du -sb "$TEMP_DIR" 2>/dev/null | awk '{print $1}' || echo "0")
        temp_files=$(find "$TEMP_DIR" -type f 2>/dev/null | wc -l || echo "0")
        
        echo -e "${CYAN}项目临时目录:${NC} $TEMP_DIR"
        echo -e "  占用空间: $(format_bytes $temp_size)"
        echo -e "  文件数量: $temp_files"
    fi
    
    # ==================== 2. 系统资源监控 ====================
    echo ""
    echo -e "${BLUE}${BOLD}=== 系统资源 ===${NC}"
    echo ""
    
    # CPU 使用率
    if command -v top &> /dev/null; then
        cpu_usage=$(top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print 100 - $1}')
        echo -e "${CYAN}CPU 使用率:${NC} ${cpu_usage}%"
    fi
    
    # 内存使用
    if command -v free &> /dev/null; then
        mem_total=$(free -b | awk 'NR==2 {print $2}')
        mem_used=$(free -b | awk 'NR==2 {print $3}')
        mem_available=$(free -b | awk 'NR==2 {print $7}')
        mem_percent=$(awk "BEGIN {printf \"%.0f\", ($mem_used/$mem_total)*100}")
        
        echo -e "${CYAN}内存使用:${NC}"
        echo -e "  总内存:   $(format_bytes $mem_total)"
        echo -e "  已使用:   $(format_bytes $mem_used) (${mem_percent}%)"
        echo -e "  可用:     ${GREEN}$(format_bytes $mem_available)${NC}"
        
        # 内存使用率条形图
        mem_filled=$((mem_percent * bar_length / 100))
        mem_empty=$((bar_length - mem_filled))
        
        if [ "$mem_percent" -ge 90 ]; then
            mem_color=$RED
        elif [ "$mem_percent" -ge 70 ]; then
            mem_color=$YELLOW
        else
            mem_color=$GREEN
        fi
        
        printf "  使用率:   ${mem_color}["
        printf "%${mem_filled}s" | tr ' ' '█'
        printf "%${mem_empty}s" | tr ' ' '░'
        printf "]${NC} ${mem_percent}%%\n"
    fi
    
    # ==================== 3. 进程监控 ====================
    echo ""
    echo -e "${BLUE}${BOLD}=== FastAPI 进程 ===${NC}"
    echo ""
    
    # 查找 uvicorn/FastAPI 进程
    if pgrep -f "uvicorn.*app.main" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} FastAPI 服务运行中"
        
        # 获取进程信息
        pid=$(pgrep -f "uvicorn.*app.main" | head -1)
        if [ -n "$pid" ]; then
            if command -v ps &> /dev/null; then
                ps_info=$(ps -p $pid -o %cpu,%mem,vsz,rss,etime 2>/dev/null | tail -1)
                cpu=$(echo $ps_info | awk '{print $1}')
                mem=$(echo $ps_info | awk '{print $2}')
                vsz=$(echo $ps_info | awk '{print $3}')
                rss=$(echo $ps_info | awk '{print $4}')
                etime=$(echo $ps_info | awk '{print $5}')
                
                echo -e "  PID:      $pid"
                echo -e "  CPU:      ${cpu}%"
                echo -e "  内存:     ${mem}%"
                echo -e "  虚拟内存: $(format_bytes $((vsz * 1024)))"
                echo -e "  物理内存: $(format_bytes $((rss * 1024)))"
                echo -e "  运行时间: $etime"
            fi
        fi
    else
        echo -e "${RED}✗${NC} FastAPI 服务未运行"
    fi
    
    # ==================== 4. 网络监控 ====================
    echo ""
    echo -e "${BLUE}${BOLD}=== 网络连接 ===${NC}"
    echo ""
    
    # 检查 API 端口
    if command -v netstat &> /dev/null || command -v ss &> /dev/null; then
        if netstat -tuln 2>/dev/null | grep -q ":8000" || ss -tuln 2>/dev/null | grep -q ":8000"; then
            echo -e "${GREEN}✓${NC} 端口 8000 正在监听"
        else
            echo -e "${RED}✗${NC} 端口 8000 未监听"
        fi
    fi
    
    # 检查活动连接
    if command -v netstat &> /dev/null; then
        active_conns=$(netstat -an 2>/dev/null | grep ":8000" | grep ESTABLISHED | wc -l || echo "0")
        echo -e "${CYAN}活动连接数:${NC} $active_conns"
    fi
    
    # ==================== 5. 最近日志 ====================
    echo ""
    echo -e "${BLUE}${BOLD}=== 最近日志 (上传相关) ===${NC}"
    echo ""
    
    if [ -n "$LOG_FILE" ] && [ -f "$LOG_FILE" ]; then
        # 显示最后5条上传相关日志
        grep -i "upload\|video_file\|process_video" "$LOG_FILE" 2>/dev/null | tail -5 | while read -r line; do
            # 截断过长的行
            short_line=$(echo "$line" | cut -c1-100)
            
            # 根据日志级别着色
            if echo "$line" | grep -qi "error\|fail"; then
                echo -e "  ${RED}${short_line}${NC}"
            elif echo "$line" | grep -qi "warn"; then
                echo -e "  ${YELLOW}${short_line}${NC}"
            elif echo "$line" | grep -qi "success\|complete"; then
                echo -e "  ${GREEN}${short_line}${NC}"
            else
                echo -e "  ${short_line}"
            fi
        done
    else
        # 尝试使用 journalctl
        if command -v journalctl &> /dev/null; then
            journalctl -u uvicorn -n 5 --no-pager 2>/dev/null | grep -i "upload\|video" | while read -r line; do
                short_line=$(echo "$line" | cut -c1-100)
                echo -e "  ${short_line}"
            done
        else
            echo -e "  ${YELLOW}未指定日志文件${NC}"
        fi
    fi
    
    # ==================== 6. 监控统计 ====================
    echo ""
    echo -e "${CYAN}─────────────────────────────────────────────────────────────${NC}"
    
    ((MONITOR_COUNT++))
    elapsed=$(($(date +%s) - START_TIME))
    elapsed_formatted=$(printf '%02d:%02d:%02d' $((elapsed/3600)) $((elapsed%3600/60)) $((elapsed%60)))
    
    echo -e "监控次数: $MONITOR_COUNT  |  运行时间: $elapsed_formatted"
    echo -e "${YELLOW}按 Ctrl+C 停止监控${NC}"
    
    # 检查是否达到持续时间
    if [ "$DURATION" -gt 0 ] && [ "$elapsed" -ge "$DURATION" ]; then
        echo ""
        echo -e "${GREEN}✓ 已达到指定监控时间${NC}"
        break
    fi
    
    # 等待下一次刷新
    sleep "$INTERVAL"
done

echo ""
echo -e "${CYAN}监控结束${NC}"
