# 测试结构说明

## 测试代码整理

我们已将项目中所有与测试相关的非核心组件代码移至 `tests` 目录，保持主代码库的整洁。整理工作包括：

1. 创建了标准的测试目录结构：
   - `tests/`: 测试代码主目录
   - `tests/docs/`: 测试相关文档
   - `tests/logs/`: 测试日志

2. 移动了以下测试文件到测试目录：
   - `test_qwen_api_format.py`: 千问API格式测试
   - `test_qwen_direct.py`: 直接API调用测试
   - `test_qwen_integration.py`: 千问服务集成测试
   - `test_qwen_api.py`: 千问API功能测试

3. 移动了千问API格式文档：
   - `docs/qwen_api_format.md` → `tests/docs/qwen_api_format.md`

4. 调整了测试脚本中的导入路径和日志配置，确保它们在新位置可以正常运行。

5. 创建了测试README文件 (`tests/README.md`)，解释测试结构和如何运行测试。

## 运行测试

测试可以从项目根目录或后端目录运行：

### 从后端目录运行

```bash
# 运行直接API测试
python -m tests.test_qwen_direct

# 运行API格式测试
python -m tests.test_qwen_api_format

# 运行集成测试
python -m tests.test_qwen_integration -t all

# 仅运行特定测试
python -m tests.test_qwen_integration -t api
```

### 从项目根目录运行

```bash
# 运行直接API测试
python -m backend.tests.test_qwen_direct

# 运行API格式测试
python -m backend.tests.test_qwen_api_format

# 运行集成测试
python -m backend.tests.test_qwen_integration -t all

# 仅运行特定测试
python -m backend.tests.test_qwen_integration -t api
```

更多测试细节请参阅 [tests/README.md](tests/README.md)。

## 测试日志

所有测试日志都保存在 `tests/logs/` 目录下，每个测试脚本都有独立的日志文件。这使得调试和问题排查更加方便。

## 后续测试工作建议

1. 添加单元测试，覆盖关键功能组件
2. 实现自动化测试流程，例如通过CI/CD自动运行测试
3. 增加测试覆盖率统计
4. 根据需要继续完善和扩展现有测试 