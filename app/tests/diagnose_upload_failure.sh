#!/bin/bash

#################################################################################
# 视频上传故障综合诊断工具
# 
# 功能: 综合诊断视频上传失败问题，提供完整的故障定位方案
# 
# 使用方法:
#   bash app/tests/diagnose_upload_failure.sh [选项]
# 
# 选项:
#   --quick             快速诊断模式(跳过耗时测试)
#   --full              完整诊断模式(默认)
#   --api-url URL       API地址 (默认: http://localhost:8000)
#   --report FILE       生成诊断报告文件
#   --verbose           显示详细输出
#   --help              显示帮助信息
# 
# 示例:
#   bash app/tests/diagnose_upload_failure.sh
#   bash app/tests/diagnose_upload_failure.sh --quick
#   bash app/tests/diagnose_upload_failure.sh --report diagnosis_report.txt
#################################################################################

# ==================== 配置参数 ====================
MODE="full"
API_URL="http://localhost:8000"
REPORT_FILE=""
VERBOSE=false
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# ==================== Conda 环境检测与激活 ====================
# 检测是否在 conda 环境中，如果不在项目环境则尝试激活
if command -v conda &> /dev/null; then
    CONDA_ENV_NAME="yt_summarizer"
    CURRENT_ENV="${CONDA_DEFAULT_ENV:-base}"
    
    # 如果不在项目环境中，尝试激活
    if [ "$CURRENT_ENV" != "$CONDA_ENV_NAME" ]; then
        # 尝试查找 conda.sh 并初始化
        CONDA_BASE=$(conda info --base 2>/dev/null)
        if [ -f "$CONDA_BASE/etc/profile.d/conda.sh" ]; then
            source "$CONDA_BASE/etc/profile.d/conda.sh"
            if conda env list | grep -q "^$CONDA_ENV_NAME "; then
                conda activate $CONDA_ENV_NAME 2>/dev/null || true
            fi
        fi
    fi
fi

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
print_banner() {
    echo -e "${CYAN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║                                                               ║${NC}"
    echo -e "${CYAN}║         ${BOLD}视频上传故障综合诊断工具 v1.0${NC}${CYAN}                  ║${NC}"
    echo -e "${CYAN}║                                                               ║${NC}"
    echo -e "${CYAN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "开始时间: ${CYAN}$(date '+%Y-%m-%d %H:%M:%S')${NC}"
    echo -e "诊断模式: ${YELLOW}$MODE${NC}"
    echo -e "API地址:  ${YELLOW}$API_URL${NC}"
    echo ""
}

print_step() {
    echo ""
    echo -e "${BLUE}${BOLD}=== 步骤 $1: $2 ===${NC}"
    echo ""
}

print_substep() {
    echo -e "${CYAN}--- $1 ---${NC}"
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

print_info() {
    echo -e "${CYAN}ℹ${NC}  $1"
}

# ==================== 参数解析 ====================
while [[ $# -gt 0 ]]; do
    case $1 in
        --quick)
            MODE="quick"
            shift
            ;;
        --full)
            MODE="full"
            shift
            ;;
        --api-url)
            API_URL="$2"
            shift 2
            ;;
        --report)
            REPORT_FILE="$2"
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

# ==================== 诊断结果收集 ====================
declare -A diagnosis_results
diagnosis_results[total_checks]=0
diagnosis_results[passed]=0
diagnosis_results[warnings]=0
diagnosis_results[failures]=0

# ==================== 开始诊断 ====================
print_banner

# ==================== 步骤 1: 环境检查 ====================
print_step "1" "服务器环境检查"

# 检查磁盘空间
print_substep "1.1 检查磁盘空间"
tmp_space=$(df -BG /tmp 2>/dev/null | awk 'NR==2 {print $4}' | sed 's/G//' || echo "0")
((diagnosis_results[total_checks]++))

if [ "$tmp_space" -gt 10 ]; then
    check_pass "/tmp 可用空间: ${tmp_space}GB"
    ((diagnosis_results[passed]++))
elif [ "$tmp_space" -gt 5 ]; then
    check_warn "/tmp 可用空间: ${tmp_space}GB (建议清理)"
    ((diagnosis_results[warnings]++))
