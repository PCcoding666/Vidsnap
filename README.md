# 阿里云视频分析平台后端

这是阿里云视频分析平台的后端服务，提供视频处理、音频转录和内容分析功能。

## 项目结构

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # 应用入口
│   ├── api/                    # API路由
│   │   ├── __init__.py
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── video.py        # 视频处理相关API
│   │   │   └── analysis.py     # 分析相关API
│   │   └── dependencies.py     # 依赖项
│   ├── core/                   # 核心配置
│   │   ├── __init__.py
│   │   ├── config.py           # 配置管理
│   │   └── logging.py          # 日志配置
│   ├── models/                 # 数据模型
│   │   ├── __init__.py
│   │   ├── video.py            # 视频相关数据模型
│   │   └── analysis.py         # 分析相关数据模型
│   ├── services/               # 业务服务层
│   │   ├── __init__.py
│   │   ├── video_service.py    # 视频处理服务
│   │   ├── speech_service.py   # 语音识别服务
│   │   ├── oss_service.py      # OSS存储服务
│   │   └── pipeline_service.py # 处理管道服务
│   ├── utils/                  # 工具函数
│   │   ├── __init__.py
│   │   └── ffmpeg_utils.py     # ffmpeg工具函数
│   └── tests/                  # 测试代码
│       ├── __init__.py
│       ├── test_video_service.py
│       ├── test_speech_service.py
│       ├── test_oss_service.py
│       └── test_pipeline_service.py
├── requirements.txt            # 依赖文件
└── README.md                  # 项目说明
```

## 安装依赖

```bash
pip install -r requirements.txt
```

## 环境变量配置

创建 `.env` 文件并配置以下环境变量：

```env
# 阿里云访问密钥
ALIYUN_ACCESS_KEY_ID=your_access_key_id
ALIYUN_ACCESS_KEY_SECRET=your_access_key_secret

# OSS配置
ALIYUN_OSS_ENDPOINT=https://oss-cn-hangzhou.aliyuncs.com
ALIYUN_OSS_BUCKET=your_bucket_name

# OpenAI配置
OPENAI_API_KEY=your_openai_api_key
```

## 运行服务

```bash
python -m app.main
```

或者使用uvicorn：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## API文档

启动服务后，可以通过以下URL访问API文档：

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 测试

运行单元测试：

```bash
pytest app/tests/
```