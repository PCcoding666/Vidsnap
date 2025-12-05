#!/bin/bash

#################################################################################
# 视频上传诊断测试脚本
# 
# 功能: 测试不同场景下的视频上传功能，帮助诊断上传失败问题
# 
# 使用方法:
#   bash app/tests/test_upload_diagnostics.sh [测试类型] [选项]
# 
# 测试类型:
#   small       测试小文件上传 (<10MB)
#   medium      测试中等文件上传 (10-100MB)
#   large       测试大文件上传 (>100MB)
#   concurrent  测试并发上传
#   all         运行所有测试 (默认)
# 
# 选项:
#   --api-url URL       API地址 (默认: http://localhost:8000)
#   --output-dir DIR    输出目录 (默认: /tmp/upload_test_results)
#   --keep-files        保留测试文件
#   --verbose           显示详细输出
#   --help              显示帮助信息
# 
# 示例:
#   bash app/tests/test_upload_diagnostics.sh small
#   bash app/tests/test_upload_diagnostics.sh medium --api-url http://server:8000
#   bash app/tests/test_upload_diagnostics.sh concurrent --verbose
#################################################################################

set -e

# ==================== 配置参数 ====================
TEST_TYPE="${1:-all}"
API_URL="http://localhost:8000"
OUTPUT_DIR="/tmp/upload_test_results"
KEEP_FILES=false
VERBOSE=false

# ==================== 颜色定义 ====================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ==================== 辅助函数 ====================
print_header() {
    echo -e "${CYAN}=========================================${NC}"
    echo -e "${CYAN}$1${NC}"
    echo -e "${CYAN}=========================================${NC}"
}

print_section() {
    echo ""
    echo -e "${BLUE}>>> $1${NC}"
}

test_pass() {
    echo -e "${GREEN}[✓ PASS]${NC} $1"
}

test_fail() {
    echo -e "${RED}[✗ FAIL]${NC} $1"
}

test_warn() {
    echo -e "${YELLOW}[! WARN]${NC} $1"
}

# ==================== 参数解析 ====================
shift || true  # 跳过第一个参数(测试类型)
while [[ $# -gt 0 ]]; do
    case $1 in
        --api-url)
            API_URL="$2"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --keep-files)
            KEEP_FILES=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --help)
            head -n 30 "$0" | grep "^#" | sed 's/^# //g' | sed 's/^#//g'
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
mkdir -p "$OUTPUT_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$OUTPUT_DIR/test_${TIMESTAMP}.log"

print_header "视频上传诊断测试工具"
echo "测试类型: $TEST_TYPE"
echo "API 地址: $API_URL"
echo "输出目录: $OUTPUT_DIR"
echo "日志文件: $LOG_FILE"
echo "开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 检查必要的命令
if ! command -v ffmpeg &> /dev/null; then
    echo -e "${RED}错误: 未找到 ffmpeg 命令，请先安装 ffmpeg${NC}"
    exit 1
fi

if ! command -v curl &> /dev/null; then
    echo -e "${RED}错误: 未找到 curl 命令，请先安装 curl${NC}"
    exit 1
fi

# ==================== 生成测试视频 ====================
generate_test_video() {
    local duration=$1
    local output_file=$2
    local size_label=$3
    
    print_section "生成测试视频: $size_label"
    
    if [ -f "$output_file" ]; then
        echo "测试文件已存在，跳过生成: $output_file"
        return 0
    fi
    
    echo "生成 ${duration}秒 视频..."
    if [ "$VERBOSE" = true ]; then
        ffmpeg -f lavfi -i "color=c=blue:s=1280x720:d=$duration" \
            -vf "drawtext=text='Test Video ${size_label} %{pts\:hms}':fontsize=40:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2" \
            -c:v libx264 -preset fast -pix_fmt yuv420p -y "$output_file" 2>&1 | tee -a "$LOG_FILE"
    else
        ffmpeg -f lavfi -i "color=c=blue:s=1280x720:d=$duration" \
            -vf "drawtext=text='Test Video ${size_label} %{pts\:hms}':fontsize=40:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2" \
            -c:v libx264 -preset fast -pix_fmt yuv420p -y "$output_file" &>> "$LOG_FILE"
    fi
    
    if [ -f "$output_file" ]; then
        local file_size=$(stat -f%z "$output_file" 2>/dev/null || stat -c%s "$output_file")
        local file_size_mb=$(awk "BEGIN {printf \"%.2f\", $file_size/1024/1024}")
        echo -e "${GREEN}✓${NC} 视频生成成功: $output_file (${file_size_mb}MB)"
        echo "$file_size"
    else
        echo -e "${RED}✗${NC} 视频生成失败"
        return 1
    fi
}

