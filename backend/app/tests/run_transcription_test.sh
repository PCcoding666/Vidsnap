#!/bin/bash

# YouTube 视频到转录的端到端测试脚本
# 测试阿里云 SenseVoice 音频转录服务

# 获取脚本所在目录和backend目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="$( cd "$SCRIPT_DIR/../../.." && pwd )"

echo "=========================================="
echo "YouTube 视频转录集成测试"
echo "使用阿里云 DashScope SenseVoice"
echo "=========================================="
echo ""
echo "脚本位置: $SCRIPT_DIR"
echo "Backend目录: $BACKEND_DIR"
echo ""

# 检查环境变量
echo "检查环境配置..."

# 尝试从 .env 文件加载环境变量
if [ -f "$BACKEND_DIR/.env" ]; then
    echo "✓ 发现 .env 文件,加载环境变量..."
    export $(cat "$BACKEND_DIR/.env" | grep -v '^#' | xargs)
else
    echo "⚠️  未找到 .env 文件"
fi

# 检查音频转录API密钥 (优先使用 TRANSCRIPT_SERVICE_API_KEY)
if [ -n "$TRANSCRIPT_SERVICE_API_KEY" ]; then
    echo "✓ TRANSCRIPT_SERVICE_API_KEY 已设置 (专用于音频转录)"
elif [ -n "$QWEN_API_KEY" ]; then
    echo "✓ QWEN_API_KEY 已设置 (后备选项)"
else
    echo "❌ 错误: 未设置音频转录API密钥"
    echo "请在 .env 文件中设置以下任一变量:"
    echo "  TRANSCRIPT_SERVICE_API_KEY='your_api_key' (推荐)"
    echo "  QWEN_API_KEY='your_api_key' (后备)"
    exit 1
fi

if [ -z "$ALIYUN_ACCESS_KEY_ID" ] || [ -z "$ALIYUN_ACCESS_KEY_SECRET" ]; then
    echo "❌ 错误: 阿里云 OSS 配置不完整"
    echo "请设置:"
    echo "  export ALIYUN_ACCESS_KEY_ID='your_access_key_id'"
    echo "  export ALIYUN_ACCESS_KEY_SECRET='your_access_key_secret'"
    exit 1
fi
echo "✓ 阿里云 OSS 配置已设置"

if [ -z "$ALIYUN_OSS_ENDPOINT" ] || [ -z "$ALIYUN_OSS_BUCKET" ]; then
    echo "❌ 错误: OSS Endpoint 或 Bucket 未设置"
    echo "请设置:"
    echo "  export ALIYUN_OSS_ENDPOINT='oss-cn-hangzhou.aliyuncs.com'"
    echo "  export ALIYUN_OSS_BUCKET='your_bucket_name'"
    exit 1
fi
echo "✓ OSS Endpoint 和 Bucket 已设置"

echo ""

# 检查依赖
echo "检查依赖..."

if ! python3 -c "import dashscope" 2>/dev/null; then
    echo "❌ 错误: dashscope 包未安装"
    echo "请运行: pip install dashscope>=1.14.0"
    exit 1
fi
echo "✓ dashscope 包已安装"

if ! python3 -c "import oss2" 2>/dev/null; then
    echo "❌ 错误: oss2 包未安装"
    echo "请运行: pip install oss2>=2.18.0"
    exit 1
fi
echo "✓ oss2 包已安装"

if ! python3 -c "import pytest" 2>/dev/null; then
    echo "❌ 错误: pytest 包未安装"
    echo "请运行: pip install pytest pytest-asyncio"
    exit 1
fi
echo "✓ pytest 包已安装"

echo ""

# 运行测试
echo "开始运行测试..."
echo "测试文件: $BACKEND_DIR/app/tests/test_video_to_transcription_pipeline.py"
echo ""
echo "注意: 转录过程可能需要较长时间,请耐心等待..."
echo ""

# 切换到backend目录
cd "$BACKEND_DIR"

# 记录开始时间
START_TIME=$(date +%s)

# 运行 pytest
pytest app/tests/test_video_to_transcription_pipeline.py \
    -v \
    -s \
    --tb=short \
    --log-cli-level=INFO \
    2>&1 | tee test_output.log

# 获取测试退出码
TEST_EXIT_CODE=${PIPESTATUS[0]}

# 记录结束时间
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo ""
echo "=========================================="
echo "测试完成"
echo "=========================================="
echo "总耗时: ${DURATION} 秒"
echo ""

# 如果测试成功，显示转录文本示例
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "==========================================" 
    echo "✅ 转录文本示例（前20行）"
    echo "=========================================="
    echo ""
    
    # 提取转录结果中的文本内容
    if grep -q "转录内容示例" test_output.log; then
        # 提取所有包含 "文本:" 的行，只显示文本内容，前20行
        grep "文本:" test_output.log | sed 's/.*文本: //' | head -20 | while IFS= read -r line; do
            echo "  $line"
        done
        
        # 统计总段落数
        TOTAL_SEGMENTS=$(grep -c "文本:" test_output.log)
        if [ $TOTAL_SEGMENTS -gt 20 ]; then
            echo ""
            echo "  ... (共 $TOTAL_SEGMENTS 个转录段落，仅显示前20行)"
        else
            echo ""
            echo "  (共 $TOTAL_SEGMENTS 个转录段落)"
        fi
    else
        echo "  ⚠️  未找到转录文本示例"
        echo "  请查看 test_output.log 获取详细信息"
    fi
    
    echo ""
    echo "=========================================="
