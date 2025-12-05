#!/bin/bash

#################################################################################
# 视频上传环境检查脚本
# 
# 功能: 自动检查服务器环境配置，诊断可能导致视频上传失败的问题
# 
# 使用方法:
#   bash app/tests/check_server_environment.sh [选项]
# 
# 选项:
#   --json          以JSON格式输出结果
#   --log FILE      将结果保存到日志文件
#   --verbose       显示详细信息
#   --help          显示帮助信息
# 
# 示例:
#   bash app/tests/check_server_environment.sh
#   bash app/tests/check_server_environment.sh --json
#   bash app/tests/check_server_environment.sh --log check.log
#################################################################################

set -e

# ==================== 配置参数 ====================
OUTPUT_JSON=false
LOG_FILE=""
VERBOSE=false
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# ==================== 颜色定义 ====================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ==================== 辅助函数 ====================
print_header() {
    echo -e "${CYAN}=========================================${NC}"
    echo -e "${CYAN}  视频上传环境诊断工具 v1.0${NC}"
    echo -e "${CYAN}  开始时间: $(date '+%Y-%m-%d %H:%M:%S')${NC}"
    echo -e "${CYAN}=========================================${NC}"
    echo ""
}

check_pass() {
    echo -e "${GREEN}[✓]${NC} $1"
}

check_fail() {
    echo -e "${RED}[✗]${NC} $1"
}

check_warn() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_section() {
    echo ""
    echo -e "${BLUE}>>> $1${NC}"
    echo ""
}

# ==================== 参数解析 ====================
while [[ $# -gt 0 ]]; do
    case $1 in
        --json)
            OUTPUT_JSON=true
            shift
            ;;
        --log)
            LOG_FILE="$2"
            shift 2
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --help)
            head -n 25 "$0" | grep "^#" | sed 's/^# //g' | sed 's/^#//g'
            exit 0
            ;;
        *)
            echo "未知选项: $1"
            echo "使用 --help 查看帮助信息"
            exit 1
            ;;
    esac
done

# ==================== 开始检查 ====================
if [ "$OUTPUT_JSON" = false ]; then
    print_header
fi

# 存储检查结果
declare -A results

# ==================== 1. 文件系统检查 ====================
print_section "1. 文件系统检查"

# 1.1 检查 /tmp 目录
echo "1.1 检查 /tmp 目录"
if [ -d "/tmp" ]; then
    check_pass "/tmp 目录存在"
    results[tmp_exists]="pass"
    
    # 检查权限
    if [ -w "/tmp" ]; then
        check_pass "/tmp 目录可写"
        results[tmp_writable]="pass"
    else
        check_fail "/tmp 目录不可写 (权限问题)"
        results[tmp_writable]="fail"
    fi
    
    # 检查磁盘空间
    tmp_available=$(df -BG /tmp 2>/dev/null | awk 'NR==2 {print $4}' | sed 's/G//' || echo "0")
    if [ "$tmp_available" -gt 10 ]; then
        check_pass "/tmp 可用空间: ${tmp_available}GB (充足)"
        results[tmp_space]="pass"
    elif [ "$tmp_available" -gt 5 ]; then
        check_warn "/tmp 可用空间: ${tmp_available}GB (建议清理)"
        results[tmp_space]="warning"
    else
        check_fail "/tmp 可用空间: ${tmp_available}GB (不足,需清理)"
        results[tmp_space]="fail"
    fi
    results[tmp_space_gb]="$tmp_available"
    
    # 检查 inode 使用率
    tmp_inode_use=$(df -i /tmp 2>/dev/null | awk 'NR==2 {print $5}' | sed 's/%//' || echo "0")
    if [ "$tmp_inode_use" -lt 80 ]; then
        check_pass "/tmp inode 使用率: ${tmp_inode_use}% (正常)"
        results[tmp_inodes]="pass"
    else
        check_warn "/tmp inode 使用率: ${tmp_inode_use}% (过高)"
        results[tmp_inodes]="warning"
    fi
    results[tmp_inode_percent]="$tmp_inode_use"
