#!/bin/bash
# 完整视频处理管道测试脚本（包含 LLM 视频总结）
# 测试流程: YouTube下载 -> 关键帧提取 -> OSS上传 -> SenseVoice转录 -> Qwen3-VL双模型总结
# 模型配置:
#   - Qwen3-VL-Flash (qwen-vl-max): 关键帧图像分析
#   - Qwen3-VL-Plus (qwen-vl-plus): 主视频文本总结

set -e  # 遇到错误立即退出

# 设置代理
export https_proxy=http://127.0.0.1:33210
export http_proxy=http://127.0.0.1:33210
export all_proxy=socks5://127.0.0.1:33211

echo "=========================================="
echo "完整视频处理管道测试"
echo "包含: YouTube下载 + 关键帧提取 + OSS上传 + SenseVoice转录 + Qwen3-VL双模型总结"
echo "模型: Flash(图像) + Plus(文本)"
echo "=========================================="
echo ""

# 获取脚本所在目录的绝对路径
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

echo "项目根目录: $PROJECT_ROOT"
echo "当前工作目录: $(pwd)"
echo ""

# 检查 .env 文件
ENV_FILE="$PROJECT_ROOT/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "错误: 找不到 .env 文件: $ENV_FILE"
    exit 1
fi

echo "✓ 找到 .env 文件: $ENV_FILE"

# 加载环境变量
set -a
source "$ENV_FILE"
set +a

echo "✓ 环境变量已加载"
echo ""

# 检查必需的环境变量
echo "检查必需的环境变量..."
MISSING_VARS=0

# OSS 配置
if [ -z "$ALIYUN_ACCESS_KEY_ID" ]; then
    echo "✗ 缺少: ALIYUN_ACCESS_KEY_ID"
    MISSING_VARS=1
else
    echo "✓ ALIYUN_ACCESS_KEY_ID: ${ALIYUN_ACCESS_KEY_ID:0:10}..."
fi

if [ -z "$ALIYUN_ACCESS_KEY_SECRET" ]; then
    echo "✗ 缺少: ALIYUN_ACCESS_KEY_SECRET"
    MISSING_VARS=1
else
    echo "✓ ALIYUN_ACCESS_KEY_SECRET: ${ALIYUN_ACCESS_KEY_SECRET:0:10}..."
fi

if [ -z "$ALIYUN_OSS_ENDPOINT" ]; then
    echo "✗ 缺少: ALIYUN_OSS_ENDPOINT"
    MISSING_VARS=1
else
    echo "✓ ALIYUN_OSS_ENDPOINT: $ALIYUN_OSS_ENDPOINT"
fi

if [ -z "$ALIYUN_OSS_BUCKET" ]; then
    echo "✗ 缺少: ALIYUN_OSS_BUCKET"
    MISSING_VARS=1
else
    echo "✓ ALIYUN_OSS_BUCKET: $ALIYUN_OSS_BUCKET"
fi

# Qwen API 密钥检查
if [ -z "$QWEN_API_KEY" ] && [ -z "$DASHSCOPE_API_KEY" ]; then
    echo "✗ 缺少: QWEN_API_KEY 或 DASHSCOPE_API_KEY"
    MISSING_VARS=1
else
    if [ -n "$QWEN_API_KEY" ]; then
        echo "✓ QWEN_API_KEY: ${QWEN_API_KEY:0:10}..."
    else
        echo "✓ DASHSCOPE_API_KEY: ${DASHSCOPE_API_KEY:0:10}..."
    fi
fi

echo ""

if [ $MISSING_VARS -eq 1 ]; then
    echo "错误: 存在缺失的环境变量，请检查 .env 文件"
    exit 1
fi

echo "✓ 所有必需的环境变量已设置"
echo ""

# 检查 Python 环境
echo "检查 Python 环境..."

# 检测是否在 Conda 环境中
if [ -n "$CONDA_DEFAULT_ENV" ]; then
    echo "✓ 检测到 Conda 环境: $CONDA_DEFAULT_ENV"
    PYTHON_CMD="python"
elif [ -n "$VIRTUAL_ENV" ]; then
    echo "✓ 检测到虚拟环境: $VIRTUAL_ENV"
    PYTHON_CMD="python"
else
    echo "警告: 未检测到虚拟环境，使用系统 Python"
    PYTHON_CMD="python3"
fi

echo "使用 Python 命令: $PYTHON_CMD"
echo "Python 版本: $($PYTHON_CMD --version)"
echo ""

# 检查必需的 Python 包
echo "检查必需的 Python 包..."

# 使用函数处理包名映射（兼容 Bash 3.x）
check_package() {
    local pip_name="$1"
    local import_name="$2"
    
    if $PYTHON_CMD -c "import $import_name" 2>/dev/null; then
        echo "✓ $pip_name 已安装"
        return 0
    else
        echo "✗ $pip_name 未安装"
        echo "请运行: pip install $pip_name"
        return 1
    fi
}

# 检查所有必需的包
ALL_PACKAGES_INSTALLED=true

check_package "pytest" "pytest" || ALL_PACKAGES_INSTALLED=false
check_package "pytest-asyncio" "pytest_asyncio" || ALL_PACKAGES_INSTALLED=false
check_package "dashscope" "dashscope" || ALL_PACKAGES_INSTALLED=false
check_package "oss2" "oss2" || ALL_PACKAGES_INSTALLED=false
check_package "yt-dlp" "yt_dlp" || ALL_PACKAGES_INSTALLED=false
check_package "ffmpeg-python" "ffmpeg" || ALL_PACKAGES_INSTALLED=false

if [ "$ALL_PACKAGES_INSTALLED" = false ]; then
    exit 1
