# 最小化测试用例设计

> **文档目标**: 提供系统化的测试用例,帮助隔离环境因素,快速定位偶发性上传失败的根本原因

---

## 📋 目录

- [1. 测试策略](#1-测试策略)
- [2. 基础功能测试](#2-基础功能测试)
- [3. 隔离测试](#3-隔离测试)
- [4. 边界条件测试](#4-边界条件测试)
- [5. 环境对比测试](#5-环境对比测试)
- [6. 压力测试与并发测试](#6-压力测试与并发测试)
- [7. 自动化测试脚本](#7-自动化测试脚本)

---

## 1. 测试策略

### 1.1 测试金字塔

```
         /\
        /  \  E2E 测试
       /----\  (少量,慢,昂贵)
      /      \
     /--------\ 集成测试
    /          \ (适量,中速)
   /------------\
  /--------------\ 单元测试
 /________________\ (大量,快速,便宜)
```

**本文档重点**: 集成测试和 E2E 测试,用于诊断生产环境问题。

### 1.2 测试原则

#### 原则 1: 最小化变量
每次测试只改变一个变量,便于定位问题根因。

**示例**:
- 测试 1: 10MB 文件 + 本地环境 + 无代理
- 测试 2: 10MB 文件 + 服务器环境 + 无代理 (变量: 环境)
- 测试 3: 10MB 文件 + 服务器环境 + 有代理 (变量: 代理)

#### 原则 2: 可重复性
所有测试必须可重复执行,使用固定的测试文件。

#### 原则 3: 详细记录
记录每次测试的完整环境信息和结果。

---

## 2. 基础功能测试

### 2.1 小文件上传测试 (< 10MB)

**目的**: 验证基础上传功能是否正常。

**测试脚本**: `app/tests/test_small_file_upload.sh`

```bash
#!/bin/bash

# 小文件上传测试
# 测试目标: 验证基础上传功能

TEST_NAME="小文件上传测试"
API_BASE="http://localhost:8000"
TEST_FILE="/tmp/test_small_video.mp4"
LOG_FILE="test_results_$(date +%Y%m%d_%H%M%S).log"

echo "========================================" | tee -a "$LOG_FILE"
echo "$TEST_NAME" | tee -a "$LOG_FILE"
echo "开始时间: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# 步骤 1: 生成测试文件 (5MB)
echo ">>> 步骤 1: 生成 5MB 测试文件" | tee -a "$LOG_FILE"
ffmpeg -f lavfi -i color=c=blue:s=640x480:d=10 \
  -vf "drawtext=text='Test Video %{pts\:hms}':fontsize=30:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2" \
  -c:v libx264 -pix_fmt yuv420p -y "$TEST_FILE" &>> "$LOG_FILE"

FILE_SIZE=$(stat -f%z "$TEST_FILE" 2>/dev/null || stat -c%s "$TEST_FILE")
echo "✓ 测试文件已生成: $TEST_FILE ($(numfmt --to=iec-i --suffix=B $FILE_SIZE))" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# 步骤 2: 执行上传
echo ">>> 步骤 2: 执行上传" | tee -a "$LOG_FILE"
START_TIME=$(date +%s)

curl -X POST "$API_BASE/video/process" \
  -F "video_file=@$TEST_FILE" \
  -H "Content-Type: multipart/form-data" \
  -w "\nHTTP Status: %{http_code}\nTime Total: %{time_total}s\n" \
  -o response.json \
  -v 2>&1 | tee -a "$LOG_FILE"

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo "" | tee -a "$LOG_FILE"
echo "✓ 上传完成,耗时: ${DURATION}s" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# 步骤 3: 验证响应
echo ">>> 步骤 3: 验证响应" | tee -a "$LOG_FILE"
if [ -f response.json ]; then
    echo "响应内容:" | tee -a "$LOG_FILE"
    cat response.json | jq '.' | tee -a "$LOG_FILE"
    
    STATUS=$(cat response.json | jq -r '.status')
    if [ "$STATUS" = "success" ]; then
        echo "" | tee -a "$LOG_FILE"
        echo "✅ 测试通过: 上传成功" | tee -a "$LOG_FILE"
        VIDEO_ID=$(cat response.json | jq -r '.video_id')
        echo "  Video ID: $VIDEO_ID" | tee -a "$LOG_FILE"
    else
        echo "" | tee -a "$LOG_FILE"
        echo "❌ 测试失败: 上传失败" | tee -a "$LOG_FILE"
        ERROR=$(cat response.json | jq -r '.error // "unknown"')
        echo "  错误: $ERROR" | tee -a "$LOG_FILE"
    fi
else
    echo "❌ 测试失败: 无响应" | tee -a "$LOG_FILE"
fi

# 清理
rm -f "$TEST_FILE" response.json

echo "" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"
echo "测试结束: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_FILE"
echo "日志文件: $LOG_FILE" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"
```

**执行**:
```bash
cd /root/my_youtube_summarizer/backend
bash app/tests/test_small_file_upload.sh
```

**期望结果**:
- HTTP 状态码: 200
- `status`: "success"
- 响应时间: < 30s

---

### 2.2 中等文件上传测试 (10-100MB)

**测试脚本**: `app/tests/test_medium_file_upload.sh`

```bash
#!/bin/bash

TEST_NAME="中等文件上传测试"
API_BASE="http://localhost:8000"
TEST_FILE="/tmp/test_medium_video.mp4"
LOG_FILE="test_results_medium_$(date +%Y%m%d_%H%M%S).log"

echo "========================================" | tee -a "$LOG_FILE"
echo "$TEST_NAME" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# 生成 50MB 测试文件
echo ">>> 生成 50MB 测试文件" | tee -a "$LOG_FILE"
ffmpeg -f lavfi -i color=c=green:s=1280x720:d=60 \
  -vf "drawtext=text='Medium Test %{pts\:hms}':fontsize=40:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2" \
  -c:v libx264 -preset ultrafast -b:v 6M -pix_fmt yuv420p -y "$TEST_FILE" &>> "$LOG_FILE"

FILE_SIZE=$(stat -f%z "$TEST_FILE" 2>/dev/null || stat -c%s "$TEST_FILE")
echo "✓ 文件大小: $(numfmt --to=iec-i --suffix=B $FILE_SIZE)" | tee -a "$LOG_FILE"

# 执行上传
echo "" | tee -a "$LOG_FILE"
echo ">>> 开始上传 (可能需要 1-2 分钟)" | tee -a "$LOG_FILE"

START_TIME=$(date +%s)

curl -X POST "$API_BASE/video/process" \
  -F "video_file=@$TEST_FILE" \
  --max-time 300 \
  -w "\nHTTP Status: %{http_code}\nTime Total: %{time_total}s\nSpeed Upload: %{speed_upload} bytes/sec\n" \
  -o response.json \
  2>&1 | tee -a "$LOG_FILE"

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo "" | tee -a "$LOG_FILE"
echo "✓ 耗时: ${DURATION}s" | tee -a "$LOG_FILE"

# 验证
if [ -f response.json ]; then
    cat response.json | jq '.' | tee -a "$LOG_FILE"
    STATUS=$(cat response.json | jq -r '.status')
    [ "$STATUS" = "success" ] && echo "✅ 测试通过" || echo "❌ 测试失败"
fi

rm -f "$TEST_FILE" response.json
```

---

### 2.3 大文件上传测试 (> 100MB)

**测试脚本**: `app/tests/test_large_file_upload.sh`

```bash
#!/bin/bash

TEST_NAME="大文件上传测试"
TEST_FILE="/tmp/test_large_video.mp4"
LOG_FILE="test_results_large_$(date +%Y%m%d_%H%M%S).log"

echo "========================================" | tee -a "$LOG_FILE"
echo "$TEST_NAME (200MB)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# 生成 200MB 文件
echo ">>> 生成 200MB 测试文件 (需要 2-3 分钟)" | tee -a "$LOG_FILE"
ffmpeg -f lavfi -i color=c=red:s=1920x1080:d=120 \
  -vf "drawtext=text='Large Test %{pts\:hms}':fontsize=60:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2" \
  -c:v libx264 -preset ultrafast -b:v 12M -pix_fmt yuv420p -y "$TEST_FILE" &>> "$LOG_FILE"

FILE_SIZE=$(stat -f%z "$TEST_FILE" 2>/dev/null || stat -c%s "$TEST_FILE")
echo "✓ 文件大小: $(numfmt --to=iec-i --suffix=B $FILE_SIZE)" | tee -a "$LOG_FILE"

# 检查磁盘空间
echo "" | tee -a "$LOG_FILE"
echo ">>> 检查磁盘空间" | tee -a "$LOG_FILE"
df -h /tmp | tee -a "$LOG_FILE"

# 执行上传 (延长超时)
echo "" | tee -a "$LOG_FILE"
echo ">>> 开始上传 (可能需要 3-5 分钟)" | tee -a "$LOG_FILE"

curl -X POST "http://localhost:8000/video/process" \
  -F "video_file=@$TEST_FILE" \
  --max-time 600 \
  -w "\nHTTP: %{http_code}\n耗时: %{time_total}s\n上传速度: %{speed_upload} bytes/s\n" \
  -o response.json \
  2>&1 | tee -a "$LOG_FILE"

# 验证
if [ -f response.json ]; then
    cat response.json | jq '.' | tee -a "$LOG_FILE"
fi

rm -f "$TEST_FILE" response.json

echo "" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"
echo "测试完成: $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"
```

---

## 3. 隔离测试

### 3.1 仅文件上传测试 (跳过 AI 处理)

**目的**: 隔离文件上传环节,排除 AI 处理影响。

**临时修改路由** (`backend/app/api/routes/video.py`):

```python
@router.post("/process_upload_only")
async def process_upload_only(
    video_file: UploadFile = File(...),
    request: Request = None
):
    """
    仅测试文件上传,跳过所有 AI 处理
    """
    request_id = str(uuid.uuid4())[:8]
    
    try:
        # 保存文件
        temp_dir = tempfile.gettempdir()
        video_path = os.path.join(temp_dir, f"{request_id}_{video_file.filename}")
        
        start_time = time.time()
        with open(video_path, "wb") as buffer:
            content = await video_file.read()
            buffer.write(content)
        save_duration = time.time() - start_time
        
        file_size = os.path.getsize(video_path)
        
        # 验证文件
        is_valid = os.path.exists(video_path) and file_size > 0
        
        # 清理
        os.remove(video_path)
        
        return {
            "status": "success",
            "request_id": request_id,
            "filename": video_file.filename,
            "file_size_bytes": file_size,
            "file_size_mb": round(file_size / 1024 / 1024, 2),
            "save_duration_seconds": round(save_duration, 2),
            "write_speed_mbps": round((file_size / 1024 / 1024) / save_duration, 2),
            "file_valid": is_valid
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }
```

**测试脚本**:
```bash
#!/bin/bash

# 测试纯文件上传 (无 AI 处理)

for i in {1..10}; do
    echo ">>> 测试 $i/10"
    
    curl -X POST http://localhost:8000/process_upload_only \
      -F "video_file=@test_video.mp4" \
      -s | jq '{status, file_size_mb, save_duration_seconds, write_speed_mbps}'
    
    sleep 2
done
```

**期望**:
- 10 次测试全部成功
- 如果此测试失败率高 → 问题在文件上传环节
- 如果此测试成功率高 → 问题在后续处理环节

---

### 3.2 OSS 上传独立测试

**测试脚本**: `app/tests/test_oss_upload_isolated.py`

```python
#!/usr/bin/env python3
"""
独立测试 OSS 上传功能
"""
import os
import time
import tempfile
from pathlib import Path
import sys

# 添加项目路径
sys.path.insert(0, '/root/my_youtube_summarizer/backend')

from app.services.oss_service import oss_service
from dotenv import load_dotenv

load_dotenv('/root/my_youtube_summarizer/.env')

def test_oss_upload():
    print("========================================")
    print("  OSS 上传独立测试")
    print("========================================\n")
    
    # 检查 OSS 服务可用性
    print(">>> 步骤 1: 检查 OSS 服务")
    if not oss_service.is_available():
        print("❌ OSS 服务不可用")
        return False
    print("✅ OSS 服务可用\n")
    
    # 生成测试文件
    print(">>> 步骤 2: 生成测试文件 (10MB)")
    test_file = "/tmp/test_oss_upload.bin"
    with open(test_file, 'wb') as f:
        f.write(os.urandom(10 * 1024 * 1024))  # 10MB 随机数据
    print(f"✅ 测试文件已生成: {test_file}\n")
    
    # 执行上传
    print(">>> 步骤 3: 上传到 OSS")
    video_id = "test_" + str(int(time.time()))
    
    start_time = time.time()
    
    try:
        # 同步调用异步方法
        import asyncio
        oss_url = asyncio.run(oss_service.upload_video(test_file, video_id))
        
        duration = time.time() - start_time
        
        if oss_url:
            print(f"✅ 上传成功")
            print(f"  OSS URL: {oss_url}")
            print(f"  耗时: {duration:.2f}s")
            print(f"  速度: {(10 / duration):.2f} MB/s\n")
            
            # 验证文件可访问
            print(">>> 步骤 4: 验证 OSS 文件可访问")
            import requests
            response = requests.head(oss_url, timeout=10)
            if response.status_code == 200:
                print(f"✅ 文件可访问 (HTTP {response.status_code})")
                return True
            else:
                print(f"⚠️ 文件不可访问 (HTTP {response.status_code})")
                return False
        else:
            print(f"❌ 上传失败 (返回 None)")
            print(f"  耗时: {duration:.2f}s")
            return False
            
    except Exception as e:
        print(f"❌ 上传异常: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # 清理
        if os.path.exists(test_file):
            os.remove(test_file)
            print("\n✓ 测试文件已清理")


if __name__ == "__main__":
    # 执行多次测试
    success_count = 0
    total_count = 5
    
    print(f"开始执行 {total_count} 次 OSS 上传测试\n")
    
    for i in range(1, total_count + 1):
        print(f"\n{'='*50}")
        print(f"  第 {i}/{total_count} 次测试")
        print(f"{'='*50}\n")
        
        if test_oss_upload():
            success_count += 1
        
        time.sleep(2)  # 间隔 2 秒
    
    print(f"\n{'='*50}")
    print(f"  测试汇总")
    print(f"{'='*50}")
    print(f"总测试次数: {total_count}")
    print(f"成功次数: {success_count}")
    print(f"失败次数: {total_count - success_count}")
    print(f"成功率: {(success_count / total_count * 100):.1f}%")
    
    if success_count == total_count:
        print("\n✅ 所有测试通过")
    elif success_count > 0:
        print(f"\n⚠️ 部分测试失败 (偶发性问题)")
    else:
        print("\n❌ 所有测试失败 (系统性问题)")
```

**执行**:
```bash
cd /root/my_youtube_summarizer/backend
python3 app/tests/test_oss_upload_isolated.py
```

---

## 4. 边界条件测试

### 4.1 特殊文件名测试

**测试脚本**:
```bash
#!/bin/bash

# 测试特殊文件名处理

TEST_FILES=(
    "test video.mp4"           # 空格
    "测试视频.mp4"             # 中文
    "test@video#2024.mp4"      # 特殊字符
    "very_long_filename_with_more_than_255_characters_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.mp4"  # 超长文件名
)

for filename in "${TEST_FILES[@]}"; do
    echo ">>> 测试文件名: $filename"
    
    # 生成测试文件
    ffmpeg -f lavfi -i color=c=blue:s=640x480:d=5 -y "$filename" &>/dev/null
    
    # 上传
    curl -X POST http://localhost:8000/video/process \
      -F "video_file=@$filename" \
      -s | jq '{status, error}'
    
    # 清理
    rm -f "$filename"
    
    echo ""
done
```

---

### 4.2 不同视频格式测试

**测试脚本**:
```bash
#!/bin/bash

# 测试不同视频格式

FORMATS=("mp4" "avi" "mov" "mkv" "flv" "webm")

for format in "${FORMATS[@]}"; do
    echo ">>> 测试格式: $format"
    
    test_file="test_video.$format"
    
    # 生成测试文件
    ffmpeg -f lavfi -i color=c=blue:s=640x480:d=5 \
      -c:v libx264 -y "$test_file" &>/dev/null
    
    # 上传
    result=$(curl -X POST http://localhost:8000/video/process \
      -F "video_file=@$test_file" \
      -s)
    
    status=$(echo "$result" | jq -r '.status')
    
    if [ "$status" = "success" ]; then
        echo "✅ 格式 $format 支持"
    else
        echo "❌ 格式 $format 不支持"
        echo "  错误: $(echo "$result" | jq -r '.error')"
    fi
    
    rm -f "$test_file"
    echo ""
done
```

---

### 4.3 网络模拟测试

**使用 tc (Traffic Control) 模拟网络条件**:

```bash
#!/bin/bash

# 需要 root 权限

# 模拟慢速网络 (1Mbps)
sudo tc qdisc add dev eth0 root tbf rate 1mbit burst 32kbit latency 400ms

# 执行上传测试
curl -X POST http://localhost:8000/video/process \
  -F "video_file=@test_video.mp4" \
  -w "Time: %{time_total}s\n"

# 恢复网络
sudo tc qdisc del dev eth0 root
```

**模拟丢包**:
```bash
# 模拟 5% 丢包率
sudo tc qdisc add dev eth0 root netem loss 5%

# 测试上传

# 恢复
sudo tc qdisc del dev eth0 root
```

---

## 5. 环境对比测试

### 5.1 本地 vs 服务器对比

**测试矩阵**:

| 环境 | 代理 | 文件大小 | 预期成功率 |
|------|------|---------|-----------|
| 本地 | 无 | 10MB | 100% |
| 本地 | 有 | 10MB | 95%+ |
| 服务器 | 无 | 10MB | 95%+ |
| 服务器 | 有 | 10MB | ? (待测试) |

**对比测试脚本**:
```bash
#!/bin/bash

# 环境对比测试

TEST_FILE="test_video.mp4"
ITERATIONS=20

# 生成测试文件
ffmpeg -f lavfi -i color=c=blue:s=640x480:d=10 -y "$TEST_FILE" &>/dev/null

# 测试函数
run_test() {
    local env_name=$1
    local use_proxy=$2
    local success=0
    
    echo ">>> 测试环境: $env_name (代理: $use_proxy)"
    
    for i in $(seq 1 $ITERATIONS); do
        # 设置代理
        if [ "$use_proxy" = "yes" ]; then
            export http_proxy=http://127.0.0.1:33210
            export https_proxy=http://127.0.0.1:33210
        else
            unset http_proxy
            unset https_proxy
        fi
        
        # 执行上传
        status=$(curl -X POST http://localhost:8000/video/process \
          -F "video_file=@$TEST_FILE" \
          -s --max-time 60 | jq -r '.status')
        
        if [ "$status" = "success" ]; then
            ((success++))
            echo "  [$i/$ITERATIONS] ✅"
        else
            echo "  [$i/$ITERATIONS] ❌"
        fi
        
        sleep 2
    done
    
    success_rate=$((success * 100 / ITERATIONS))
    echo "  成功率: $success_rate% ($success/$ITERATIONS)"
    echo ""
}

# 执行测试
run_test "本地环境" "no"
run_test "本地环境" "yes"

# 如果在服务器上,也测试服务器环境
if [ "$(hostname)" != "localhost" ]; then
    run_test "服务器环境" "no"
    run_test "服务器环境" "yes"
fi

# 清理
rm -f "$TEST_FILE"
```

---

## 6. 压力测试与并发测试

### 6.1 并发上传测试

**测试脚本**: `app/tests/test_concurrent_upload.sh`

```bash
#!/bin/bash

# 并发上传测试 (模拟偶发性失败场景)

CONCURRENT=10  # 并发数
TEST_FILE="test_video.mp4"
LOG_DIR="concurrent_test_logs"

mkdir -p "$LOG_DIR"

# 生成测试文件
echo ">>> 生成测试文件"
ffmpeg -f lavfi -i color=c=blue:s=640x480:d=10 -y "$TEST_FILE" &>/dev/null
echo "✓ 文件已生成"

# 单次上传函数
upload_once() {
    local id=$1
    local log_file="$LOG_DIR/upload_${id}.log"
    
    echo "[$id] 开始上传 $(date '+%H:%M:%S')" >> "$log_file"
    
    result=$(curl -X POST http://localhost:8000/video/process \
      -F "video_file=@$TEST_FILE" \
      -s --max-time 120 2>&1)
    
    status=$(echo "$result" | jq -r '.status' 2>/dev/null || echo "error")
    
    echo "[$id] 结果: $status $(date '+%H:%M:%S')" >> "$log_file"
    echo "$result" >> "$log_file"
    
    if [ "$status" = "success" ]; then
        echo "[$id] ✅"
    else
        echo "[$id] ❌"
    fi
}

export -f upload_once
export TEST_FILE
export LOG_DIR

echo ""
echo ">>> 启动 $CONCURRENT 个并发上传"
echo ""

# 并发执行
seq 1 $CONCURRENT | xargs -n 1 -P $CONCURRENT bash -c 'upload_once "$@"' _

echo ""
echo ">>> 统计结果"

success=$(grep -r "结果: success" "$LOG_DIR" | wc -l)
total=$CONCURRENT
success_rate=$((success * 100 / total))

echo "总数: $total"
echo "成功: $success"
echo "失败: $((total - success))"
echo "成功率: $success_rate%"

if [ $success_rate -lt 90 ]; then
    echo ""
    echo "⚠️ 成功率低于 90%,存在并发问题"
    echo "查看详细日志: $LOG_DIR/"
fi

# 清理
rm -f "$TEST_FILE"
```

---

### 6.2 持续压力测试

**测试脚本**: `app/tests/stress_test_upload.py`

```python
#!/usr/bin/env python3
"""
持续压力测试 - 模拟长时间运行环境
"""
import requests
import time
import threading
from datetime import datetime
import json

API_BASE = "http://localhost:8000"
TEST_FILE = "test_video.mp4"
DURATION_HOURS = 24  # 测试持续时间
INTERVAL_SECONDS = 60  # 每次上传间隔

results = {
    "success": 0,
    "failure": 0,
    "errors": []
}
results_lock = threading.Lock()

def upload_test():
    """执行单次上传测试"""
    timestamp = datetime.now().isoformat()
    
    try:
        with open(TEST_FILE, 'rb') as f:
            files = {'video_file': f}
            response = requests.post(
                f"{API_BASE}/video/process",
                files=files,
                timeout=120
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    with results_lock:
                        results['success'] += 1
                    print(f"[{timestamp}] ✅ 成功")
                else:
                    with results_lock:
                        results['failure'] += 1
                        results['errors'].append({
                            "time": timestamp,
                            "error": data.get('error', 'unknown')
                        })
                    print(f"[{timestamp}] ❌ 失败: {data.get('error')}")
            else:
                with results_lock:
                    results['failure'] += 1
                    results['errors'].append({
                        "time": timestamp,
                        "error": f"HTTP {response.status_code}"
                    })
                print(f"[{timestamp}] ❌ HTTP {response.status_code}")
                
    except Exception as e:
        with results_lock:
            results['failure'] += 1
            results['errors'].append({
                "time": timestamp,
                "error": str(e)
            })
        print(f"[{timestamp}] ❌ 异常: {e}")


def print_stats():
    """打印统计信息"""
    total = results['success'] + results['failure']
    if total > 0:
        success_rate = (results['success'] / total) * 100
        print(f"\n{'='*50}")
        print(f"统计 (截至 {datetime.now()})")
        print(f"{'='*50}")
        print(f"总请求: {total}")
        print(f"成功: {results['success']}")
        print(f"失败: {results['failure']}")
        print(f"成功率: {success_rate:.2f}%")
        
        if results['errors']:
            print(f"\n最近 5 个错误:")
            for error in results['errors'][-5:]:
                print(f"  [{error['time']}] {error['error']}")
        print(f"{'='*50}\n")


if __name__ == "__main__":
    print(f"开始压力测试 (持续 {DURATION_HOURS} 小时)")
    print(f"上传间隔: {INTERVAL_SECONDS} 秒")
    print(f"测试文件: {TEST_FILE}\n")
    
    start_time = time.time()
    end_time = start_time + (DURATION_HOURS * 3600)
    
    iteration = 0
    while time.time() < end_time:
        iteration += 1
        print(f"\n>>> 第 {iteration} 次上传 ({datetime.now()})")
        
        upload_test()
        
        # 每 10 次打印统计
        if iteration % 10 == 0:
            print_stats()
        
        time.sleep(INTERVAL_SECONDS)
    
    # 最终统计
    print("\n" + "="*50)
    print("  测试完成")
    print("="*50)
    print_stats()
    
    # 保存结果
    with open(f"stress_test_results_{int(start_time)}.json", 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n✓ 结果已保存到 stress_test_results_{int(start_time)}.json")
```

**执行**:
```bash
cd /root/my_youtube_summarizer/backend

# 生成测试文件
ffmpeg -f lavfi -i color=c=blue:s=640x480:d=10 -y test_video.mp4

# 后台运行 24 小时压力测试
nohup python3 app/tests/stress_test_upload.py > stress_test.log 2>&1 &

# 查看日志
tail -f stress_test.log
```

---

## 7. 自动化测试脚本

### 7.1 完整测试套件

**创建**: `app/tests/run_full_diagnostic_tests.sh`

```bash
#!/bin/bash

# 完整诊断测试套件
# 按顺序执行所有测试,生成汇总报告

REPORT_FILE="diagnostic_report_$(date +%Y%m%d_%H%M%S).txt"

echo "========================================" | tee "$REPORT_FILE"
echo "  视频上传诊断测试套件" | tee -a "$REPORT_FILE"
echo "  开始时间: $(date)" | tee -a "$REPORT_FILE"
echo "========================================" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

# 测试 1: 环境检查
echo ">>> 测试 1: 环境检查" | tee -a "$REPORT_FILE"
bash app/tests/diagnostics_check_server.sh >> "$REPORT_FILE" 2>&1
echo "" | tee -a "$REPORT_FILE"

# 测试 2: 小文件上传
echo ">>> 测试 2: 小文件上传" | tee -a "$REPORT_FILE"
bash app/tests/test_small_file_upload.sh >> "$REPORT_FILE" 2>&1
echo "" | tee -a "$REPORT_FILE"

# 测试 3: 中等文件上传
echo ">>> 测试 3: 中等文件上传" | tee -a "$REPORT_FILE"
bash app/tests/test_medium_file_upload.sh >> "$REPORT_FILE" 2>&1
echo "" | tee -a "$REPORT_FILE"

# 测试 4: OSS 独立测试
echo ">>> 测试 4: OSS 上传独立测试" | tee -a "$REPORT_FILE"
python3 app/tests/test_oss_upload_isolated.py >> "$REPORT_FILE" 2>&1
echo "" | tee -a "$REPORT_FILE"

# 测试 5: 并发测试
echo ">>> 测试 5: 并发上传测试 (10 并发)" | tee -a "$REPORT_FILE"
bash app/tests/test_concurrent_upload.sh >> "$REPORT_FILE" 2>&1
echo "" | tee -a "$REPORT_FILE"

echo "========================================" | tee -a "$REPORT_FILE"
echo "  测试完成: $(date)" | tee -a "$REPORT_FILE"
echo "  报告文件: $REPORT_FILE" | tee -a "$REPORT_FILE"
echo "========================================" | tee -a "$REPORT_FILE"
```

**执行**:
```bash
cd /root/my_youtube_summarizer/backend
bash app/tests/run_full_diagnostic_tests.sh
```

---

## 总结

### 测试优先级

**P0 - 必须执行**:
1. 环境检查 (diagnostics_check_server.sh)
2. 小文件上传测试
3. OSS 独立测试

**P1 - 强烈建议**:
4. 中等文件上传测试
5. 并发测试
6. 环境对比测试

**P2 - 可选**:
7. 大文件测试
8. 边界条件测试
9. 24 小时压力测试

### 问题定位路径

```
测试失败
├─ 小文件测试失败
│  ├─ 环境检查异常 → 修复环境配置
│  └─ 环境检查正常 → 查看日志,检查代码逻辑
│
├─ 小文件成功,中等/大文件失败
│  ├─ Nginx 超时 → 调整 timeout 配置
│  └─ 磁盘空间不足 → 清理临时文件
│
├─ 单次成功,并发失败
│  ├─ 文件名冲突 → 使用唯一文件名
│  └─ 资源竞争 → 增加系统资源限制
│
└─ OSS 独立测试失败
   ├─ 网络不通 → 检查代理/防火墙
   └─ 凭证错误 → 验证 AccessKey
```

---

**文档版本**: v1.0  
**最后更新**: 2025-01-15  
**维护者**: 测试工程组