else
    check_fail "/tmp 可用空间不足: ${tmp_space}GB"
    ((diagnosis_results[failures]++))
fi

# 检查文件权限
print_substep "1.2 检查文件权限"
((diagnosis_results[total_checks]++))

if [ -w "/tmp" ]; then
    check_pass "/tmp 目录可写"
    ((diagnosis_results[passed]++))
else
    check_fail "/tmp 目录不可写"
    ((diagnosis_results[failures]++))
fi

# 检查系统资源
print_substep "1.3 检查系统资源"
((diagnosis_results[total_checks]++))

if command -v free &> /dev/null; then
    mem_available=$(free -g | awk 'NR==2 {print $7}')
    if [ "$mem_available" -ge 2 ]; then
        check_pass "可用内存: ${mem_available}GB"
        ((diagnosis_results[passed]++))
    else
        check_warn "可用内存较低: ${mem_available}GB"
        ((diagnosis_results[warnings]++))
    fi
else
    check_warn "无法检查内存使用情况"
    ((diagnosis_results[warnings]++))
fi

# ==================== 步骤 2: 网络连通性检查 ====================
print_step "2" "网络连通性检查"

# 检查 OSS 连接
print_substep "2.1 检查阿里云 OSS 连接"
((diagnosis_results[total_checks]++))

if command -v curl &> /dev/null; then
    oss_response=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 10 https://oss-cn-beijing.aliyuncs.com 2>&1 || echo "error")
    
    if [[ "$oss_response" =~ ^[0-9]+$ ]] && [ "$oss_response" -ge 200 ] && [ "$oss_response" -lt 500 ]; then
        check_pass "OSS 连接正常 (HTTP $oss_response)"
        ((diagnosis_results[passed]++))
    else
        check_fail "OSS 连接失败"
        ((diagnosis_results[failures]++))
    fi
else
    check_warn "curl 不可用，跳过网络检查"
    ((diagnosis_results[warnings]++))
fi

# 检查 DashScope 连接
print_substep "2.2 检查 DashScope API 连接"
((diagnosis_results[total_checks]++))

if command -v curl &> /dev/null; then
    ds_response=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 10 https://dashscope.aliyuncs.com 2>&1 || echo "error")
    
    if [[ "$ds_response" =~ ^[0-9]+$ ]] && [ "$ds_response" -ge 200 ] && [ "$ds_response" -lt 500 ]; then
        check_pass "DashScope 连接正常 (HTTP $ds_response)"
        ((diagnosis_results[passed]++))
    else
        check_fail "DashScope 连接失败"
        ((diagnosis_results[failures]++))
    fi
else
    ((diagnosis_results[warnings]++))
fi

# 检查代理设置
print_substep "2.3 检查代理配置"
if [ -n "$http_proxy" ] || [ -n "$https_proxy" ] || [ -n "$all_proxy" ]; then
    check_warn "检测到代理设置 (可能影响连接)"
    [ -n "$http_proxy" ] && echo "  http_proxy: $http_proxy"
    [ -n "$https_proxy" ] && echo "  https_proxy: $https_proxy"
    [ -n "$all_proxy" ] && echo "  all_proxy: $all_proxy"
else
    check_pass "未使用代理"
fi

# ==================== 步骤 3: Python 环境检查 ====================
print_step "3" "Python 环境检查"

print_substep "3.1 检查 Python 版本"
((diagnosis_results[total_checks]++))

if command -v python3 &> /dev/null; then
    python_version=$(python3 --version | awk '{print $2}')
    major=$(echo "$python_version" | cut -d. -f1)
    minor=$(echo "$python_version" | cut -d. -f2)
    
    if [ "$major" -eq 3 ] && [ "$minor" -ge 9 ]; then
        check_pass "Python $python_version"
        ((diagnosis_results[passed]++))
    else
        check_warn "Python 版本较低: $python_version"
        ((diagnosis_results[warnings]++))
    fi
else
    check_fail "Python3 未安装"
    ((diagnosis_results[failures]++))
fi

print_substep "3.2 检查关键依赖"
required_packages=("fastapi" "uvicorn" "oss2" "dashscope" "psutil")