fi
echo ""

# 生成测试报告
echo "生成测试报告..."
cat > "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md" << 'EOF'
# YouTube 视频转录集成测试报告

## 测试时间
EOF

echo "- 测试时间: $(date '+%Y-%m-%d %H:%M:%S')" >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
echo "- 总耗时: ${DURATION} 秒" >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
echo "" >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"

cat >> TEST_TRANSCRIPTION_RESULTS.md << 'EOF'
## 测试环境

- Python 版本: 
EOF

python3 --version >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"

cat >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md" << 'EOF'

- DashScope SDK 版本:
EOF

python3 -c "import dashscope; print(f'  - dashscope: {dashscope.__version__}')" 2>/dev/null >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md" || echo "  - dashscope: 未知版本" >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"

cat >> TEST_TRANSCRIPTION_RESULTS.md << 'EOF'

## 测试结果

EOF

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "✅ **状态**: 全部通过" >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
else
    echo "❌ **状态**: 测试失败" >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
fi

echo "" >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"

cat >> TEST_TRANSCRIPTION_RESULTS.md << 'EOF'
## 测试详情

请查看 `test_output.log` 获取完整的测试输出。

### 测试用例

1. **test_dashscope_service_availability**: 检查 DashScope 服务可用性
2. **test_full_pipeline_youtube_to_transcription**: 完整流程测试
   - YouTube 视频下载
   - 音频提取 (ffmpeg)
   - 音频上传到 OSS
   - SenseVoice 音频转录
   - 转录结果验证
3. **test_transcription_segments_format**: 转录段落格式验证
4. **test_cleanup_after_processing**: 临时文件清理测试

### 关键指标

EOF

# 提取关键信息(如果测试成功)
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "从测试输出中提取关键指标..." >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
    echo "" >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
    
    # 尝试提取转录信息
    if grep -q "检测语言:" test_output.log; then
        echo "**转录语言**: $(grep "检测语言:" test_output.log | head -1 | sed 's/.*检测语言: //')" >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
    fi
    
    if grep -q "段落数量:" test_output.log; then
        echo "**段落数量**: $(grep "段落数量:" test_output.log | head -1 | sed 's/.*段落数量: //')" >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
    fi
    
    if grep -q "总体置信度:" test_output.log; then
        echo "**总体置信度**: $(grep "总体置信度:" test_output.log | head -1 | sed 's/.*总体置信度: //')" >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
    fi
    
    echo "" >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
fi

cat >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md" << 'EOF'

### 性能数据

EOF

# 提取性能数据
if grep -q "视频下载:" test_output.log; then
    echo "- **视频下载**: $(grep "视频下载:" test_output.log | tail -1 | sed 's/.*视频下载: //')" >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
fi

if grep -q "音频提取:" test_output.log; then
    echo "- **音频提取**: $(grep "音频提取:" test_output.log | tail -1 | sed 's/.*音频提取: //')" >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
fi

if grep -q "OSS上传:" test_output.log; then
    echo "- **OSS上传**: $(grep "OSS上传:" test_output.log | tail -1 | sed 's/.*OSS上传: //')" >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
fi

if grep -q "SenseVoice转录:" test_output.log; then
    echo "- **SenseVoice转录**: $(grep "SenseVoice转录:" test_output.log | tail -1 | sed 's/.*SenseVoice转录: //')" >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
fi

cat >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md" << 'EOF'

## OSS 资源

测试过程中上传的文件:

EOF

# 提取 OSS URL
if grep -q "OSS URL:" test_output.log; then
    echo "### 音频文件" >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
    echo "" >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
    grep "OSS URL:" test_output.log | sed 's/.*OSS URL: /- /' >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
    echo "" >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
fi

cat >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md" << 'EOF'

## 转录示例

EOF

# 提取转录示例
if grep -q "转录内容示例" test_output.log; then
    echo "从测试输出提取的转录内容:" >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
    echo "" >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
    echo '```' >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
    
    # 提取转录示例段落
    sed -n '/转录内容示例/,/共.*个段落/p' test_output.log | grep -E "(^\s+\[|文本:|置信度:)" >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
    
    echo '```' >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
    echo "" >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
fi

cat >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md" << 'EOF'

## 错误日志

EOF

if [ $TEST_EXIT_CODE -ne 0 ]; then
    echo "测试失败,错误信息:" >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
    echo "" >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
    echo '```' >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
    grep -i "error\|fail\|exception" test_output.log | tail -20 >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
    echo '```' >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
else
    echo "无错误" >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
fi

echo "" >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
echo "---" >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
echo "*报告生成时间: $(date '+%Y-%m-%d %H:%M:%S')*" >> "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"

echo "✓ 测试报告已生成: $BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"
echo ""

# 显示摘要
echo "=========================================="
echo "测试摘要"
echo "=========================================="
cat "$BACKEND_DIR/app/tests/docs/TEST_TRANSCRIPTION_RESULTS.md"

exit $TEST_EXIT_CODE
