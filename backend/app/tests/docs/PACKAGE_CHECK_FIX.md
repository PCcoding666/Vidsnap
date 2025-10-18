# Python 包检查修复说明

## 问题描述

在运行 `run_complete_pipeline_test.sh` 时，脚本错误地报告 `pytest-asyncio` 未安装，但实际上该包已经正确安装。

### 错误输出

```bash
检查必需的 Python 包...
✓ pytest 已安装
✗ pytest-asyncio 未安装
请运行: pip install pytest-asyncio
```

### 实际情况

```bash
$ pip install pytest-asyncio
Requirement already satisfied: pytest-asyncio in /Users/chengpeng/miniconda3/envs/yt_summarizer/lib/python3.10/site-packages (0.26.0)
```

## 根本原因

### Python 包名与导入名不一致

某些 Python 包的 **pip 安装名** 和 **Python 导入名** 不一致：

| pip 包名 | Python 导入名 | 说明 |
|---------|--------------|------|
| `pytest-asyncio` | `pytest_asyncio` | 连字符变下划线 |
| `yt-dlp` | `yt_dlp` | 连字符变下划线 |
| `ffmpeg-python` | `ffmpeg` | 完全不同的名称 |

### 错误的检查逻辑

原脚本直接使用 pip 包名进行导入检查：

```bash
REQUIRED_PACKAGES=("pytest" "pytest-asyncio" "dashscope" "oss2" "yt-dlp" "ffmpeg-python")

for package in "${REQUIRED_PACKAGES[@]}"; do
    if $PYTHON_CMD -c "import $package" 2>/dev/null; then
        echo "✓ $package 已安装"
    else
        echo "✗ $package 未安装"
    fi
done
```

当执行 `python -c "import pytest-asyncio"` 时会失败，因为：
- Python 不认识 `pytest-asyncio` 这个名称
- 正确的导入语句应该是 `import pytest_asyncio`

## 解决方案

### 修复后的代码（兼容 Bash 3.x）

由于 macOS 默认使用 Bash 3.2，不支持关联数组，我们使用函数来处理包名映射：

```bash
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
```

### Bash 版本兼容性说明

**问题**：macOS 默认的 Bash 版本是 3.2（2007年发布），不支持关联数组（`declare -A`）。

```bash
# 检查 Bash 版本
$ bash --version
GNU bash, version 3.2.57(1)-release (arm64-apple-darwin24)

# Bash 3.x 不支持这个语法：
declare -A PACKAGE_MAP=(...)  # ❌ 会报错：declare: -A: invalid option
```

**解决方案**：使用函数封装逻辑，通过参数传递包名映射，完全兼容 Bash 3.x。

## 影响范围

### 已修复的脚本

- ✅ `run_complete_pipeline_test.sh` - 已使用新的映射检查逻辑

### 已验证正常的脚本

- ✅ `run_pipeline_test.sh` - 已有特殊处理逻辑（虽然不够优雅但能正常工作）
- ✅ `run_transcription_test.sh` - 不包含包检查逻辑

## 验证方法

运行修复后的测试脚本：

```bash
cd /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend
./app/tests/run_complete_pipeline_test.sh
```

预期输出：

```bash
检查必需的 Python 包...
✓ pytest 已安装
✓ pytest-asyncio 已安装
✓ dashscope 已安装
✓ oss2 已安装
✓ yt-dlp 已安装
✓ ffmpeg-python 已安装

✓ 所有必需的 Python 包已安装
```

## 最佳实践

### 1. 总是验证包导入名

在编写包检查脚本时，需要验证 Python 导入名：

```bash
# 验证导入名
python -c "import pytest_asyncio"  # ✅ 正确
python -c "import pytest-asyncio"  # ❌ 错误
```

### 2. 常见包名映射

```bash
# 连字符转下划线
pip install pytest-asyncio  → import pytest_asyncio
pip install yt-dlp          → import yt_dlp

# 完全不同的名称
pip install ffmpeg-python   → import ffmpeg
pip install Pillow          → import PIL
pip install beautifulsoup4  → import bs4
```

### 3. Bash 脚本兼容性

**macOS 兼容性注意事项**：

- macOS 默认使用 Bash 3.2（2007年发布）
- Bash 4.0+ 才支持关联数组（`declare -A`）
- 编写脚本时应考虑 Bash 3.x 兼容性

**推荐做法**：

```bash
# ❌ 不推荐：需要 Bash 4.0+
declare -A PACKAGE_MAP=(...)

# ✅ 推荐：兼容 Bash 3.x
check_package() {
    local pip_name="$1"
    local import_name="$2"
    # 检查逻辑...
}
```

**升级 Bash（可选）**：

```bash
# 通过 Homebrew 安装最新的 Bash
brew install bash

# 检查版本
/usr/local/bin/bash --version  # Bash 5.x

# 修改脚本 shebang
#!/usr/local/bin/bash  # 使用新版 Bash
```

### 4. 使用 pkg_resources 检查

更可靠的方法是使用 `pkg_resources`：

```bash
python -c "import pkg_resources; pkg_resources.require('pytest-asyncio')"
```

或者使用 `importlib.metadata`（Python 3.8+）：

```bash
python -c "from importlib.metadata import version; print(version('pytest-asyncio'))"
```

## 相关文件

- `/backend/app/tests/run_complete_pipeline_test.sh` - 完整管道测试脚本（已修复）
- `/backend/app/tests/run_pipeline_test.sh` - OSS 管道测试脚本（已有处理）

## 修复时间

- 修复日期：2025-10-18
- 修复版本：已应用到所有相关测试脚本

---

**总结**：这个问题是由于 Python 包的 pip 安装名和导入名不一致造成的。通过引入包名映射机制，我们现在可以正确检测所有依赖包的安装状态。