for pkg in "${required_packages[@]}"; do
    ((diagnosis_results[total_checks]++))
    if python3 -c "import $pkg" &> /dev/null; then
        check_pass "$pkg 已安装"
        ((diagnosis_results[passed]++))
    else
        check_fail "$pkg 未安装"
        ((diagnosis_results[failures]++))
    fi
done

# ==================== 步骤 4: 配置文件检查 ====================
print_step "4" "配置文件检查"

print_substep "4.1 检查 .env 文件"
((diagnosis_results[total_checks]++))

ENV_FILE="$PROJECT_ROOT/.env"
if [ -f "$ENV_FILE" ]; then
    check_pass ".env 文件存在"
    ((diagnosis_results[passed]++))
    
    # 检查关键配置项
    required_vars=("OSS_ACCESS_KEY_ID" "OSS_BUCKET" "QWEN_API_KEY" "SUPABASE_URL")
    for var in "${required_vars[@]}"; do
        ((diagnosis_results[total_checks]++))
        if grep -q "^${var}=" "$ENV_FILE" 2>/dev/null; then
            check_pass "$var 已配置"
            ((diagnosis_results[passed]++))
        else
            check_fail "$var 未配置"
            ((diagnosis_results[failures]++))
        fi
    done
else
    check_fail ".env 文件不存在"
    ((diagnosis_results[failures]++))
fi

# ==================== 步骤 5: API 服务检查 ====================
print_step "5" "FastAPI 服务检查"

print_substep "5.1 检查服务状态"
((diagnosis_results[total_checks]++))

if command -v curl &> /dev/null; then
    api_response=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 --max-time 5 "${API_URL}/docs" 2>&1 || echo "000")
    
    if [ "$api_response" = "200" ]; then
        check_pass "FastAPI 服务运行中"
        ((diagnosis_results[passed]++))
        
        # 检查视频端点
        print_substep "5.2 检查视频处理端点"
        ((diagnosis_results[total_checks]++))
        
        video_response=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 --max-time 5 "${API_URL}/video/status" 2>&1 || echo "000")
        
        if [ "$video_response" = "200" ]; then
            check_pass "视频处理端点可访问"
            ((diagnosis_results[passed]++))
        else
            check_warn "视频处理端点不可访问 (HTTP $video_response)"
            ((diagnosis_results[warnings]++))
        fi
    else
        check_fail "FastAPI 服务未运行 (HTTP $api_response)"
        ((diagnosis_results[failures]++))
        echo ""
        print_info "请启动 FastAPI 服务:"
        echo "  cd backend && uvicorn app.main:app --reload"
    fi
else
    check_warn "无法检查服务状态"
    ((diagnosis_results[warnings]++))
fi

# ==================== 步骤 6: 实际上传测试 (仅 full 模式) ====================
if [ "$MODE" = "full" ]; then
    print_step "6" "实际上传测试"
    
    print_substep "6.1 生成测试视频"
    TEST_FILE="/tmp/diagnostic_test_video.mp4"
    
    if command -v ffmpeg &> /dev/null; then
        echo "生成小型测试视频..."
        ffmpeg -f lavfi -i "color=c=blue:s=640x480:d=5" \
            -vf "drawtext=text='Diagnostic Test':fontsize=30:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2" \
            -c:v libx264 -preset ultrafast -pix_fmt yuv420p -y "$TEST_FILE" &>/dev/null
        
        if [ -f "$TEST_FILE" ]; then
            file_size=$(stat -f%z "$TEST_FILE" 2>/dev/null || stat -c%s "$TEST_FILE")
            file_size_mb=$(awk "BEGIN {printf \"%.2f\", $file_size/1024/1024}")
            check_pass "测试视频已生成 (${file_size_mb}MB)"
            
            print_substep "6.2 执行上传测试"
            ((diagnosis_results[total_checks]++))
            
            response_file="/tmp/diagnostic_response.json"
            http_code=$(curl -X POST "${API_URL}/video/process" \
                -F "video_file=@$TEST_FILE" \
                -w "%{http_code}" \
                -o "$response_file" \
                -s 2>&1 || echo "000")
            
            if [ "$http_code" = "200" ]; then
                check_pass "上传测试成功 (HTTP $http_code)"
                ((diagnosis_results[passed]++))
                
                if command -v jq &> /dev/null && [ -f "$response_file" ]; then
                    status=$(cat "$response_file" | jq -r '.status' 2>/dev/null || echo "unknown")
                    echo "  API 状态: $status"
                fi
            else
                check_fail "上传测试失败 (HTTP $http_code)"
                ((diagnosis_results[failures]++))
                
                if [ -f "$response_file" ]; then
                    echo ""
                    echo "错误详情:"
                    if command -v jq &> /dev/null; then
                        cat "$response_file" | jq '.' 2>/dev/null || cat "$response_file"
                    else
                        cat "$response_file"
                    fi
                fi
            fi
            
            # 清理测试文件
            rm -f "$TEST_FILE" "$response_file"
        else
            check_fail "测试视频生成失败"
            ((diagnosis_results[failures]++))
        fi
    else
        check_warn "ffmpeg 不可用，跳过上传测试"
        ((diagnosis_results[warnings]++))
    fi