# ==================== 执行上传测试 ====================
test_upload() {
    local test_name=$1
    local test_file=$2
    local expected_result=$3  # "success" or "fail"
    
    print_section "测试: $test_name"
    
    # 获取文件信息
    local file_size=$(stat -f%z "$test_file" 2>/dev/null || stat -c%s "$test_file")
    local file_size_mb=$(awk "BEGIN {printf \"%.2f\", $file_size/1024/1024}")
    local file_name=$(basename "$test_file")
    
    echo "测试文件: $file_name"
    echo "文件大小: ${file_size_mb}MB"
    echo ""
    
    # 执行上传
    local start_time=$(date +%s.%N)
    local response_file="$OUTPUT_DIR/response_${TIMESTAMP}_$(echo $test_name | tr ' ' '_').json"
    local curl_output="$OUTPUT_DIR/curl_${TIMESTAMP}_$(echo $test_name | tr ' ' '_').log"
    
    echo "开始上传..."
    
    local http_code=$(curl -X POST "${API_URL}/video/process" \
        -F "video_file=@$test_file" \
        -H "Content-Type: multipart/form-data" \
        -H "X-Test-ID: test-${TIMESTAMP}" \
        -w "%{http_code}" \
        -o "$response_file" \
        -v 2>"$curl_output" || echo "000")
    
    local end_time=$(date +%s.%N)
    local duration=$(awk "BEGIN {printf \"%.2f\", $end_time - $start_time}")
    
    # 分析结果
    echo ""
    echo "========== 上传结果 =========="
    echo "HTTP 状态码: $http_code"
    echo "上传耗时: ${duration}秒"
    
    if [ "$file_size" -gt 0 ]; then
        local speed=$(awk "BEGIN {printf \"%.2f\", $file_size/$duration/1024/1024}")
        echo "上传速度: ${speed}MB/s"
    fi
    
    # 显示响应内容
    if [ -f "$response_file" ]; then
        echo ""
        echo "========== API 响应 =========="
        if command -v jq &> /dev/null; then
            cat "$response_file" | jq '.' 2>/dev/null || cat "$response_file"
        else
            cat "$response_file"
        fi
    fi
    
    # 判断测试结果
    echo ""
    if [ "$http_code" = "200" ]; then
        # 检查响应中的 status 字段
        if command -v jq &> /dev/null && [ -f "$response_file" ]; then
            local status=$(cat "$response_file" | jq -r '.status' 2>/dev/null || echo "unknown")
            if [ "$status" = "success" ]; then
                test_pass "$test_name - 上传成功"
                return 0
            else
                test_fail "$test_name - API返回失败状态: $status"
                return 1
            fi
        else
            test_pass "$test_name - HTTP 200 响应"
            return 0
        fi
    elif [ "$http_code" = "000" ]; then
        test_fail "$test_name - 网络连接失败"
        return 1
    else
        test_fail "$test_name - HTTP 错误: $http_code"
        
        # 显示详细错误信息
        if [ -f "$response_file" ]; then
            echo ""
            echo "错误详情:"
            if command -v jq &> /dev/null; then
                cat "$response_file" | jq -r '.detail // .message // .' 2>/dev/null || cat "$response_file"
            else
                cat "$response_file"
            fi
        fi
        
        return 1
    fi
}

# ==================== 测试用例 ====================

# 测试 1: 小文件上传
test_small_file() {
    print_header "测试 1: 小文件上传 (<10MB)"
    
    local test_file="$OUTPUT_DIR/test_small.mp4"
    generate_test_video 10 "$test_file" "Small"
    
    if [ -f "$test_file" ]; then
        test_upload "小文件上传" "$test_file" "success"
    else
        test_fail "小文件测试 - 视频生成失败"
    fi
}

# 测试 2: 中等文件上传
test_medium_file() {
    print_header "测试 2: 中等文件上传 (10-100MB)"
    
    local test_file="$OUTPUT_DIR/test_medium.mp4"
    generate_test_video 60 "$test_file" "Medium"
    
    if [ -f "$test_file" ]; then
        test_upload "中等文件上传" "$test_file" "success"
    else
        test_fail "中等文件测试 - 视频生成失败"
    fi
}

# 测试 3: 大文件上传
test_large_file() {
    print_header "测试 3: 大文件上传 (>100MB)"
    
    local test_file="$OUTPUT_DIR/test_large.mp4"
    generate_test_video 180 "$test_file" "Large"
    
    if [ -f "$test_file" ]; then
        test_upload "大文件上传" "$test_file" "success"
    else
        test_fail "大文件测试 - 视频生成失败"
    fi
}

