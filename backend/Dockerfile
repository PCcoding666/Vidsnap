# VidSnap 后端镜像
# 基于本地一致的 Python 3.10
FROM python:3.10-slim

# ffmpeg：音频提取 / 截帧的底层二进制（ffmpeg-python 仅是 wrapper，必须装系统 ffmpeg）
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖，利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝应用代码
COPY . .

# 临时文件/产物目录（compose 里挂 volume 持久化）
RUN mkdir -p /data/tmp /data/storage

EXPOSE 8000

# 生产启动：无 --reload。
# 注意：workspace job runner 是进程内内存态（self.jobs/self.results），
# 多 worker 下提交与轮询可能命中不同进程导致 job 查不到，故固定单 worker。
# 需要横向扩展时，按 docs/deployment.md 把 job 状态迁到 Postgres + 任务队列。
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