else
    check_fail "/tmp 目录不存在"
    results[tmp_exists]="fail"
fi

# 1.2 检查项目临时目录
echo ""
echo "1.2 检查项目临时目录"
TEMP_DIR="/tmp/aliyun_video_service"
if [ -d "$TEMP_DIR" ]; then
    check_pass "项目临时目录存在: $TEMP_DIR"
    results[project_temp_exists]="pass"
    
    # 检查目录大小
    dir_size=$(du -sh "$TEMP_DIR" 2>/dev/null | awk '{print $1}')
    echo "   目录大小: $dir_size"
    results[project_temp_size]="$dir_size"
    
    # 检查文件数量
    file_count=$(find "$TEMP_DIR" -type f 2>/dev/null | wc -l)
    echo "   文件数量: $file_count"
    results[project_temp_files]="$file_count"
    
    if [ "$file_count" -gt 100 ]; then
        check_warn "临时文件较多，建议清理: $file_count 个文件"
    fi
else
    check_warn "项目临时目录不存在: $TEMP_DIR (首次运行时正常)"
    results[project_temp_exists]="not_found"
fi

# 1.3 检查项目目录权限
echo ""
echo "1.3 检查项目目录权限"
if [ -d "$PROJECT_ROOT" ]; then
    check_pass "项目根目录存在: $PROJECT_ROOT"
    results[project_root_exists]="pass"
    
    if [ -w "$PROJECT_ROOT" ]; then
        check_pass "项目目录可写"
        results[project_root_writable]="pass"
    else
        check_fail "项目目录不可写 (权限问题)"
        results[project_root_writable]="fail"
    fi
else
    check_fail "项目根目录不存在: $PROJECT_ROOT"
    results[project_root_exists]="fail"
fi

# ==================== 2. 系统资源检查 ====================
print_section "2. 系统资源限制"

# 2.1 文件描述符限制
echo "2.1 文件描述符限制 (ulimit -n)"
ulimit_n=$(ulimit -n)
echo "   当前值: $ulimit_n"
results[ulimit_n]="$ulimit_n"

if [ "$ulimit_n" -ge 4096 ]; then
    check_pass "文件描述符限制充足: $ulimit_n"
    results[ulimit_n_status]="pass"
elif [ "$ulimit_n" -ge 1024 ]; then
    check_warn "文件描述符限制较低: $ulimit_n (建议设置为 4096 以上)"
    results[ulimit_n_status]="warning"
else
    check_fail "文件描述符限制过低: $ulimit_n (可能导致文件操作失败)"
    results[ulimit_n_status]="fail"
fi

# 2.2 最大进程数限制
echo ""
echo "2.2 最大进程数限制 (ulimit -u)"
ulimit_u=$(ulimit -u)
echo "   当前值: $ulimit_u"
results[ulimit_u]="$ulimit_u"

if [ "$ulimit_u" -ge 4096 ]; then
    check_pass "进程数限制充足: $ulimit_u"
    results[ulimit_u_status]="pass"
else
    check_warn "进程数限制较低: $ulimit_u"
    results[ulimit_u_status]="warning"
fi

# 2.3 内存使用情况
echo ""
echo "2.3 系统内存使用情况"
if command -v free &> /dev/null; then
    mem_total=$(free -g | awk 'NR==2 {print $2}')
    mem_available=$(free -g | awk 'NR==2 {print $7}')
    mem_used=$(free -g | awk 'NR==2 {print $3}')
    mem_percent=$(awk "BEGIN {printf \"%.0f\", ($mem_used/$mem_total)*100}")
    
    echo "   总内存: ${mem_total}GB"
    echo "   已使用: ${mem_used}GB (${mem_percent}%)"
    echo "   可用: ${mem_available}GB"
    
    results[mem_total_gb]="$mem_total"
    results[mem_available_gb]="$mem_available"
    results[mem_used_percent]="$mem_percent"
    
    if [ "$mem_available" -ge 2 ]; then
        check_pass "可用内存充足: ${mem_available}GB"
        results[mem_status]="pass"
    elif [ "$mem_available" -ge 1 ]; then
        check_warn "可用内存较低: ${mem_available}GB"
        results[mem_status]="warning"
    else
        check_fail "可用内存不足: ${mem_available}GB"
        results[mem_status]="fail"
    fi
