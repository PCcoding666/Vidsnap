# 诊断工具与监控

> **文档目标**: 提供实用的诊断工具、监控方案和故障定位方法,帮助快速解决偶发性上传失败问题

---

## 📋 目录

- [1. 手动诊断工具](#1-手动诊断工具)
- [2. 中间件增强与日志分析](#2-中间件增强与日志分析)
- [3. 性能分析工具](#3-性能分析工具)
- [4. 实时监控方案](#4-实时监控方案)
- [5. 故障定位决策树](#5-故障定位决策树)
- [6. 应急响应手册](#6-应急响应手册)

---

## 1. 手动诊断工具

### 1.1 curl 上传测试

**基础测试**:
```bash
#!/bin/bash

# 基础 curl 上传测试

TEST_FILE="test_video.mp4"
API_URL="http://localhost:8000/video/process"

# 生成测试文件
echo ">>> 生成测试文件"
ffmpeg -f lavfi -i color=c=blue:s=640x480:d=10 -y "$TEST_FILE" &>/dev/null
echo "✓ 文件已生成: $(ls -lh $TEST_FILE | awk '{print $5}')"

# 执行上传
echo ""
echo ">>> 开始上传"
curl -X POST "$API_URL" \
  -F "video_file=@$TEST_FILE" \
  -H "Content-Type: multipart/form-data" \
  -w "\n\n===== 性能指标 =====\nHTTP 状态码: %{http_code}\n总耗时: %{time_total}s\nDNS 解析: %{time_namelookup}s\nTCP 连接: %{time_connect}s\n开始传输: %{time_starttransfer}s\n上传速度: %{speed_upload} bytes/s\n下载速度: %{speed_download} bytes/s\n" \
  -o response.json \
  -v

# 显示响应
echo ""
echo "===== 响应内容 ====="
cat response.json | jq '.' || cat response.json

# 清理
rm -f "$TEST_FILE" response.json
```

---

**详细诊断版本**:
```bash
#!/bin/bash

# 详细 curl 诊断测试 (包含所有 HTTP 头和计时信息)

TEST_FILE="test_video.mp4"
API_URL="http://localhost:8000/video/process"
LOG_FILE="curl_diagnostic_$(date +%Y%m%d_%H%M%S).log"

echo "开始诊断测试: $(date)" | tee "$LOG_FILE"
echo "目标 API: $API_URL" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# 生成测试文件
ffmpeg -f lavfi -i color=c=blue:s=640x480:d=10 -y "$TEST_FILE" &>/dev/null

FILE_SIZE=$(stat -f%z "$TEST_FILE" 2>/dev/null || stat -c%s "$TEST_FILE")
echo "测试文件: $TEST_FILE ($(numfmt --to=iec-i --suffix=B $FILE_SIZE))" | tee -a "$LOG_FILE"

# 执行上传 (详细模式)
echo "" | tee -a "$LOG_FILE"
echo ">>> 开始上传" | tee -a "$LOG_FILE"

curl -X POST "$API_URL" \
  -F "video_file=@$TEST_FILE" \
  -H "X-Test-ID: curl-diagnostic-$(date +%s)" \
  -w "\n\n===== HTTP 性能指标 =====\nHTTP 状态码: %{http_code}\n重定向次数: %{num_redirects}\n内容类型: %{content_type}\n\n===== 时间统计 (秒) =====\nDNS 解析: %{time_namelookup}\nTCP 连接: %{time_connect}\nSSL 握手: %{time_appconnect}\n开始传输: %{time_starttransfer}\n总耗时: %{time_total}\n\n===== 数据传输 =====\n上传字节: %{size_upload}\n下载字节: %{size_download}\n上传速度: %{speed_upload} bytes/s\n下载速度: %{speed_download} bytes/s\n\n" \
  -o response.json \
  -v 2>&1 | tee -a "$LOG_FILE"

# 分析响应
echo "" | tee -a "$LOG_FILE"
echo "===== 响应分析 =====" | tee -a "$LOG_FILE"

if [ -f response.json ]; then
    # 美化 JSON 输出
    if cat response.json | jq . &>/dev/null; then
        cat response.json | jq '.' | tee -a "$LOG_FILE"
        
        # 提取关键信息
        STATUS=$(cat response.json | jq -r '.status')
        VIDEO_ID=$(cat response.json | jq -r '.video_id // "N/A"')
        ERROR=$(cat response.json | jq -r '.error // "N/A"')
        
        echo "" | tee -a "$LOG_FILE"
        echo "状态: $STATUS" | tee -a "$LOG_FILE"
        echo "Video ID: $VIDEO_ID" | tee -a "$LOG_FILE"
        [ "$ERROR" != "N/A" ] && echo "错误: $ERROR" | tee -a "$LOG_FILE"
    else
        echo "⚠️ 响应不是有效的 JSON" | tee -a "$LOG_FILE"
        cat response.json | tee -a "$LOG_FILE"
    fi
else
    echo "❌ 无响应文件" | tee -a "$LOG_FILE"
fi

# 清理
rm -f "$TEST_FILE" response.json

echo "" | tee -a "$LOG_FILE"
echo "诊断完成: $(date)" | tee -a "$LOG_FILE"
echo "日志文件: $LOG_FILE" | tee -a "$LOG_FILE"
```

**执行**:
```bash
cd /root/my_youtube_summarizer/backend
bash app/tests/curl_diagnostic.sh
```

---

### 1.2 Python requests 测试

**交互式测试脚本**:
```python
#!/usr/bin/env python3
"""
Python requests 上传测试 (更灵活的控制)
"""
import requests
import time
import sys
from pathlib import Path

API_BASE = "http://localhost:8000"
TEST_FILE = "test_video.mp4"

def upload_with_progress(file_path: str):
    """带进度显示的上传"""
    print(f">>> 上传文件: {file_path}")
    
    file_size = Path(file_path).stat().st_size
    print(f"文件大小: {file_size / 1024 / 1024:.2f} MB\n")
    
    # 创建自定义会话 (可配置超时、重试等)
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Python Diagnostic Tool/1.0'
    })
    
    start_time = time.time()
    
    try:
        with open(file_path, 'rb') as f:
            files = {'video_file': f}
            
            # 发送请求
            response = session.post(
                f"{API_BASE}/video/process",
                files=files,
                timeout=300,  # 5 分钟超时
                stream=True   # 流式响应
            )
            
            duration = time.time() - start_time
            
            print(f"\n✓ 请求完成")
            print(f"  HTTP 状态码: {response.status_code}")
            print(f"  耗时: {duration:.2f}s")
            print(f"  上传速度: {(file_size / 1024 / 1024) / duration:.2f} MB/s")
            print(f"  响应头:")
            for key, value in response.headers.items():
                if key.lower() in ['content-type', 'content-length', 'x-request-id']:
                    print(f"    {key}: {value}")
            
            # 解析响应
            print(f"\n  响应内容:")
            data = response.json()
            
            import json
            print(json.dumps(data, indent=2, ensure_ascii=False))
            
            return data.get('status') == 'success'
            
    except requests.exceptions.Timeout:
        print(f"\n❌ 超时错误 (> 300s)")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"\n❌ 连接错误: {e}")
        return False
    except Exception as e:
        print(f"\n❌ 异常: {type(e).__name__} - {e}")
        import traceback
        traceback.print_exc()
        return False


def test_service_health():
    """测试服务健康状态"""
    print(">>> 测试服务健康状态")
    
    try:
        response = requests.get(f"{API_BASE}/health", timeout=5)
        if response.status_code == 200:
            print(f"✅ 服务运行正常")
            return True
        else:
            print(f"⚠️ 服务异常 (HTTP {response.status_code})")
            return False
    except Exception as e:
        print(f"❌ 服务不可达: {e}")
        return False


def test_service_status():
    """测试各服务组件状态"""
    print("\n>>> 测试服务组件状态")
    
    try:
        response = requests.get(f"{API_BASE}/video/status", timeout=5)
        data = response.json()
        
        services = data.get('services', {})
        for service_name, available in services.items():
            status = "✅" if available else "❌"
            print(f"  {status} {service_name}: {'可用' if available else '不可用'}")
        
        return True
    except Exception as e:
        print(f"❌ 无法获取状态: {e}")
        return False


if __name__ == "__main__":
    print("="*50)
    print("  Python requests 上传诊断工具")
    print("="*50)
    print("")
    
    # 步骤 1: 测试服务健康
    if not test_service_health():
        print("\n⚠️ 服务不健康,终止测试")
        sys.exit(1)
    
    # 步骤 2: 测试服务组件
    test_service_status()
    
    # 步骤 3: 生成测试文件
    print(f"\n>>> 生成测试文件: {TEST_FILE}")
    import subprocess
    subprocess.run([
        'ffmpeg', '-f', 'lavfi', '-i', 'color=c=blue:s=640x480:d=10',
        '-y', TEST_FILE
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"✓ 文件已生成\n")
    
    # 步骤 4: 执行上传
    print("="*50)
    success = upload_with_progress(TEST_FILE)
    print("="*50)
    
    # 清理
    Path(TEST_FILE).unlink(missing_ok=True)
    
    # 结论
    print("")
    if success:
        print("✅ 诊断测试通过")
        sys.exit(0)
    else:
        print("❌ 诊断测试失败")
        sys.exit(1)
```

**执行**:
```bash
cd /root/my_youtube_summarizer/backend
python3 app/tests/python_upload_diagnostic.py
```

---

## 2. 中间件增强与日志分析

### 2.1 增强的请求日志中间件

**完整实现** (`backend/app/main.py`):

```python
import uuid
import time
import json
import traceback
from datetime import datetime
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class DiagnosticLoggingMiddleware(BaseHTTPMiddleware):
    """
    诊断日志中间件
    记录所有请求的详细信息,包括文件上传
    """
    
    async def dispatch(self, request: Request, call_next):
        # 生成请求 ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        request.state.request_id = request_id
        
        start_time = time.time()
        start_timestamp = datetime.utcnow().isoformat()
        
        # 记录请求信息
        request_log = {
            "request_id": request_id,
            "timestamp": start_timestamp,
            "method": request.method,
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "client_ip": request.client.host if request.client else "Unknown",
            "user_agent": request.headers.get("user-agent", "Unknown"),
            "content_type": request.headers.get("content-type", ""),
            "content_length": request.headers.get("content-length", "0"),
            "host": request.headers.get("host", ""),
            "referer": request.headers.get("referer", ""),
        }
        
        # 特殊处理文件上传
        if "multipart/form-data" in request_log["content_type"]:
            request_log["is_file_upload"] = True
            try:
                content_length = int(request_log["content_length"])
                request_log["file_size_mb"] = round(content_length / 1024 / 1024, 2)
            except:
                pass
        
        logger.info(f"[{request_id}] 📥 收到请求", extra=request_log)
        
        # 处理请求
        try:
            response = await call_next(request)
            
            # 记录响应
            duration = time.time() - start_time
            response_log = {
                "request_id": request_id,
                "status_code": response.status_code,
                "duration_seconds": round(duration, 3),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # 添加请求 ID 到响应头
            response.headers["X-Request-ID"] = request_id
            
            # 根据状态码选择日志级别
            if response.status_code >= 500:
                logger.error(f"[{request_id}] ❌ 服务器错误", extra=response_log)
            elif response.status_code >= 400:
                logger.warning(f"[{request_id}] ⚠️ 客户端错误", extra=response_log)
            else:
                logger.info(f"[{request_id}] ✅ 请求完成", extra=response_log)
            
            return response
            
        except Exception as e:
            duration = time.time() - start_time
            error_log = {
                "request_id": request_id,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "duration_seconds": round(duration, 3),
                "stack_trace": traceback.format_exc(),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            logger.error(f"[{request_id}] ❌ 请求异常", extra=error_log)
            raise


# 应用中间件
app.add_middleware(DiagnosticLoggingMiddleware)
```

---

### 2.2 日志查询工具

**创建查询脚本**: `app/tests/query_logs.sh`

```bash
#!/bin/bash

# 日志查询工具

LOG_FILE="/var/log/video_analysis/app.log"

# 使用方法
show_usage() {
    cat << EOF
日志查询工具

用法:
  $0 request <request_id>       # 查询特定请求的所有日志
  $0 errors [count]             # 查询最近的错误 (默认 10 条)
  $0 slow [threshold]           # 查询慢请求 (默认 > 60s)
  $0 upload-stats [hours]       # 统计上传性能 (默认最近 24 小时)
  $0 success-rate [hours]       # 计算成功率 (默认最近 24 小时)

示例:
  $0 request a3f2b1c4
  $0 errors 20
  $0 slow 30
  $0 upload-stats 12
EOF
}

# 查询特定请求
query_request() {
    local request_id=$1
    echo "查询 request_id: $request_id"
    echo "========================================"
    
    grep "\"request_id\":\"$request_id\"" "$LOG_FILE" | \
      jq -r '. | "\(.timestamp) [\(.level)] \(.message)"'
    
    echo ""
    echo "详细信息:"
    grep "\"request_id\":\"$request_id\"" "$LOG_FILE" | jq '.'
}

# 查询错误
query_errors() {
    local count=${1:-10}
    echo "最近 $count 条错误:"
    echo "========================================"
    
    grep '"level":"ERROR"' "$LOG_FILE" | tail -$count | \
      jq -r '. | "\(.timestamp) [\(.request_id // "N/A")] \(.message) - \(.error_message // "")"'
}

# 查询慢请求
query_slow() {
    local threshold=${1:-60}
    echo "慢请求 (> ${threshold}s):"
    echo "========================================"
    
    grep '"duration_seconds"' "$LOG_FILE" | \
      jq -r "select(.duration_seconds > $threshold) | \"\(.timestamp) [\(.request_id)] 耗时: \(.duration_seconds)s - \(.message)\"" | \
      tail -20
}

# 统计上传性能
upload_stats() {
    local hours=${1:-24}
    echo "上传性能统计 (最近 ${hours} 小时):"
    echo "========================================"
    
    # 提取上传速度
    grep -E "upload_speed_mbps|write_speed_mbps" "$LOG_FILE" | \
      jq -r '.upload_speed_mbps // .write_speed_mbps' | \
      awk '
        BEGIN {sum=0; count=0; min=999999; max=0}
        {
            sum+=$1; count++;
            if($1<min) min=$1;
            if($1>max) max=$1;
        }
        END {
            if(count>0) {
                printf "样本数: %d\n", count;
                printf "平均速度: %.2f MB/s\n", sum/count;
                printf "最快速度: %.2f MB/s\n", max;
                printf "最慢速度: %.2f MB/s\n", min;
            } else {
                print "无数据";
            }
        }
      '
}

# 计算成功率
success_rate() {
    local hours=${1:-24}
    echo "成功率统计 (最近 ${hours} 小时):"
    echo "========================================"
    
    # 计算成功和失败次数
    success=$(grep '"status":"success"' "$LOG_FILE" | wc -l)
    error=$(grep '"status":"error"' "$LOG_FILE" | wc -l)
    total=$((success + error))
    
    if [ $total -gt 0 ]; then
        rate=$(echo "scale=2; $success * 100 / $total" | bc)
        echo "总请求数: $total"
        echo "成功: $success"
        echo "失败: $error"
        echo "成功率: ${rate}%"
        
        # 失败原因分布
        echo ""
        echo "失败原因分布:"
        grep '"status":"error"' "$LOG_FILE" | \
          jq -r '.error_type // "unknown"' | \
          sort | uniq -c | sort -rn | head -10
    else
        echo "无数据"
    fi
}

# 主逻辑
case "$1" in
    request)
        query_request "$2"
        ;;
    errors)
        query_errors "$2"
        ;;
    slow)
        query_slow "$2"
        ;;
    upload-stats)
        upload_stats "$2"
        ;;
    success-rate)
        success_rate "$2"
        ;;
    *)
        show_usage
        exit 1
        ;;
esac
```

**使用示例**:
```bash
# 查询特定请求
bash app/tests/query_logs.sh request a3f2b1c4

# 查询最近 20 个错误
bash app/tests/query_logs.sh errors 20

# 查询慢请求 (> 30s)
bash app/tests/query_logs.sh slow 30

# 统计上传性能
bash app/tests/query_logs.sh upload-stats 24

# 计算成功率
bash app/tests/query_logs.sh success-rate 24
```

---

## 3. 性能分析工具

### 3.1 cProfile 性能剖析

**创建剖析脚本**: `app/tests/profile_upload.py`

```python
#!/usr/bin/env python3
"""
使用 cProfile 分析上传性能瓶颈
"""
import cProfile
import pstats
import io
import sys
import asyncio

sys.path.insert(0, '/root/my_youtube_summarizer/backend')

from app.services.pipeline_service import pipeline

async def profile_upload():
    """剖析完整上传流程"""
    test_video = "/tmp/test_video.mp4"
    
    # 确保测试文件存在
    import subprocess
    subprocess.run([
        'ffmpeg', '-f', 'lavfi', '-i', 'color=c=blue:s=640x480:d=10',
        '-y', test_video
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # 执行处理
    result = await pipeline.process_video_with_summary(
        video_file=test_video,
        user_id="test_user"
    )
    
    return result


def run_profiling():
    """运行性能剖析"""
    pr = cProfile.Profile()
    pr.enable()
    
    # 执行异步函数
    result = asyncio.run(profile_upload())
    
    pr.disable()
    
    # 输出统计
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
    ps.print_stats(30)  # 显示前 30 个最耗时的函数
    
    print(s.getvalue())
    
    # 保存到文件
    ps.dump_stats('upload_profile.prof')
    print("\n✓ 剖析结果已保存到 upload_profile.prof")
    print("  可使用 snakeviz 可视化: pip install snakeviz && snakeviz upload_profile.prof")


if __name__ == "__main__":
    run_profiling()
```

**执行**:
```bash
cd /root/my_youtube_summarizer/backend
python3 app/tests/profile_upload.py

# 可视化结果 (可选)
pip install snakeviz
snakeviz upload_profile.prof
```

---

### 3.2 内存分析

**内存监控脚本**:
```python
#!/usr/bin/env python3
"""
监控上传过程的内存使用
"""
from memory_profiler import profile
import sys
import asyncio

sys.path.insert(0, '/root/my_youtube_summarizer/backend')

from app.services.pipeline_service import pipeline

@profile
async def memory_test_upload():
    """监控内存使用的上传测试"""
    test_video = "/tmp/test_video.mp4"
    
    print("开始上传测试...")
    result = await pipeline.process_video_with_summary(
        video_file=test_video,
        user_id="test_user"
    )
    print("上传完成")
    
    return result


if __name__ == "__main__":
    # 安装: pip install memory_profiler
    asyncio.run(memory_test_upload())
```

**执行**:
```bash
pip install memory_profiler
python3 -m memory_profiler app/tests/memory_upload_test.py
```

---

## 4. 实时监控方案

### 4.1 实时日志监控脚本

**创建**: `app/tests/monitor_upload_health.py`

```python
#!/usr/bin/env python3
"""
实时监控上传健康状态
当检测到异常时发送告警
"""
import time
import json
import subprocess
from datetime import datetime, timedelta
from collections import deque

LOG_FILE = "/var/log/video_analysis/app.log"
CHECK_INTERVAL = 60  # 每分钟检查一次
ALERT_THRESHOLD = 3  # 5 分钟内失败 3 次告警

# 使用队列记录最近的失败
recent_failures = deque(maxlen=10)

def send_alert(message: str):
    """发送告警 (可扩展到钉钉/邮件/短信)"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    alert = f"🚨 告警 [{timestamp}]: {message}"
    
    print(alert)
    
    # 写入告警日志
    with open("/var/log/video_analysis/alerts.log", "a") as f:
        f.write(alert + "\n")
    
    # TODO: 发送钉钉/邮件通知
    # send_dingtalk(alert)


def check_recent_errors():
    """检查最近的错误"""
    # 获取最近 5 分钟的错误
    cmd = f'tail -1000 {LOG_FILE} | grep \'"level":"ERROR"\' | tail -10'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    errors = []
    for line in result.stdout.strip().split('\n'):
        if line:
            try:
                log_entry = json.loads(line)
                errors.append(log_entry)
            except:
                pass
    
    return errors


def check_success_rate():
    """检查最近 1 小时的成功率"""
    cmd = f'tail -10000 {LOG_FILE} | grep \'"status"\' | tail -100'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    success = 0
    total = 0
    
    for line in result.stdout.strip().split('\n'):
        if line:
            try:
                log_entry = json.loads(line)
                total += 1
                if log_entry.get('status') == 'success':
                    success += 1
            except:
                pass
    
    if total > 0:
        rate = (success / total) * 100
        return rate, success, total
    return 100, 0, 0


def main():
    """主监控循环"""
    print("="*50)
    print("  视频上传健康监控")
    print(f"  日志文件: {LOG_FILE}")
    print(f"  检查间隔: {CHECK_INTERVAL}s")
    print("="*50)
    print("")
    
    while True:
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] 执行健康检查...")
            
            # 检查 1: 最近错误
            errors = check_recent_errors()
            if len(errors) >= ALERT_THRESHOLD:
                send_alert(f"最近检测到 {len(errors)} 个错误,超过阈值 {ALERT_THRESHOLD}")
                
                # 显示错误详情
                for error in errors[-3:]:  # 显示最近 3 个
                    print(f"  错误: {error.get('message')} - {error.get('error_message')}")
            
            # 检查 2: 成功率
            rate, success, total = check_success_rate()
            print(f"  成功率: {rate:.1f}% ({success}/{total})")
            
            if rate < 80 and total >= 10:
                send_alert(f"成功率降至 {rate:.1f}% ({success}/{total})")
            
            # 检查 3: 磁盘空间
            df_result = subprocess.run(
                'df -h /tmp | awk \'NR==2 {print $5}\' | sed \'s/%//\'',
                shell=True, capture_output=True, text=True
            )
            disk_usage = int(df_result.stdout.strip())
            print(f"  磁盘使用率 (/tmp): {disk_usage}%")
            
            if disk_usage > 90:
                send_alert(f"磁盘空间不足: /tmp 使用率 {disk_usage}%")
            
            print("")
            
        except Exception as e:
            print(f"⚠️ 监控异常: {e}")
        
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n✓ 监控已停止")
```

**后台运行**:
```bash
cd /root/my_youtube_summarizer/backend
nohup python3 app/tests/monitor_upload_health.py > /var/log/video_analysis/monitor.log 2>&1 &

# 查看监控日志
tail -f /var/log/video_analysis/monitor.log
```

---

## 5. 故障定位决策树

### 5.1 完整决策树

```
上传失败
│
├─ HTTP 状态码 != 200?
│  ├─ 413 (Payload Too Large)
│  │  └─ 检查 Nginx client_max_body_size
│  │
│  ├─ 504 (Gateway Timeout)
│  │  └─ 检查 Nginx proxy_read_timeout
│  │
│  ├─ 502 (Bad Gateway)
│  │  └─ 检查 FastAPI 服务是否运行
│  │
│  └─ 其他
│     └─ 查看 Nginx error.log
│
├─ HTTP 200 但 status != "success"?
│  │
│  ├─ 错误包含 "disk space"?
│  │  └─ 清理 /tmp 目录
│  │
│  ├─ 错误包含 "OSS"?
│  │  ├─ 检查网络到 OSS 连通性
│  │  ├─ 验证 AccessKey 配置
│  │  └─ 查看 OSS 控制台状态
│  │
│  ├─ 错误包含 "Paraformer" 或 "DashScope"?
│  │  ├─ 检查 API Key 配置
│  │  ├─ 查看是否触发限流
│  │  └─ 测试 API 连通性
│  │
│  └─ 其他错误
│     └─ 查看后端日志详细堆栈
│
└─ 偶发性失败 (有时成功有时失败)?
   │
   ├─ 执行并发测试
   │  ├─ 并发失败率高
   │  │  ├─ 检查文件名冲突
   │  │  ├─ 检查资源限制 (ulimit)
   │  │  └─ 检查数据库连接池
   │  │
   │  └─ 并发成功率正常
   │     └─ 问题不在并发
   │
   ├─ 执行环境对比测试
   │  ├─ 本地成功,服务器失败
   │  │  ├─ 检查服务器配置差异
   │  │  ├─ 检查网络代理设置
   │  │  └─ 检查防火墙规则
   │  │
   │  └─ 两者成功率相近
   │     └─ 问题不在环境
   │
   └─ 执行 24 小时监控
      ├─ 特定时间段失败率高
      │  ├─ 检查网络质量变化
      │  ├─ 检查服务器负载
      │  └─ 检查依赖服务限流
      │
      └─ 无明显规律
         └─ 开启详细日志追踪单次失败
```

---

### 5.2 快速诊断清单

**当遇到上传失败时,按顺序执行:**

```bash
# 1. 检查服务是否运行
curl http://localhost:8000/health

# 2. 检查磁盘空间
df -h /tmp

# 3. 查看最近的错误日志
tail -50 /var/log/video_analysis/app.log | grep ERROR

# 4. 测试 OSS 连接
curl -I https://oss-cn-beijing.aliyuncs.com

# 5. 执行小文件上传测试
bash app/tests/test_small_file_upload.sh

# 6. 查询特定 request_id 的完整链路
bash app/tests/query_logs.sh request <request_id>

# 7. 如果仍未定位,开启详细日志
# 编辑 backend/app/core/logging.py 设置 log_level="DEBUG"
# 重启服务并重新测试
```

---

## 6. 应急响应手册

### 6.1 紧急故障处理流程

**P0 - 服务完全不可用**:
```bash
# 1. 检查服务进程
ps aux | grep uvicorn

# 2. 如果进程不存在,重启服务
systemctl restart video-analysis

# 3. 查看启动日志
journalctl -u video-analysis -n 50

# 4. 如果仍无法启动,检查端口占用
netstat -tuln | grep 8000

# 5. 通知用户维护中,预计恢复时间
```

**P1 - 成功率 < 50%**:
```bash
# 1. 立即查看错误分布
bash app/tests/query_logs.sh errors 50

# 2. 如果是 OSS 问题,切换到本地存储 (临时)
# 修改代码跳过 OSS 上传

# 3. 如果是磁盘空间问题,紧急清理
find /tmp/aliyun_video_service -mmin +30 -delete

# 4. 监控后续成功率变化
```

**P2 - 成功率 50-80%**:
```bash
# 1. 收集最近 100 次请求的统计
bash app/tests/query_logs.sh success-rate 1

# 2. 分析失败模式
bash app/tests/query_logs.sh slow 60

# 3. 部署监控脚本
nohup python3 app/tests/monitor_upload_health.py &

# 4. 计划下一次维护窗口优化
```

---

### 6.2 常见问题快速修复

**问题 1: "磁盘空间不足"**
```bash
# 临时清理
find /tmp -type f -mtime +1 -delete

# 永久解决
# 1. 添加定时清理任务 (crontab)
# 2. 增加磁盘配额
# 3. 启用自动清理机制
```

**问题 2: "OSS 连接超时"**
```bash
# 1. 测试网络
ping oss-cn-beijing.aliyuncs.com

# 2. 检查代理
echo $http_proxy

# 3. 尝试直连 (临时)
unset http_proxy https_proxy
systemctl restart video-analysis

# 4. 检查 OSS 控制台是否有故障公告
```

**问题 3: "并发上传冲突"**
```bash
# 1. 立即限制并发数
# 在 Nginx 配置添加:
# limit_conn_zone $binary_remote_addr zone=addr:10m;
# limit_conn addr 5;

# 2. 重启 Nginx
nginx -s reload

# 3. 优化代码使用唯一文件名
```

---

## 总结

### 工具速查表

| 工具 | 用途 | 命令 |
|------|------|------|
| curl 诊断 | 手动上传测试 | `bash app/tests/curl_diagnostic.sh` |
| Python 测试 | 交互式上传测试 | `python3 app/tests/python_upload_diagnostic.py` |
| 日志查询 | 分析历史日志 | `bash app/tests/query_logs.sh request <id>` |
| 性能剖析 | 定位性能瓶颈 | `python3 app/tests/profile_upload.py` |
| 实时监控 | 持续健康检查 | `python3 app/tests/monitor_upload_health.py` |
| 环境检查 | 验证配置 | `bash app/tests/diagnostics_check_server.sh` |

### 诊断优先级

1. **快速排查** (< 5 分钟):
   - 执行 `curl http://localhost:8000/health`
   - 查看最近错误日志
   - 检查磁盘空间

2. **深入分析** (15-30 分钟):
   - 执行完整环境检查
   - 运行小文件上传测试
   - 查询日志统计

3. **长期监控** (持续):
   - 部署实时监控脚本
   - 执行 24 小时压力测试
   - 分析性能剖析报告

---

**文档版本**: v1.0  
**最后更新**: 2025-01-15  
**维护者**: 系统诊断组
