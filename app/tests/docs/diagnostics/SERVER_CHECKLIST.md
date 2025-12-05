# 服务器环境检查清单

> **文档目标**: 提供系统化的服务器环境检查步骤,确保视频上传处理所需的所有环境配置正确

---

## 📋 目录

- [1. 快速检查脚本](#1-快速检查脚本)
- [2. 文件系统检查](#2-文件系统检查)
- [3. Web 服务器配置](#3-web-服务器配置)
- [4. FastAPI/Uvicorn 配置](#4-fastapiuvicorn-配置)
- [5. 网络连接检查](#5-网络连接检查)
- [6. Python 环境检查](#6-python-环境检查)
- [7. 系统资源限制](#7-系统资源限制)
- [8. 依赖服务检查](#8-依赖服务检查)

---

## 1. 快速检查脚本

### 1.1 一键检查脚本

**创建文件**: `app/tests/diagnostics_check_server.sh`

```bash
#!/bin/bash

# 视频上传环境检查脚本
# 用法: bash diagnostics_check_server.sh

set -e

echo "========================================="
echo "  视频上传环境诊断工具 v1.0"
echo "  开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

check_pass() {
    echo -e "${GREEN}[✓]${NC} $1"
}

check_fail() {
    echo -e "${RED}[✗]${NC} $1"
}

check_warn() {
    echo -e "${YELLOW}[!]${NC} $1"
}

# ==================== 1. 文件系统检查 ====================
echo ">>> 1. 文件系统检查"
echo ""

# 检查 /tmp 目录
echo "1.1 检查 /tmp 目录"
if [ -d "/tmp" ]; then
    check_pass "/tmp 目录存在"
    
    # 检查权限
    if [ -w "/tmp" ]; then
        check_pass "/tmp 目录可写"
    else
        check_fail "/tmp 目录不可写 (权限问题)"
    fi
    
    # 检查磁盘空间
    tmp_available=$(df -BG /tmp | awk 'NR==2 {print $4}' | sed 's/G//')
    if [ "$tmp_available" -gt 10 ]; then
        check_pass "/tmp 可用空间: ${tmp_available}GB (充足)"
    elif [ "$tmp_available" -gt 5 ]; then
        check_warn "/tmp 可用空间: ${tmp_available}GB (建议清理)"
    else
        check_fail "/tmp 可用空间: ${tmp_available}GB (不足,需清理)"
    fi
    
    # 检查 inode 使用率
    tmp_inode_use=$(df -i /tmp | awk 'NR==2 {print $5}' | sed 's/%//')
    if [ "$tmp_inode_use" -lt 80 ]; then
        check_pass "/tmp inode 使用率: ${tmp_inode_use}% (正常)"
    else
        check_warn "/tmp inode 使用率: ${tmp_inode_use}% (过高)"
    fi
else
    check_fail "/tmp 目录不存在"
fi

# 检查项目临时目录
echo ""
echo "1.2 检查项目临时目录"
TEMP_DIR="/tmp/aliyun_video_service"
if [ -d "$TEMP_DIR" ]; then
    check_pass "项目临时目录存在: $TEMP_DIR"
    
    # 检查权限
    if [ -w "$TEMP_DIR" ]; then
        check_pass "项目临时目录可写"
    else
        check_fail "项目临时目录不可写"
    fi
    
    # 检查残留文件
    file_count=$(find "$TEMP_DIR" -type f | wc -l)
    if [ "$file_count" -gt 50 ]; then
        check_warn "残留文件过多: $file_count 个 (建议清理)"
    else
        check_pass "残留文件数量: $file_count (正常)"
    fi
else
    check_warn "项目临时目录不存在,将自动创建: $TEMP_DIR"
    mkdir -p "$TEMP_DIR" 2>/dev/null && check_pass "临时目录创建成功" || check_fail "临时目录创建失败"
fi

# ==================== 2. Web 服务器检查 ====================
echo ""
echo ">>> 2. Web 服务器检查"
echo ""

# 检查 Nginx
echo "2.1 检查 Nginx"
if command -v nginx &> /dev/null; then
    check_pass "Nginx 已安装: $(nginx -v 2>&1 | grep -oP 'nginx/\K[0-9.]+')"
    
    # 检查 Nginx 运行状态
    if systemctl is-active --quiet nginx; then
        check_pass "Nginx 服务运行中"
    else
        check_warn "Nginx 服务未运行"
    fi
    
    # 检查关键配置
    echo ""
    echo "  检查 Nginx 配置..."
    if nginx -t &> /dev/null; then
        check_pass "Nginx 配置语法正确"
        
        # 提取 client_max_body_size
        max_body_size=$(nginx -T 2>/dev/null | grep -oP 'client_max_body_size\s+\K[0-9]+[a-zA-Z]+' | head -1)
        if [ -n "$max_body_size" ]; then
            check_pass "client_max_body_size = $max_body_size"
            
            # 转换为 MB 进行比较
            size_mb=$(echo "$max_body_size" | sed 's/[^0-9]*//g')
            unit=$(echo "$max_body_size" | sed 's/[0-9]*//g' | tr '[:lower:]' '[:upper:]')
            
            if [ "$unit" = "G" ]; then
                size_mb=$((size_mb * 1024))
            fi
            
            if [ "$size_mb" -ge 500 ]; then
                check_pass "文件大小限制充足 (>= 500MB)"
            else
                check_warn "文件大小限制较小 (<500MB), 建议调整为 1G"
            fi
        else
            check_warn "未找到 client_max_body_size 配置 (使用默认 1MB)"
        fi
        
        # 检查超时配置
        proxy_timeout=$(nginx -T 2>/dev/null | grep -oP 'proxy_read_timeout\s+\K[0-9]+' | head -1)
        if [ -n "$proxy_timeout" ]; then
            if [ "$proxy_timeout" -ge 300 ]; then
                check_pass "proxy_read_timeout = ${proxy_timeout}s (充足)"
            else
                check_warn "proxy_read_timeout = ${proxy_timeout}s (建议 >= 300s)"
            fi
        else
            check_warn "未配置 proxy_read_timeout (使用默认 60s)"
        fi
    else
        check_fail "Nginx 配置存在错误"
    fi
else
    check_warn "Nginx 未安装 (如使用直连则正常)"
fi

# ==================== 3. FastAPI/Uvicorn 检查 ====================
echo ""
echo ">>> 3. FastAPI/Uvicorn 检查"
echo ""

# 检查 FastAPI 服务
echo "3.1 检查 FastAPI 服务"
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health | grep -q "200"; then
    check_pass "FastAPI 服务运行正常 (http://localhost:8000)"
else
    check_fail "FastAPI 服务不可访问 (http://localhost:8000)"
fi

# 检查服务状态端点
echo ""
echo "3.2 检查服务状态"
service_status=$(curl -s http://localhost:8000/video/status 2>/dev/null || echo "{}")
if echo "$service_status" | jq . &> /dev/null; then
    check_pass "服务状态端点可访问"
    
    # 检查各服务可用性
    oss_available=$(echo "$service_status" | jq -r '.services.oss_service // false')
    speech_available=$(echo "$service_status" | jq -r '.services.speech_service // false')
    llm_available=$(echo "$service_status" | jq -r '.services.llm_service // false')
    
    [ "$oss_available" = "true" ] && check_pass "OSS 服务可用" || check_warn "OSS 服务不可用"
    [ "$speech_available" = "true" ] && check_pass "语音服务可用" || check_warn "语音服务不可用"
    [ "$llm_available" = "true" ] && check_pass "LLM 服务可用" || check_warn "LLM 服务不可用"
else
    check_warn "无法解析服务状态 (JSON 格式错误)"
fi

# ==================== 4. 网络连接检查 ====================
echo ""
echo ">>> 4. 网络连接检查"
echo ""

# 检查到 OSS 的连接
echo "4.1 检查阿里云 OSS 连接"
if curl -I -s --connect-timeout 5 https://oss-cn-beijing.aliyuncs.com &> /dev/null; then
    check_pass "OSS Endpoint 可达: oss-cn-beijing.aliyuncs.com"
else
    check_fail "OSS Endpoint 不可达 (网络问题或防火墙)"
fi

# 检查到 DashScope 的连接
echo ""
echo "4.2 检查 DashScope API 连接"
if curl -I -s --connect-timeout 5 https://dashscope.aliyuncs.com &> /dev/null; then
    check_pass "DashScope API 可达"
else
    check_fail "DashScope API 不可达"
fi

# 检查代理配置
echo ""
echo "4.3 检查网络代理"
if [ -n "$http_proxy" ] || [ -n "$https_proxy" ]; then
    check_warn "检测到代理配置:"
    [ -n "$http_proxy" ] && echo "  http_proxy = $http_proxy"
    [ -n "$https_proxy" ] && echo "  https_proxy = $https_proxy"
    [ -n "$all_proxy" ] && echo "  all_proxy = $all_proxy"
    
    # 测试代理可用性
    if curl -x "$http_proxy" -I -s --connect-timeout 5 https://www.google.com &> /dev/null; then
        check_pass "代理服务可用"
    else
        check_fail "代理服务不可用"
    fi
else
    check_pass "未配置代理 (直连模式)"
fi

# ==================== 5. Python 环境检查 ====================
echo ""
echo ">>> 5. Python 环境检查"
echo ""

# 检查 Python 版本
echo "5.1 检查 Python 版本"
python_version=$(python3 --version 2>&1 | grep -oP 'Python \K[0-9.]+')
if [ -n "$python_version" ]; then
    check_pass "Python 版本: $python_version"
    
    # 检查版本是否 >= 3.9
    major=$(echo "$python_version" | cut -d. -f1)
    minor=$(echo "$python_version" | cut -d. -f2)
    if [ "$major" -ge 3 ] && [ "$minor" -ge 9 ]; then
        check_pass "Python 版本满足要求 (>= 3.9)"
    else
        check_fail "Python 版本过低 (需要 >= 3.9)"
    fi
else
    check_fail "Python 未安装"
fi

# 检查关键依赖
echo ""
echo "5.2 检查关键 Python 依赖"
deps=("fastapi" "uvicorn" "oss2" "yt-dlp" "dashscope" "supabase")
for dep in "${deps[@]}"; do
    if python3 -c "import $dep" 2>/dev/null; then
        version=$(python3 -c "import $dep; print(getattr($dep, '__version__', 'unknown'))" 2>/dev/null)
        check_pass "$dep = $version"
    else
        check_fail "$dep 未安装"
    fi
done

# 检查系统工具
echo ""
echo "5.3 检查系统工具"
tools=("ffmpeg" "jq" "curl")
for tool in "${tools[@]}"; do
    if command -v "$tool" &> /dev/null; then
        version=$($tool --version 2>&1 | head -1)
        check_pass "$tool 已安装"
    else
        check_fail "$tool 未安装"
    fi
done

# ==================== 6. 系统资源限制检查 ====================
echo ""
echo ">>> 6. 系统资源限制检查"
echo ""

# 检查文件描述符限制
echo "6.1 检查文件描述符限制"
ulimit_n=$(ulimit -n)
if [ "$ulimit_n" -ge 10000 ]; then
    check_pass "文件描述符限制: $ulimit_n (充足)"
elif [ "$ulimit_n" -ge 1024 ]; then
    check_warn "文件描述符限制: $ulimit_n (建议 >= 10000)"
else
    check_fail "文件描述符限制: $ulimit_n (过低)"
fi

# 检查进程数限制
echo ""
echo "6.2 检查进程数限制"
ulimit_u=$(ulimit -u)
if [ "$ulimit_u" -ge 4096 ]; then
    check_pass "进程数限制: $ulimit_u (充足)"
else
    check_warn "进程数限制: $ulimit_u (建议 >= 4096)"
fi

# 检查内存使用
echo ""
echo "6.3 检查内存使用"
mem_total=$(free -m | awk 'NR==2 {print $2}')
mem_available=$(free -m | awk 'NR==2 {print $7}')
mem_percent=$((100 - mem_available * 100 / mem_total))

if [ "$mem_percent" -lt 80 ]; then
    check_pass "内存使用率: ${mem_percent}% (正常)"
else
    check_warn "内存使用率: ${mem_percent}% (较高)"
fi

# ==================== 7. 环境变量检查 ====================
echo ""
echo ">>> 7. 环境变量检查"
echo ""

# 检查 .env 文件
echo "7.1 检查配置文件"
if [ -f ".env" ]; then
    check_pass ".env 文件存在"
    
    # 检查关键配置项
    required_vars=("OSS_ACCESS_KEY_ID" "OSS_ACCESS_KEY_SECRET" "OSS_BUCKET" "OSS_ENDPOINT" "QWEN_API_KEY")
    for var in "${required_vars[@]}"; do
        if grep -q "^${var}=" .env; then
            check_pass "$var 已配置"
        else
            check_fail "$var 未配置"
        fi
    done
else
    check_fail ".env 文件不存在"
fi

# ==================== 总结 ====================
echo ""
echo "========================================="
echo "  检查完成: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================="
echo ""
echo "建议:"
echo "1. 修复所有 [✗] 标记的问题"
echo "2. 关注 [!] 标记的警告项"
echo "3. 定期运行此脚本进行健康检查"
echo ""
```

**使用方法**:
```bash
cd /root/my_youtube_summarizer
bash app/tests/diagnostics_check_server.sh
```

---

## 2. 文件系统检查

### 2.1 临时目录配置

**检查项 1: /tmp 目录权限**
```bash
# 检查权限
ls -ld /tmp
# 期望输出: drwxrwxrwt (1777)

# 测试写入
echo "test" > /tmp/test_write && rm /tmp/test_write && echo "✅ 可写" || echo "❌ 不可写"
```

**检查项 2: 磁盘空间**
```bash
# 检查磁盘空间
df -h /tmp

# 期望:
# Filesystem      Size  Used Avail Use% Mounted on
# /dev/sda1        50G   20G   28G  42% /

# 建议: Avail >= 10G
```

**检查项 3: inode 使用率**
```bash
# 检查 inode
df -i /tmp

# 期望: IUse% < 80%
```

**问题修复**:
```bash
# 清理临时文件
find /tmp -type f -mtime +7 -delete  # 删除 7 天前的文件
find /tmp -type d -empty -delete      # 删除空目录

# 如果 /tmp 空间不足,可挂载 tmpfs
sudo mount -t tmpfs -o size=20G tmpfs /tmp
```

### 2.2 项目临时目录

**默认路径**: `/tmp/aliyun_video_service/session_{video_id}`

**检查脚本**:
```bash
#!/bin/bash

TEMP_DIR="/tmp/aliyun_video_service"

# 创建目录
mkdir -p "$TEMP_DIR"

# 检查权限
if [ -w "$TEMP_DIR" ]; then
    echo "✅ 目录可写"
else
    echo "❌ 目录不可写,修复权限:"
    chmod 777 "$TEMP_DIR"
fi

# 检查残留文件
echo "残留文件统计:"
find "$TEMP_DIR" -type f -printf '%T@ %p\n' | sort -n | awk '{print strftime("%Y-%m-%d %H:%M:%S", $1), $2}'

# 清理超过 1 小时的文件
find "$TEMP_DIR" -type f -mmin +60 -delete
echo "✅ 已清理超过 1 小时的临时文件"
```

**定时清理任务** (crontab):
```bash
# 每小时清理一次
0 * * * * find /tmp/aliyun_video_service -type f -mmin +60 -delete

# 每天凌晨 3 点清理所有文件
0 3 * * * rm -rf /tmp/aliyun_video_service/*
```

---

## 3. Web 服务器配置

### 3.1 Nginx 配置检查

**配置文件位置**: `/etc/nginx/sites-available/video-analysis`

**推荐配置**:
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    # ========== 关键配置1: 文件大小限制 ==========
    client_max_body_size 1G;          # 允许上传 1GB 文件
    client_body_buffer_size 10M;       # 缓冲区 10MB
    client_body_timeout 300s;          # 客户端上传超时
    
    # ========== 关键配置2: 超时设置 ==========
    proxy_connect_timeout 600s;        # 连接超时
    proxy_send_timeout 600s;           # 发送超时
    proxy_read_timeout 600s;           # 读取超时
    send_timeout 600s;                 # 响应超时
    
    # ========== 关键配置3: 缓冲区设置 ==========
    proxy_buffering off;               # 禁用代理缓冲 (流式上传)
    proxy_request_buffering off;       # 禁用请求缓冲
    
    # ========== 关键配置4: 临时文件路径 ==========
    client_body_temp_path /var/nginx_temp;  # 确保有足够空间
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # 日志配置
    access_log /var/log/nginx/video-analysis-access.log;
    error_log /var/log/nginx/video-analysis-error.log warn;
}
```

**验证配置**:
```bash
# 测试配置语法
nginx -t

# 重新加载配置
nginx -s reload

# 查看实际配置
nginx -T | grep -A 5 "client_max_body_size\|proxy_read_timeout"
```

**测试上传限制**:
```bash
# 生成 100MB 测试文件
dd if=/dev/zero of=/tmp/test_100mb.bin bs=1M count=100

# 测试上传
curl -X POST http://your-domain.com/video/process \
  -F "video_file=@/tmp/test_100mb.bin" \
  -v

# 期望: 返回 200 或 500 (处理失败),而非 413 (文件过大)
```

### 3.2 Apache 配置检查 (如使用)

**配置文件**: `/etc/apache2/sites-available/video-analysis.conf`

```apache
<VirtualHost *:80>
    ServerName your-domain.com
    
    # 文件大小限制 (1GB)
    LimitRequestBody 1073741824
    
    # 超时设置
    Timeout 600
    ProxyTimeout 600
    
    # 反向代理
    ProxyPass / http://localhost:8000/
    ProxyPassReverse / http://localhost:8000/
    
    # 日志
    ErrorLog ${APACHE_LOG_DIR}/video-analysis-error.log
    CustomLog ${APACHE_LOG_DIR}/video-analysis-access.log combined
</VirtualHost>
```

---

## 4. FastAPI/Uvicorn 配置

### 4.1 Uvicorn 启动参数

**推荐启动命令**:
```bash
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4 \              # 工作进程数 (CPU 核心数)
  --timeout-keep-alive 600 \  # Keep-Alive 超时
  --limit-concurrency 100 \   # 最大并发连接数
  --limit-max-requests 10000 \# 单进程最大请求数 (防内存泄漏)
  --reload                    # 开发模式热重载
```

**生产环境配置** (`systemd` 服务):

创建 `/etc/systemd/system/video-analysis.service`:
```ini
[Unit]
Description=Video Analysis FastAPI Service
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/root/my_youtube_summarizer/backend
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=/root/my_youtube_summarizer/.env
ExecStart=/usr/local/bin/uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4 \
  --timeout-keep-alive 600 \
  --limit-concurrency 100

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**启动服务**:
```bash
sudo systemctl daemon-reload
sudo systemctl enable video-analysis
sudo systemctl start video-analysis
sudo systemctl status video-analysis
```

### 4.2 健康检查

**检查服务运行状态**:
```bash
# 检查端口监听
netstat -tuln | grep 8000

# 检查进程
ps aux | grep uvicorn

# 测试 API 可达性
curl http://localhost:8000/health
# 期望: {"status": "healthy"}

# 测试服务状态
curl http://localhost:8000/video/status | jq .
```

---

## 5. 网络连接检查

### 5.1 OSS 连接测试

**测试脚本**:
```bash
#!/bin/bash

echo "测试阿里云 OSS 连接..."

# 测试 1: Ping Endpoint
echo "1. 测试网络可达性:"
ping -c 3 oss-cn-beijing.aliyuncs.com

# 测试 2: HTTP 连接
echo ""
echo "2. 测试 HTTP 连接:"
curl -I https://oss-cn-beijing.aliyuncs.com

# 测试 3: Python SDK 连接
echo ""
echo "3. 测试 Python SDK:"
python3 << EOF
import oss2
from dotenv import load_dotenv
import os

load_dotenv('/root/my_youtube_summarizer/.env')

access_key_id = os.getenv('OSS_ACCESS_KEY_ID')
access_key_secret = os.getenv('OSS_ACCESS_KEY_SECRET')
endpoint = os.getenv('OSS_ENDPOINT', 'oss-cn-beijing.aliyuncs.com')
bucket_name = os.getenv('OSS_BUCKET')

try:
    auth = oss2.Auth(access_key_id, access_key_secret)
    bucket = oss2.Bucket(auth, endpoint, bucket_name)
    
    # 测试 Bucket 信息
    info = bucket.get_bucket_info()
    print(f"✅ OSS 连接成功")
    print(f"  Bucket: {info.name}")
    print(f"  Location: {info.location}")
    print(f"  Storage Class: {info.storage_class}")
except Exception as e:
    print(f"❌ OSS 连接失败: {e}")
EOF
```

### 5.2 代理配置检查

**检查代理环境变量**:
```bash
echo "HTTP Proxy: $http_proxy"
echo "HTTPS Proxy: $https_proxy"
echo "All Proxy: $all_proxy"
echo "No Proxy: $no_proxy"
```

**测试代理连接**:
```bash
# 测试代理是否工作
curl -x http://127.0.0.1:33210 -I https://www.google.com

# 测试直连 vs 代理速度对比
echo "直连速度:"
time curl -I https://oss-cn-beijing.aliyuncs.com

echo "代理速度:"
time curl -x http://127.0.0.1:33210 -I https://oss-cn-beijing.aliyuncs.com
```

**代理故障排查**:
```bash
# 检查代理服务是否运行
netstat -tuln | grep 33210

# 检查代理日志 (V2Ray 示例)
tail -f /var/log/v2ray/access.log
tail -f /var/log/v2ray/error.log
```

---

## 6. Python 环境检查

### 6.1 依赖版本验证

**生成依赖清单**:
```bash
cd /root/my_youtube_summarizer/backend
pip freeze > installed_packages.txt
```

**对比 requirements.txt**:
```bash
# 检查缺失的包
comm -23 <(sort requirements.txt) <(pip freeze | cut -d= -f1 | sort)

# 检查版本不匹配
pip check
```

**关键依赖版本要求**:
```txt
fastapi>=0.104.0
uvicorn>=0.24.0
oss2>=2.18.0
yt-dlp>=2023.11.0
dashscope>=1.14.0
supabase>=2.0.0
python-multipart>=0.0.6  # 文件上传必需
```

### 6.2 系统依赖检查

**ffmpeg 检查**:
```bash
# 检查安装
ffmpeg -version

# 检查支持的编码格式
ffmpeg -codecs | grep -E "h264|h265|vp9"

# 检查音频提取
ffmpeg -i test_video.mp4 -vn -acodec pcm_s16le test_audio.wav
```

**PySceneDetect 检查**:
```bash
# 检查安装
python3 -c "import scenedetect; print(scenedetect.__version__)"

# 测试场景检测
python3 << EOF
from scenedetect import detect, AdaptiveDetector
scenes = detect('test_video.mp4', AdaptiveDetector())
print(f"检测到 {len(scenes)} 个场景")
EOF
```

---

## 7. 系统资源限制

### 7.1 修改 ulimit 限制

**临时修改** (当前会话):
```bash
ulimit -n 10000   # 文件描述符
ulimit -u 4096    # 进程数
```

**永久修改** (`/etc/security/limits.conf`):
```bash
# 添加以下行
* soft nofile 10000
* hard nofile 100000
* soft nproc 4096
* hard nproc 8192
```

**验证**:
```bash
# 重新登录后检查
ulimit -n
ulimit -u
```

### 7.2 监控资源使用

**实时监控脚本**:
```bash
#!/bin/bash

echo "实时资源监控 (每 5 秒刷新)"
while true; do
    clear
    echo "========== 系统资源监控 =========="
    echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo ""
    
    echo ">>> CPU 使用率:"
    mpstat 1 1 | awk '/Average/ {print "  CPU Idle: " $NF "%"}'
    
    echo ""
    echo ">>> 内存使用:"
    free -h | awk 'NR==2 {printf "  已用: %s / 总计: %s (%.1f%%)\n", $3, $2, ($3/$2)*100}'
    
    echo ""
    echo ">>> 磁盘 I/O:"
    iostat -x 1 1 | awk '/^[s|v|h]d/ {printf "  %s: %util=%.1f%%\n", $1, $NF}'
    
    echo ""
    echo ">>> 网络连接:"
    netstat -an | grep -E "8000|33210" | awk '{print "  " $0}'
    
    echo ""
    echo ">>> FastAPI 进程:"
    ps aux | grep uvicorn | grep -v grep | awk '{printf "  PID=%s CPU=%.1f%% MEM=%.1f%%\n", $2, $3, $4}'
    
    sleep 5
done
```

---

## 8. 依赖服务检查

### 8.1 Supabase 连接测试

```bash
python3 << EOF
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv('/root/my_youtube_summarizer/.env')

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')

try:
    client = create_client(url, key)
    
    # 测试查询
    response = client.table('videos').select('*').limit(1).execute()
    print("✅ Supabase 连接成功")
except Exception as e:
    print(f"❌ Supabase 连接失败: {e}")
EOF
```

### 8.2 DashScope API 测试

```bash
python3 << EOF
import dashscope
import os
from dotenv import load_dotenv

load_dotenv('/root/my_youtube_summarizer/.env')

dashscope.api_key = os.getenv('QWEN_API_KEY')

try:
    # 测试简单请求
    from dashscope.audio.asr import Transcription
    print("✅ DashScope SDK 配置正确")
except Exception as e:
    print(f"❌ DashScope 配置失败: {e}")
EOF
```

---

## 总结

### 快速检查清单

- [ ] `/tmp` 目录空间 > 10GB
- [ ] Nginx `client_max_body_size` >= 1G
- [ ] Nginx `proxy_read_timeout` >= 300s
- [ ] FastAPI 服务运行正常 (curl http://localhost:8000/health)
- [ ] OSS 网络可达 (curl -I https://oss-cn-beijing.aliyuncs.com)
- [ ] Python 版本 >= 3.9
- [ ] 所有依赖已安装 (pip check)
- [ ] ffmpeg 已安装
- [ ] ulimit -n >= 10000
- [ ] 环境变量配置完整 (.env 文件)

**建议频率**: 每周运行一次完整检查

---

**文档版本**: v1.0  
**最后更新**: 2025-01-15  
**维护者**: 系统运维组
