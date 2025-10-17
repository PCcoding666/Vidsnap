# Transcription Display Enhancement

## 修改时间
2025-10-17

## 修改目的

在运行 `run_transcription_test.sh` 测试脚本时，在终端中直接显示转录后的文字（前20行），以便快速确认转录是否成功以及转录质量。

## 修改内容

### 修改文件
- [`run_transcription_test.sh`](file:///Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend/run_transcription_test.sh)

### 新增功能

在测试成功完成后，脚本会自动：

1. **提取转录文本**：从测试输出日志中提取所有包含"文本:"的行
2. **清理格式**：去除日志前缀，只保留纯文本内容
3. **显示前20行**：在终端中直接显示前20行转录文本
4. **统计信息**：显示总转录段落数量

### 显示格式示例

```
==========================================
✅ 转录文本示例（前20行）
==========================================

  Sound on for Sora 2
  OpenAI's newest video generation model
  Now with audio
  ...（更多转录文本）

  （共 45 个转录段落，仅显示前20行）

==========================================
```

## 工作原理

```bash
if [ $TEST_EXIT_CODE -eq 0 ]; then
    # 1. 检查是否有转录内容
    if grep -q "转录内容示例" test_output.log; then
        # 2. 提取所有"文本:"行，去除前缀，显示前20行
        grep "文本:" test_output.log | sed 's/.*文本: //' | head -20
        
        # 3. 统计总段落数
        TOTAL_SEGMENTS=$(grep -c "文本:" test_output.log)
        
        # 4. 显示统计信息
        if [ $TOTAL_SEGMENTS -gt 20 ]; then
            echo "... (共 $TOTAL_SEGMENTS 个转录段落，仅显示前20行)"
        fi
    fi
fi
```

## 使用方法

直接运行测试脚本：

```bash
cd /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend
./run_transcription_test.sh
```

## 预期输出

### 测试成功时

测试完成后，终端会显示：
1. 测试摘要和耗时
2. ✅ **转录文本示例（前20行）** - 直接显示转录的文字内容
3. 总段落数统计
4. 完整的测试报告保存在 `TEST_TRANSCRIPTION_RESULTS.md`

### 测试失败时

- 不会显示转录文本示例
- 会显示错误日志
- 提示查看 `test_output.log` 获取详细信息

## 优势

1. **快速验证**：无需打开日志文件即可确认转录是否成功
2. **质量检查**：直接看到转录文本，可以快速判断转录质量
3. **调试便利**：如果转录有问题，可以立即在终端看到
4. **保持简洁**：只显示前20行，避免终端输出过长

## 相关文件

- [`run_transcription_test.sh`](file:///Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend/run_transcription_test.sh) - 测试脚本（已修改）
- [`test_video_to_transcription_pipeline.py`](file:///Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend/app/tests/test_video_to_transcription_pipeline.py) - 测试用例
- [`speech_service.py`](file:///Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend/app/services/speech_service.py) - SenseVoice 服务
- `test_output.log` - 完整测试输出（自动生成）
- `TEST_TRANSCRIPTION_RESULTS.md` - 测试报告（自动生成）

## 注意事项

1. **日志格式依赖**：脚本依赖测试输出中"文本:"关键字，如果测试日志格式改变，可能需要调整提取逻辑
2. **中文支持**：确保终端支持UTF-8编码以正确显示中文转录文本
3. **行数限制**：默认显示前20行，可以通过修改 `head -20` 来调整显示数量

---
**状态**: ✅ 已完成并可用
**测试**: 需要运行完整测试来验证显示效果