else
    check_warn "无法检查内存 (free 命令不可用)"
    results[mem_status]="unknown"
fi

# 2.4 CPU 信息
echo ""
echo "2.4 CPU 信息"
if command -v nproc &> /dev/null; then
    cpu_cores=$(nproc)
    echo "   CPU 核心数: $cpu_cores"
    results[cpu_cores]="$cpu_cores"
    
    if [ "$cpu_cores" -ge 4 ]; then
        check_pass "CPU 核心数充足: $cpu_cores"
        results[cpu_status]="pass"
    elif [ "$cpu_cores" -ge 2 ]; then
        check_warn "CPU 核心数较少: $cpu_cores"
        results[cpu_status]="warning"
    else
        check_warn "CPU 核心数过少: $cpu_cores (可能影响性能)"
        results[cpu_status]="warning"
    fi
else
    check_warn "无法检查 CPU (nproc 命令不可用)"
    results[cpu_status]="unknown"
fi

# ==================== 3. 网络连接检查 ====================
print_section "3. 网络连接检查"

# 3.1 检查 DNS 解析
echo "3.1 DNS 解析检查"
if command -v nslookup &> /dev/null || command -v host &> /dev/null; then
    if nslookup oss-cn-beijing.aliyuncs.com &> /dev/null || host oss-cn-beijing.aliyuncs.com &> /dev/null; then
        check_pass "DNS 解析正常 (oss-cn-beijing.aliyuncs.com)"
        results[dns_status]="pass"
    else
        check_fail "DNS 解析失败 (oss-cn-beijing.aliyuncs.com)"
        results[dns_status]="fail"
    fi
else
    check_warn "无法检查 DNS (nslookup/host 命令不可用)"
    results[dns_status]="unknown"
fi

# 3.2 检查 OSS 连接
echo ""
echo "3.2 阿里云 OSS 连接检查"
if command -v curl &> /dev/null; then
    oss_response=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 10 https://oss-cn-beijing.aliyuncs.com 2>&1 || echo "error")
    
    if [[ "$oss_response" =~ ^[0-9]+$ ]] && [ "$oss_response" -ge 200 ] && [ "$oss_response" -lt 500 ]; then
        check_pass "OSS 连接正常 (HTTP $oss_response)"
        results[oss_status]="pass"
        results[oss_http_code]="$oss_response"
    else
        check_fail "OSS 连接失败 (响应: $oss_response)"
        results[oss_status]="fail"
        results[oss_http_code]="$oss_response"
    fi
else
    check_warn "无法检查 OSS 连接 (curl 命令不可用)"
    results[oss_status]="unknown"
fi

# 3.3 检查 DashScope API 连接
echo ""
echo "3.3 DashScope API 连接检查"
if command -v curl &> /dev/null; then
    dashscope_response=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 10 https://dashscope.aliyuncs.com 2>&1 || echo "error")
    
    if [[ "$dashscope_response" =~ ^[0-9]+$ ]] && [ "$dashscope_response" -ge 200 ] && [ "$dashscope_response" -lt 500 ]; then
        check_pass "DashScope 连接正常 (HTTP $dashscope_response)"
        results[dashscope_status]="pass"
        results[dashscope_http_code]="$dashscope_response"
    else
        check_fail "DashScope 连接失败 (响应: $dashscope_response)"
        results[dashscope_status]="fail"
        results[dashscope_http_code]="$dashscope_response"
    fi
else
    check_warn "无法检查 DashScope 连接 (curl 命令不可用)"
    results[dashscope_status]="unknown"
fi

# 3.4 检查代理配置
echo ""
echo "3.4 检查网络代理配置"
if [ -n "$http_proxy" ]; then
    echo "   http_proxy: $http_proxy"
    results[http_proxy]="$http_proxy"
    check_warn "检测到 HTTP 代理设置"
