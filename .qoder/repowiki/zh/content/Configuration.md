# 配置

<cite>
**本文档引用的文件**   
- [main.py](file://main.py)
- [simple_llm_service.py](file://simple_llm_service.py)
- [simple_speech_service.py](file://simple_speech_service.py)
- [simple_video_service.py](file://simple_video_service.py)
- [video_processing_pipeline.py](file://video_processing_pipeline.py)
- [requirements_simple.txt](file://requirements_simple.txt)
- [package.json](file://package.json)
- [GOOGLE_SPEECH_SETUP.md](file://GOOGLE_SPEECH_SETUP.md)
- [youtube-summarizer-451419-2dd62705f73e.json](file://youtube-summarizer-451419-2dd62705f73e.json)
- [verify_config.py](file://verify_config.py) - *更新于最近提交*
- [requirements_aliyun.txt](file://requirements_aliyun.txt) - *新增于v0.1.2版本*
- [.env.example](file://.env.example) - *新增于v0.1.2版本*
</cite>

## 更新摘要
**已做更改**   
- 新增 `.env.example` 文件说明，反映 v0.1.2 版本的简化配置需求
- 更新依赖管理部分，同步 `requirements_simple.txt` 的最新依赖项
- 修正本地开发设置中的配置文件复制指引，增加 `.env.example` 示例支持
- 更新环境变量检查逻辑说明，基于 `verify_config.py` 的最新实现
- 移除关于 `MODEL_SELECTION` 的过时说明，确认其未被使用

## 目录
1. [环境变量](#环境变量)
2. [依赖管理](#依赖管理)
3. [Google Cloud服务账户密钥](#google-cloud服务账户密钥)
4. [本地开发设置](#本地开发设置)
5. [安全最佳实践](#安全最佳实践)

## 环境变量

My_Youtube_Summarizer 应用依赖多个环境变量来配置外部服务并控制行为。这些变量在 `main.py` 和 `verify_config.py` 中进行验证。

### OPENAI_API_KEY
**用途**: 用于访问 OpenAI 的 Whisper API 进行音频转录，以及在选择时使用 GPT-4 Vision 进行视频摘要。

**来源**: 在 `main.py` 和 `simple_llm_service.py` 中检查。LLM 服务在存在此密钥时优先使用 OpenAI。

```python
# 来自 main.py
openai_key = os.getenv("OPENAI_API_KEY")
```

### QWEN_API_KEY 或 DASHSCOPE_API_KEY
**用途**: 作为替代 API 密钥，用于阿里云的 Qwen-VL 模型进行多模态视频摘要。当 OpenAI 不可用时作为备用方案。

**来源**: 系统首先检查 `QWEN_API_KEY`，若不存在则回退到 `DASHSCOPE_API_KEY`（用于向后兼容）。

```python
# 来自 simple_llm_service.py
self.qwen_api_key = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
```

### GOOGLE_APPLICATION_CREDENTIALS
**用途**: 指向 Google Cloud 服务账户 JSON 密钥文件的路径。使用 Google Cloud Speech-to-Text API 作为替代转录服务时需要此变量。

**来源**: 在 `GOOGLE_SPEECH_SETUP.md` 中引用。应用使用此环境变量对 Google Cloud 服务进行身份验证。

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/youtube-summarizer-451419-2dd62705f73e.json"
```

### PORT
**用途**: 指定 Gradio Web 界面运行的端口号。若未设置，默认为 7860。

**来源**: 在 `main.py` 中作为可配置环境变量记录。

### ALIYUN_ACCESS_KEY_ID 和 ALIYUN_ACCESS_KEY_SECRET
**用途**: 用于身份验证阿里云 OSS（对象存储服务）的访问密钥 ID 和密钥 Secret。这些是使用阿里云存储功能所必需的。

**来源**: 在 `main.py` 和 `verify_config.py` 中检查，是启动应用时的必需变量。

```python
# 来自 main.py
required_env_vars = [
    'ALIYUN_ACCESS_KEY_ID',
    'ALIYUN_ACCESS_KEY_SECRET', 
    'ALIYUN_OSS_ENDPOINT',
    'ALIYUN_OSS_BUCKET',
    'OPENAI_API_KEY'
]
```

### ALIYUN_OSS_ENDPOINT 和 ALIYUN_OSS_BUCKET
**用途**: 分别指定阿里云 OSS 的服务端点和存储桶名称。用于视频和摘要结果的上传与存储。

**来源**: 在 `aliyun_oss_service.py` 和 `main.py` 中使用，由 `verify_config.py` 进行验证。

### MODEL_SELECTION
**注意**: 尽管在文档目标中提到，`MODEL_SELECTION` **未在任何项目文件中使用**。模型选择实际上基于可用的 API 密钥自动确定：
- 如果存在 `OPENAI_API_KEY` → 使用 GPT-4 Vision
- 否则如果存在 `QWEN_API_KEY` → 使用 Qwen-VL
- 否则 → 无 LLM 服务可用

此逻辑在 `simple_llm_service.py` 中实现。

**Section sources**
- [main.py](file://main.py#L36-L79)
- [simple_llm_service.py](file://simple_llm_service.py#L15-L35)
- [verify_config.py](file://verify_config.py#L39-L70) - *更新于v0.1.2版本*

## 依赖管理

### Python 依赖 (requirements_simple.txt)
项目使用 `requirements_simple.txt` 管理视频处理、转录和摘要所需的 Python 包。

关键依赖包括：
- **gradio**: Web 界面框架
- **yt-dlp**: 从 YouTube 和其他平台下载视频
- **opencv-python**: 视频帧提取和图像处理
- **openai**: 访问 Whisper 和 GPT-4 Vision API
- **SpeechRecognition**: 语音转录的可选本地备用方案
- **python-dotenv**: 环境变量管理

```txt
# 来自 requirements_simple.txt
gradio>=4.0.0
yt-dlp>=2023.10.13
opencv-python>=4.8.0
openai>=1.0.0
requests>=2.31.0
SpeechRecognition>=3.10.0
pydub>=0.25.1
Pillow>=10.0.0
numpy>=1.24.0
python-dotenv>=1.0.0
ffmpeg-python>=0.2.0
```

### 阿里云 Python 依赖 (requirements_aliyun.txt)
项目新增 `requirements_aliyun.txt` 以支持阿里云服务集成。

关键依赖包括：
- **oss2**: 阿里云对象存储服务 SDK
- **openai**: 使用 OpenAI Whisper 进行语音识别（替代阿里云语音服务）
- **gradio**: Web 界面
- **ffmpeg-python**: 视频处理支持

```txt
# 来自 requirements_aliyun.txt
gradio>=4.0.0
oss2>=2.18.0
openai>=1.0.0
ffmpeg-python>=0.2.0
python-dotenv>=1.0.0
```

### Node.js 依赖 (package.json)
项目包含最少的 Node.js 依赖，可能用于扩展功能中的浏览器自动化工具。

```json
{
  "dependencies": {
    "@agentdeskai/browser-tools-mcp": "^1.2.1"
  }
}
```

**Section sources**
- [requirements_simple.txt](file://requirements_simple.txt#L1-L31)
- [requirements_aliyun.txt](file://requirements_aliyun.txt#L1-L27) - *新增于v0.1.2版本*
- [package.json](file://package.json#L1-L6)

## Google Cloud服务账户密钥

文件 `youtube-summarizer-451419-2dd62705f73e.json` 是一个 Google Cloud 服务账户密钥，使应用能够对 Google Cloud API（特别是 Speech-to-Text API）进行身份验证。

### 密钥详情
- **项目ID**: `youtube-summarizer-451419`
- **服务账户邮箱**: `yt-summarizer@youtube-summarizer-451419.iam.gserviceaccount.com`
- **用途**: 对 Google Cloud Speech-to-Text 服务的 API 调用进行身份验证，作为 OpenAI Whisper 的替代方案。

### 设置说明
1. 将 JSON 密钥文件放在项目根目录。
2. 设置 `GOOGLE_APPLICATION_CREDENTIALS` 环境变量指向此文件。
3. 确保在 Cloud Console 中启用了 Google Cloud Speech-to-Text API。

系统将自动检测并使用此凭据进行音频转录（若可用），否则回退到 OpenAI Whisper。

**Section sources**
- [GOOGLE_SPEECH_SETUP.md](file://GOOGLE_SPEECH_SETUP.md#L1-L121)
- [youtube-summarizer-451419-2dd62705f73e.json](file://youtube-summarizer-451419-2dd62705f73e.json#L1-L14)

## 本地开发设置

按照以下步骤为本地开发设置 My_Youtube_Summarizer 应用：

### 1. 克隆仓库
```bash
git clone https://github.com/yourusername/youtube-summarizer.git
cd youtube-summarizer
```

### 2. 创建虚拟环境
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 3. 安装 Python 依赖
```bash
# 基础依赖
pip install -r requirements_simple.txt

# 或使用阿里云集成的依赖
pip install -r requirements_aliyun.txt
```

### 4. 设置环境变量
项目包含示例配置文件。根据需要复制相应的示例文件：

```bash
# 使用通用示例配置文件
cp .env.example .env

# 或对于阿里云配置
cp .env.aliyun.example .env

# 或对于 OpenAI 配置
cp .env.openai.example .env
```

编辑 `.env` 文件填入您的 API 密钥：

```env
OPENAI_API_KEY=your_openai_api_key
ALIYUN_ACCESS_KEY_ID=your_aliyun_access_key_id
ALIYUN_ACCESS_KEY_SECRET=your_aliyun_access_key_secret
ALIYUN_OSS_ENDPOINT=your_oss_endpoint
ALIYUN_OSS_BUCKET=your_oss_bucket
```

### 5. 配置 Google Cloud 凭据
下载服务账户 JSON 密钥并设置环境变量：
```bash
export GOOGLE_APPLICATION_CREDENTIALS="youtube-summarizer-451419-2dd62705f73e.json"
```

### 6. 运行应用
```bash
python main.py
```

Gradio 界面将在 `http://localhost:7860` 可用。

**Section sources**
- [README.md](file://README.md#L57-L128)
- [main.py](file://main.py#L0-L118)
- [verify_config.py](file://verify_config.py) - *新增验证脚本*

## 安全最佳实践

### 使用 .env 文件
将所有敏感凭据存储在 `.env` 文件中，并通过 `.gitignore` 从版本控制中排除。使用 `python-dotenv` 加载这些变量。

### 避免硬编码密钥
切勿在代码中直接提交 API 密钥或服务账户凭据。始终使用环境变量。

### 限制服务账户权限
Google Cloud 服务账户应具有最低必要权限（例如 `roles/speech.user`），而非广泛的管理访问权限。

### 安全的凭据存储
安全地存储 JSON 密钥文件并限制文件权限：
```bash
chmod 600 youtube-summarizer-451419-2dd62705f73e.json
```

### 使用 API 密钥轮换
定期轮换 API 密钥并在环境配置中更新。

### 开发与生产环境分离
为开发和生产环境使用独立的 API 密钥和服务账户，以防止意外使用并改善安全监控。

### 阿里云密钥管理
为阿里云 OSS 访问密钥使用具有最小权限的 RAM 子账户，避免使用主账户密钥。

**Section sources**
- [README.md](file://README.md#L57-L128)
- [GOOGLE_SPEECH_SETUP.md](file://GOOGLE_SPEECH_SETUP.md#L1-L121)
- [verify_config.py](file://verify_config.py#L39-L70) - *包含安全检查逻辑*