fi

echo ""
echo "✓ 所有必需的 Python 包已安装"
echo ""

# 检查 ffmpeg
echo "检查 ffmpeg..."
if command -v ffmpeg &> /dev/null; then
    echo "✓ ffmpeg 已安装"
    ffmpeg -version | head -n 1
else
    echo "✗ ffmpeg 未安装，音频提取功能将不可用"
    echo "请安装 ffmpeg: brew install ffmpeg (macOS) 或 apt-get install ffmpeg (Linux)"
    exit 1
fi

echo ""

# 创建测试报告目录
REPORT_DIR="$PROJECT_ROOT/backend/app/tests/docs"
mkdir -p "$REPORT_DIR"

REPORT_FILE="$REPORT_DIR/TEST_COMPLETE_PIPELINE_RESULTS.md"

echo "测试报告将保存到: $REPORT_FILE"
echo ""

# 运行测试
echo "=========================================="
echo "开始运行完整管道测试..."
echo "=========================================="
echo ""

cd "$PROJECT_ROOT/backend"

# 运行 pytest
$PYTHON_CMD -m pytest app/tests/test_complete_pipeline.py -v -s --tb=short 2>&1 | tee /tmp/test_output.log

TEST_EXIT_CODE=${PIPESTATUS[0]}

echo ""
echo "=========================================="
echo "测试完成"
echo "=========================================="
echo ""

# 生成测试报告
echo "生成测试报告..."

cat > "$REPORT_FILE" << 'EOF'
# 完整视频处理管道测试报告

## 测试概述

本报告记录了完整视频处理管道的集成测试结果，包括：

1. **YouTube 视频下载**
2. **关键帧提取**
3. **OSS 存储上传**
4. **SenseVoice 音频转录**
5. **Qwen3-VL-Flash 视频总结**

## 测试环境

EOF

echo "- 测试时间: $(date)" >> "$REPORT_FILE"
echo "- Python 版本: $($PYTHON_CMD --version)" >> "$REPORT_FILE"
echo "- 项目路径: $PROJECT_ROOT" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "## 环境变量检查" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "- ALIYUN_ACCESS_KEY_ID: ✓ 已设置" >> "$REPORT_FILE"
echo "- ALIYUN_ACCESS_KEY_SECRET: ✓ 已设置" >> "$REPORT_FILE"
echo "- ALIYUN_OSS_ENDPOINT: $ALIYUN_OSS_ENDPOINT" >> "$REPORT_FILE"
echo "- ALIYUN_OSS_BUCKET: $ALIYUN_OSS_BUCKET" >> "$REPORT_FILE"

if [ -n "$QWEN_API_KEY" ]; then
    echo "- QWEN_API_KEY: ✓ 已设置" >> "$REPORT_FILE"
else
    echo "- DASHSCOPE_API_KEY: ✓ 已设置" >> "$REPORT_FILE"
fi

echo "" >> "$REPORT_FILE"

echo "## 测试结果" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "### ✅ 测试状态: 全部通过" >> "$REPORT_FILE"
else
    echo "### ❌ 测试状态: 部分失败" >> "$REPORT_FILE"
fi

echo "" >> "$REPORT_FILE"
echo "### 详细测试输出" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo '```' >> "$REPORT_FILE"
cat /tmp/test_output.log >> "$REPORT_FILE"
echo '```' >> "$REPORT_FILE"

echo "" >> "$REPORT_FILE"
echo "## 测试项目清单" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "- [ ] Qwen VL 服务可用性检查" >> "$REPORT_FILE"
echo "- [ ] 关键帧描述生成" >> "$REPORT_FILE"
echo "- [ ] 完整视频总结（模拟数据）" >> "$REPORT_FILE"
echo "- [ ] 多种总结粒度测试" >> "$REPORT_FILE"
echo "- [ ] 时间线同步测试" >> "$REPORT_FILE"
echo "- [ ] 完整端到端管道（真实YouTube视频）" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "## 性能指标" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "- 测试总耗时: 见上述日志" >> "$REPORT_FILE"
echo "- 视频下载速度: 取决于网络状况" >> "$REPORT_FILE"
echo "- 关键帧提取速度: 取决于视频长度" >> "$REPORT_FILE"
echo "- 转录速度: 取决于音频长度" >> "$REPORT_FILE"
echo "- LLM 总结速度: 取决于关键帧数量" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "## 输出文件" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "所有生成的文件都上传到了阿里云 OSS，包括：" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "- 视频文件 (OSS)" >> "$REPORT_FILE"
echo "- 关键帧图片 (OSS)" >> "$REPORT_FILE"
echo "- 音频文件 (OSS)" >> "$REPORT_FILE"
echo "- 元数据文件 (OSS)" >> "$REPORT_FILE"
echo "- 视频总结文件 (OSS)" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "## 下一步" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "1. 检查 OSS 中的所有生成文件" >> "$REPORT_FILE"
echo "2. 验证视频总结的质量" >> "$REPORT_FILE"
echo "3. 测试不同类型的视频" >> "$REPORT_FILE"
echo "4. 优化 LLM 提示词以提高总结质量" >> "$REPORT_FILE"
echo "5. 实现缓存机制以提高性能" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "---" >> "$REPORT_FILE"
echo "报告生成时间: $(date)" >> "$REPORT_FILE"

echo "✓ 测试报告已生成: $REPORT_FILE"
echo ""

# 显示报告位置
echo "=========================================="
echo "测试报告位置:"
echo "$REPORT_FILE"
echo "=========================================="
echo ""

# 返回测试退出码
exit $TEST_EXIT_CODE