else
    echo "   http_proxy: 未设置"
    results[http_proxy]="none"
fi

if [ -n "$https_proxy" ]; then
    echo "   https_proxy: $https_proxy"
    results[https_proxy]="$https_proxy"
    check_warn "检测到 HTTPS 代理设置"
else
    echo "   https_proxy: 未设置"
    results[https_proxy]="none"
fi

if [ -n "$all_proxy" ]; then
    echo "   all_proxy: $all_proxy"
    results[all_proxy]="$all_proxy"
    check_warn "检测到全局代理设置"
else
    echo "   all_proxy: 未设置"
    results[all_proxy]="none"
fi

# ==================== 4. Python 环境检查 ====================
print_section "4. Python 环境检查"

# 4.1 Python 版本
echo "4.1 Python 版本检查"
if command -v python3 &> /dev/null; then
    python_version=$(python3 --version 2>&1 | awk '{print $2}')
    echo "   Python 版本: $python_version"
    results[python_version]="$python_version"
    
    # 检查是否 >= 3.9
    major_version=$(echo "$python_version" | cut -d. -f1)
    minor_version=$(echo "$python_version" | cut -d. -f2)
    
    if [ "$major_version" -eq 3 ] && [ "$minor_version" -ge 9 ]; then
        check_pass "Python 版本满足要求 (>= 3.9)"
        results[python_version_status]="pass"
    else
        check_warn "Python 版本较低: $python_version (建议 >= 3.9)"
        results[python_version_status]="warning"
    fi
else
    check_fail "Python3 未安装"
    results[python_version_status]="fail"
fi

# 4.2 关键依赖包检查
echo ""
echo "4.2 关键依赖包检查"
check_python_package() {
    local package=$1
    if python3 -c "import $package" &> /dev/null; then
        local version=$(python3 -c "import $package; print($package.__version__)" 2>/dev/null || echo "unknown")
        check_pass "$package 已安装 (版本: $version)"
        results["pkg_${package}"]="installed:$version"
    else
        check_fail "$package 未安装"
        results["pkg_${package}"]="not_installed"
    fi
}

check_python_package "fastapi"
check_python_package "uvicorn"
check_python_package "oss2"
check_python_package "dashscope"
check_python_package "supabase"
check_python_package "psutil"

# ==================== 5. 配置文件检查 ====================
print_section "5. 配置文件检查"

# 5.1 .env 文件
echo "5.1 环境变量文件检查"
ENV_FILE="$PROJECT_ROOT/.env"
if [ -f "$ENV_FILE" ]; then
    check_pass ".env 文件存在"
    results[env_file_exists]="pass"
    
    # 检查关键配置项
    check_env_var() {
        local var_name=$1
        if grep -q "^${var_name}=" "$ENV_FILE" 2>/dev/null; then
            check_pass "$var_name 已配置"
            results["env_${var_name}"]="configured"
        else
            check_fail "$var_name 未配置"
            results["env_${var_name}"]="not_configured"
        fi
    }
    
    check_env_var "OSS_ACCESS_KEY_ID"
    check_env_var "OSS_ACCESS_KEY_SECRET"
    check_env_var "OSS_BUCKET"
    check_env_var "OSS_ENDPOINT"
    check_env_var "QWEN_API_KEY"
    check_env_var "SUPABASE_URL"
    check_env_var "SUPABASE_ANON_KEY"
else
    check_fail ".env 文件不存在: $ENV_FILE"
    results[env_file_exists]="fail"
fi

# ==================== 6. FastAPI 服务检查 ====================
print_section "6. FastAPI 服务检查"

