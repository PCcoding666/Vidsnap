# 千问API测试

这个目录包含了与千问API服务相关的所有测试代码和文档。

## 目录结构

```
tests/
├── __init__.py           # 测试包初始化文件
├── README.md             # 本文档
├── docs/                 # 测试相关文档
│   └── qwen_api_format.md # 千问API格式文档
├── logs/                 # 测试日志目录
└── test_*.py             # 各种测试脚本
```

## 测试脚本说明

1. **test_qwen_api_format.py**: 测试千问API的请求格式，验证正确的JSON结构
2. **test_qwen_direct.py**: 直接调用千问API的测试，不依赖QwenService类
3. **test_qwen_integration.py**: 千问服务集成测试，测试QwenService类的主要功能
4. **test_qwen_api.py**: 千问API功能测试

## 如何运行测试

测试可以从项目根目录或后端目录运行：

### 从后端目录运行

```bash
# 运行直接API测试
python -m tests.test_qwen_direct

# 运行API格式测试
python -m tests.test_qwen_api_format

# 运行集成测试 (所有测试)
python -m tests.test_qwen_integration -t all

# 运行特定类型的集成测试
python -m tests.test_qwen_integration -t api  # 只测试API调用
python -m tests.test_qwen_integration -t text  # 只测试文本摘要
python -m tests.test_qwen_integration -t multimodal  # 只测试多模态摘要
```

### 从项目根目录运行

```bash
# 运行直接API测试
python -m backend.tests.test_qwen_direct

# 运行API格式测试
python -m backend.tests.test_qwen_api_format

# 运行集成测试 (所有测试)
python -m backend.tests.test_qwen_integration -t all

# 运行特定类型的集成测试
python -m backend.tests.test_qwen_integration -t api  # 只测试API调用
```

## 日志

所有测试日志都保存在 `tests/logs/` 目录下。每个测试脚本都有自己的日志文件。 