# 测试 4: 并发上传
test_concurrent_upload() {
    print_header "测试 4: 并发上传测试"
    
    local concurrent_count=3
    local test_file="$OUTPUT_DIR/test_concurrent.mp4"
    
    generate_test_video 10 "$test_file" "Concurrent"
    
    if [ ! -f "$test_file" ]; then
        test_fail "并发测试 - 视频生成失败"
        return 1
    fi
    
    echo "启动 $concurrent_count 个并发上传..."
    local pids=()
    
    for i in $(seq 1 $concurrent_count); do
        (
            local response_file="$OUTPUT_DIR/response_concurrent_${i}_${TIMESTAMP}.json"
            curl -X POST "${API_URL}/video/process" \
                -F "video_file=@$test_file" \
                -H "X-Test-ID: concurrent-${i}-${TIMESTAMP}" \
                -w "\nHTTP:%{http_code}\n" \
                -o "$response_file" \
                -s > "$OUTPUT_DIR/concurrent_${i}_${TIMESTAMP}.log" 2>&1
            echo $? > "$OUTPUT_DIR/concurrent_${i}_${TIMESTAMP}.exit"
        ) &
        pids+=($!)
        echo "  启动上传 #$i (PID: ${pids[-1]})"
    done
    
    echo ""
    echo "等待所有上传完成..."
    
    local success_count=0
    local fail_count=0
    
    for i in $(seq 1 $concurrent_count); do
        wait ${pids[$i-1]} || true
        
        local exit_code=$(cat "$OUTPUT_DIR/concurrent_${i}_${TIMESTAMP}.exit" 2>/dev/null || echo "1")
        local log_file="$OUTPUT_DIR/concurrent_${i}_${TIMESTAMP}.log"
        
        if [ -f "$log_file" ]; then
            local http_code=$(grep "^HTTP:" "$log_file" | cut -d: -f2 || echo "000")
            
            if [ "$http_code" = "200" ]; then
                echo -e "  上传 #$i: ${GREEN}成功${NC} (HTTP $http_code)"
                ((success_count++))
            else
                echo -e "  上传 #$i: ${RED}失败${NC} (HTTP $http_code)"
                ((fail_count++))
            fi
        else
            echo -e "  上传 #$i: ${RED}失败${NC} (无日志)"
            ((fail_count++))
        fi
    done
    
    echo ""
    echo "========== 并发测试结果 =========="
    echo "成功: $success_count / $concurrent_count"
    echo "失败: $fail_count / $concurrent_count"
    
    if [ "$success_count" -eq "$concurrent_count" ]; then
        test_pass "并发上传测试 - 全部成功"
        return 0
    elif [ "$success_count" -gt 0 ]; then
        test_warn "并发上传测试 - 部分成功 ($success_count/$concurrent_count)"
        return 1
    else
        test_fail "并发上传测试 - 全部失败"
        return 1
    fi
}

# ==================== 执行测试 ====================
execute_tests() {
    local total_tests=0
    local passed_tests=0
    local failed_tests=0
    
    case $TEST_TYPE in
        "small")
            total_tests=1
            test_small_file && ((passed_tests++)) || ((failed_tests++))
            ;;
        "medium")
            total_tests=1
            test_medium_file && ((passed_tests++)) || ((failed_tests++))
            ;;
        "large")
            total_tests=1
            test_large_file && ((passed_tests++)) || ((failed_tests++))
            ;;
        "concurrent")
            total_tests=1
            test_concurrent_upload && ((passed_tests++)) || ((failed_tests++))
            ;;
        "all")
            total_tests=4
            test_small_file && ((passed_tests++)) || ((failed_tests++))
            test_medium_file && ((passed_tests++)) || ((failed_tests++))
            test_large_file && ((passed_tests++)) || ((failed_tests++))
            test_concurrent_upload && ((passed_tests++)) || ((failed_tests++))
            ;;
        *)
            echo -e "${RED}错误: 未知的测试类型 '$TEST_TYPE'${NC}"
            echo "支持的测试类型: small, medium, large, concurrent, all"
            exit 1
            ;;
    esac
    
    # 输出总结
    print_header "测试总结"
    echo "总测试数: $total_tests"
    echo -e "通过: ${GREEN}$passed_tests${NC}"
    echo -e "失败: ${RED}$failed_tests${NC}"
    echo ""
    echo "详细日志: $LOG_FILE"
    echo "输出目录: $OUTPUT_DIR"
    
    # 清理测试文件
    if [ "$KEEP_FILES" = false ]; then
        echo ""
        echo "清理测试文件..."
        rm -f "$OUTPUT_DIR"/test_*.mp4
        echo "✓ 测试文件已清理"
    else
        echo ""
        echo "测试文件已保留在: $OUTPUT_DIR"
    fi
    
    echo ""
    echo "测试完成: $(date '+%Y-%m-%d %H:%M:%S')"
    
    # 返回失败测试数量
    return $failed_tests
}

# ==================== 主函数 ====================
execute_tests

exit $?