fi

# ==================== 生成诊断报告 ====================
print_step "✓" "诊断总结"

total=${diagnosis_results[total_checks]}
passed=${diagnosis_results[passed]}
warnings=${diagnosis_results[warnings]}
failures=${diagnosis_results[failures]}

echo ""
echo -e "${BOLD}检查统计:${NC}"
echo -e "  总检查项: $total"
echo -e "  ${GREEN}通过: $passed${NC}"
echo -e "  ${YELLOW}警告: $warnings${NC}"
echo -e "  ${RED}失败: $failures${NC}"
echo ""

# 计算健康度得分
if [ "$total" -gt 0 ]; then
    health_score=$(awk "BEGIN {printf \"%.0f\", ($passed/$total)*100}")
    
    echo -e "${BOLD}系统健康度: ${health_score}%${NC}"
    
    if [ "$health_score" -ge 90 ]; then
        echo -e "${GREEN}系统状态: 优秀${NC}"
    elif [ "$health_score" -ge 70 ]; then
        echo -e "${YELLOW}系统状态: 良好${NC}"
    elif [ "$health_score" -ge 50 ]; then
        echo -e "${YELLOW}系统状态: 一般 (需要优化)${NC}"
    else
        echo -e "${RED}系统状态: 差 (需要立即修复)${NC}"
    fi
fi

# 给出建议
echo ""
echo -e "${BOLD}诊断建议:${NC}"

if [ "$failures" -gt 0 ]; then
    echo -e "${RED}⚠ 发现严重问题，建议:${NC}"
    echo "  1. 检查磁盘空间和文件权限"
    echo "  2. 验证网络连接和 API 密钥"
    echo "  3. 确认 Python 依赖完整安装"
    echo "  4. 检查 FastAPI 服务是否正常运行"
elif [ "$warnings" -gt 0 ]; then
    echo -e "${YELLOW}ℹ 存在一些警告，建议:${NC}"
    echo "  1. 清理临时文件释放空间"
    echo "  2. 检查代理配置是否必要"
    echo "  3. 考虑升级 Python 版本"
else
    echo -e "${GREEN}✓ 系统配置正常，上传功能应正常工作${NC}"
fi

# 保存报告
if [ -n "$REPORT_FILE" ]; then
    {
        echo "======================================"
        echo "视频上传诊断报告"
        echo "======================================"
        echo ""
        echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
        echo "模式: $MODE"
        echo "API: $API_URL"
        echo ""
        echo "检查统计:"
        echo "  总检查项: $total"
        echo "  通过: $passed"
        echo "  警告: $warnings"
        echo "  失败: $failures"
        echo "  健康度: ${health_score}%"
        echo ""
        echo "详细结果:"
        for key in "${!diagnosis_results[@]}"; do
            echo "  $key: ${diagnosis_results[$key]}"
        done
    } > "$REPORT_FILE"
    
    echo ""
    echo -e "诊断报告已保存: ${CYAN}$REPORT_FILE${NC}"
fi

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}诊断完成: $(date '+%Y-%m-%d %H:%M:%S')${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"

# 返回失败数量
exit $failures