# 6.1 检查服务是否运行
echo "6.1 检查 FastAPI 服务状态"
if command -v curl &> /dev/null; then
    api_response=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 --max-time 5 http://localhost:8000/docs 2>&1 || echo "error")
    
    if [[ "$api_response" =~ ^[0-9]+$ ]] && [ "$api_response" -eq 200 ]; then
        check_pass "FastAPI 服务正在运行 (http://localhost:8000)"
        results[fastapi_status]="running"
        
        # 检查视频处理端点
        video_status=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 --max-time 5 http://localhost:8000/video/status 2>&1 || echo "error")
        if [[ "$video_status" =~ ^[0-9]+$ ]] && [ "$video_status" -eq 200 ]; then
            check_pass "视频处理端点可访问"
            results[video_endpoint_status]="accessible"
        else
            check_warn "视频处理端点不可访问 (HTTP $video_status)"
            results[video_endpoint_status]="not_accessible"
        fi
    else
        check_warn "FastAPI 服务未运行或不可访问"
        results[fastapi_status]="not_running"
    fi
else
    check_warn "无法检查服务状态 (curl 命令不可用)"
    results[fastapi_status]="unknown"
fi

# ==================== 7. 生成检查报告 ====================
print_section "7. 检查总结"

# 统计结果
total_checks=0
passed_checks=0
failed_checks=0
warning_checks=0

for key in "${!results[@]}"; do
    if [[ "$key" == *"_status" ]]; then
        total_checks=$((total_checks + 1))
        case "${results[$key]}" in
            "pass")
                passed_checks=$((passed_checks + 1))
                ;;
            "fail")
                failed_checks=$((failed_checks + 1))
                ;;
            "warning")
                warning_checks=$((warning_checks + 1))
                ;;
        esac
    fi
done

echo "检查项总数: $total_checks"
echo -e "通过: ${GREEN}$passed_checks${NC}"
echo -e "警告: ${YELLOW}$warning_checks${NC}"
echo -e "失败: ${RED}$failed_checks${NC}"
echo ""

# 给出建议
if [ "$failed_checks" -gt 0 ]; then
    echo -e "${RED}❌ 发现 $failed_checks 个严重问题，需要立即修复${NC}"
    echo ""
    echo "建议操作:"
    echo "1. 检查磁盘空间和权限"
    echo "2. 确认网络连接正常"
    echo "3. 验证配置文件完整性"
    echo "4. 检查 Python 依赖是否安装"
elif [ "$warning_checks" -gt 0 ]; then
    echo -e "${YELLOW}⚠️ 发现 $warning_checks 个警告，建议优化${NC}"
    echo ""
    echo "建议操作:"
    echo "1. 增加系统资源限制 (ulimit)"
    echo "2. 清理临时文件"
    echo "3. 检查代理设置是否必要"
else
    echo -e "${GREEN}✅ 所有检查项通过，环境配置正常${NC}"
fi

# ==================== JSON 输出 ====================
if [ "$OUTPUT_JSON" = true ]; then
    echo ""
    echo "{"
    echo "  \"timestamp\": \"$(date -Iseconds)\","
    echo "  \"total_checks\": $total_checks,"
    echo "  \"passed\": $passed_checks,"
    echo "  \"warnings\": $warning_checks,"
    echo "  \"failed\": $failed_checks,"
    echo "  \"results\": {"
    
    first=true
    for key in "${!results[@]}"; do
        if [ "$first" = true ]; then
            first=false
        else
            echo ","
        fi
        echo -n "    \"$key\": \"${results[$key]}\""
    done
    
    echo ""
    echo "  }"
    echo "}"
fi

# ==================== 保存到日志文件 ====================
if [ -n "$LOG_FILE" ]; then
    {
        echo "========================================="
        echo "视频上传环境检查报告"
        echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
        echo "========================================="
        echo ""
        for key in "${!results[@]}"; do
            echo "$key: ${results[$key]}"
        done
    } > "$LOG_FILE"
    
    echo ""
    echo "检查结果已保存到: $LOG_FILE"
fi

echo ""
echo -e "${CYAN}=========================================${NC}"
echo -e "${CYAN}检查完成: $(date '+%Y-%m-%d %H:%M:%S')${NC}"
echo -e "${CYAN}=========================================${NC}"

# 退出码: 0=成功, 1=有失败项
exit $failed_checks
