#!/bin/bash

LOG_DIR="/root/my_youtube_summarizer/backend/logs"
APP_LOG="$LOG_DIR/app.log"
ERROR_LOG="$LOG_DIR/error.log"

show_usage() {
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  -f, --follow       实时跟踪日志 (tail -f)"
    echo "  -e, --errors       只显示错误日志"
    echo "  -n NUM             显示最后 NUM 行 (默认: 50)"
    echo "  -s, --search TERM  搜索包含 TERM 的日志"
    echo "  -t, --today        只显示今天的日志"
    echo "  -r, --request ID   按request_id过滤日志"
    echo "  -h, --help         显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 -f              # 实时查看日志"
    echo "  $0 -e -n 100       # 查看最近100条错误"
    echo "  $0 -s 'video upload'  # 搜索视频上传相关日志"
    echo "  $0 -r abc123       # 查看特定请求的所有日志"
}

# 默认参数
LINES=50
FOLLOW=false
ERRORS_ONLY=false
SEARCH_TERM=""
TODAY_ONLY=false
REQUEST_ID=""

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--follow)
            FOLLOW=true
            shift
            ;;
        -e|--errors)
            ERRORS_ONLY=true
            shift
            ;;
        -n)
            LINES="$2"
            shift 2
            ;;
        -s|--search)
            SEARCH_TERM="$2"
            shift 2
            ;;
        -t|--today)
            TODAY_ONLY=true
            shift
            ;;
        -r|--request)
            REQUEST_ID="$2"
            shift 2
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            echo "未知选项: $1"
            show_usage
            exit 1
            ;;
    esac
done

# 检查日志目录
if [ ! -d "$LOG_DIR" ]; then
    echo "错误: 日志目录不存在: $LOG_DIR"
    echo "请先启动后端服务以生成日志"
    exit 1
fi

# 选择日志文件
if [ "$ERRORS_ONLY" = true ]; then
    LOG_FILE="$ERROR_LOG"
    if [ ! -f "$LOG_FILE" ]; then
        echo "没有错误日志"
        exit 0
    fi
else
    LOG_FILE="$APP_LOG"
    if [ ! -f "$LOG_FILE" ]; then
        echo "错误: 应用日志不存在: $LOG_FILE"
        exit 1
    fi
fi

# 构建过滤命令
FILTER_CMD="cat"

# 按日期过滤
if [ "$TODAY_ONLY" = true ]; then
    TODAY=$(date +%Y-%m-%d)
    FILTER_CMD="grep '$TODAY'"
fi

# 按request_id过滤
if [ -n "$REQUEST_ID" ]; then
    FILTER_CMD="$FILTER_CMD | grep '\"request_id\": \"$REQUEST_ID\"'"
fi

# 按搜索词过滤
if [ -n "$SEARCH_TERM" ]; then
    FILTER_CMD="$FILTER_CMD | grep -i '$SEARCH_TERM'"
fi

# 执行查看
if [ "$FOLLOW" = true ]; then
    echo "实时跟踪日志: $LOG_FILE"
    echo "按 Ctrl+C 退出"
    echo "----------------------------------------"
    eval "$FILTER_CMD $LOG_FILE | tail -f"
else
    eval "$FILTER_CMD $LOG_FILE | tail -n $LINES | jq -r '[.timestamp, .level, .message] | @tsv' 2>/dev/null || eval \"$FILTER_CMD $LOG_FILE | tail -n $LINES\""
fi
