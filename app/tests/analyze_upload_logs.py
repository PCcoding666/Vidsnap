#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
视频上传日志分析工具

功能:
- 解析结构化日志文件
- 提取上传失败记录
- 统计失败模式和原因
- 生成分析报告

使用方法:
    python3 app/tests/analyze_upload_logs.py [选项]

选项:
    --log-file FILE         日志文件路径
    --time-range HOURS      分析最近N小时的日志 (默认: 24)
    --format FORMAT         输出格式 (text|json|html, 默认: text)
    --output FILE           输出报告文件
    --filter PATTERN        过滤特定模式的日志
    --verbose               显示详细信息

示例:
    python3 app/tests/analyze_upload_logs.py --log-file /var/log/app.log
    python3 app/tests/analyze_upload_logs.py --time-range 12 --format json
    python3 app/tests/analyze_upload_logs.py --output report.html --format html
"""

import argparse
import json
import sys
import re
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from pathlib import Path
from typing import Dict, List, Any, Optional
import subprocess


# ==================== 颜色输出 ====================
class Colors:
    """终端颜色代码"""
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    MAGENTA = '\033[0;35m'
    CYAN = '\033[0;36m'
    BOLD = '\033[1m'
    NC = '\033[0m'  # No Color


def colorize(text: str, color: str) -> str:
    """给文本添加颜色"""
    return f"{color}{text}{Colors.NC}"


# ==================== 日志解析 ====================
class LogEntry:
    """日志条目"""
    
    def __init__(self, raw_line: str):
        self.raw = raw_line
        self.timestamp = None
        self.level = None
        self.message = None
        self.request_id = None
        self.error_type = None
        self.error_message = None
        self.file_name = None
        self.file_size = None
        self.duration_ms = None
        self.user_id = None
        self.extra_data = {}
        
        self._parse()
    
    def _parse(self):
        """解析日志行"""
        try:
            # 尝试解析 JSON 格式
            if self.raw.strip().startswith('{'):
                data = json.loads(self.raw)
                self.timestamp = data.get('timestamp')
                self.level = data.get('level')
                self.message = data.get('message')
                self.request_id = data.get('request_id')
                self.user_id = data.get('user_id')
                self.duration_ms = data.get('duration_ms')
                self.file_size = data.get('file_size')
                
                # 提取额外数据
                if 'extra' in data:
                    self.extra_data = data['extra']
                
                # 提取异常信息
                if 'exception' in data:
                    exc = data['exception']
                    self.error_type = exc.get('type')
                    self.error_message = exc.get('message')
            
            else:
                # 解析文本格式日志
                # 格式: [timestamp] [request_id] LEVEL - message
                pattern = r'\[([^\]]+)\]\s*(?:\[([^\]]+)\])?\s*(\w+)\s*-\s*(.+)'
                match = re.match(pattern, self.raw)
                
                if match:
                    self.timestamp = match.group(1)
                    self.request_id = match.group(2)
                    self.level = match.group(3)
                    self.message = match.group(4)
                    
                    # 提取文件名
                    file_match = re.search(r'file[_-]?name[:\s]+([^\s,]+)', self.message, re.IGNORECASE)
                    if file_match:
                        self.file_name = file_match.group(1)
                    
                    # 提取文件大小
                    size_match = re.search(r'(\d+(?:\.\d+)?)\s*(MB|GB|bytes)', self.message)
                    if size_match:
                        size_val = float(size_match.group(1))
                        unit = size_match.group(2)
                        if unit == 'GB':
                            self.file_size = int(size_val * 1024 * 1024 * 1024)
                        elif unit == 'MB':
                            self.file_size = int(size_val * 1024 * 1024)
                        else:
                            self.file_size = int(size_val)
                    
                    # 提取错误信息
                    error_match = re.search(r'error[_-]?type[:\s]+(\w+)', self.message, re.IGNORECASE)
                    if error_match:
                        self.error_type = error_match.group(1)
                    
                    error_msg_match = re.search(r'error[:\s]+(.+?)(?:\s*,|\s*$)', self.message, re.IGNORECASE)
                    if error_msg_match:
                        self.error_message = error_msg_match.group(1).strip()
        
        except Exception as e:
            # 解析失败，保留原始数据
            pass
    
    def is_error(self) -> bool:
        """判断是否为错误日志"""
        return self.level in ('ERROR', 'CRITICAL')
    
    def is_upload_related(self) -> bool:
        """判断是否与上传相关"""
        keywords = ['upload', '上传', 'video_file', 'process_video', 'file operation']
        message_lower = (self.message or '').lower()
        return any(kw in message_lower for kw in keywords)


class LogAnalyzer:
    """日志分析器"""
    
    def __init__(self, log_file: Optional[str] = None, time_range_hours: int = 24):
        self.log_file = log_file
        self.time_range_hours = time_range_hours
        self.entries: List[LogEntry] = []
        self.errors: List[LogEntry] = []
        self.upload_errors: List[LogEntry] = []
        
        # 统计数据
        self.stats = {
            'total_entries': 0,
            'total_errors': 0,
            'upload_errors': 0,
            'error_types': Counter(),
            'error_messages': Counter(),
            'requests_with_errors': set(),
            'affected_files': set(),
        }
    
    def read_logs(self):
        """读取日志文件"""
        print(colorize(f"📖 读取日志文件: {self.log_file}", Colors.CYAN))
        
        if not self.log_file:
            # 尝试从 journalctl 读取
            print("未指定日志文件，尝试从 journalctl 读取...")
            try:
                cmd = f"journalctl -u uvicorn -u fastapi --since '{self.time_range_hours} hours ago' --no-pager"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                lines = result.stdout.split('\n')
            except Exception as e:
                print(colorize(f"❌ 无法从 journalctl 读取: {e}", Colors.RED))
                return
        else:
            log_path = Path(self.log_file)
            if not log_path.exists():
                print(colorize(f"❌ 日志文件不存在: {self.log_file}", Colors.RED))
                return
            
            with open(log_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        
        # 过滤时间范围
        cutoff_time = datetime.now() - timedelta(hours=self.time_range_hours)
        
        for line in lines:
            if not line.strip():
                continue
            
            entry = LogEntry(line)
            
            # 时间过滤
            if entry.timestamp:
                try:
                    # 尝试多种时间格式
                    for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f']:
                        try:
                            entry_time = datetime.strptime(entry.timestamp.split('+')[0].split('.')[0], fmt)
                            if entry_time < cutoff_time:
                                continue
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass
            
            self.entries.append(entry)
            self.stats['total_entries'] += 1
            
            if entry.is_error():
                self.errors.append(entry)
                self.stats['total_errors'] += 1
                
                if entry.request_id:
                    self.stats['requests_with_errors'].add(entry.request_id)
                
                if entry.is_upload_related():
                    self.upload_errors.append(entry)
                    self.stats['upload_errors'] += 1
                    
                    if entry.error_type:
                        self.stats['error_types'][entry.error_type] += 1
                    
                    if entry.error_message:
                        self.stats['error_messages'][entry.error_message] += 1
                    
                    if entry.file_name:
                        self.stats['affected_files'].add(entry.file_name)
        
        print(colorize(f"✓ 共读取 {self.stats['total_entries']} 条日志", Colors.GREEN))
        print(colorize(f"✓ 发现 {self.stats['total_errors']} 条错误日志", Colors.YELLOW))
        print(colorize(f"✓ 其中 {self.stats['upload_errors']} 条与上传相关", Colors.RED))
    
    def analyze(self):
        """分析日志"""
        print("\n" + colorize("=" * 60, Colors.CYAN))
        print(colorize("📊 日志分析报告", Colors.BOLD))
        print(colorize("=" * 60, Colors.CYAN))
        
        # 基本统计
        print(f"\n{colorize('📈 基本统计', Colors.BLUE)}")
        print(f"  分析时间范围: 最近 {self.time_range_hours} 小时")
        print(f"  总日志条目: {self.stats['total_entries']}")
        print(f"  总错误数: {self.stats['total_errors']}")
        print(f"  上传相关错误: {colorize(str(self.stats['upload_errors']), Colors.RED)}")
        print(f"  受影响的请求: {len(self.stats['requests_with_errors'])}")
        print(f"  受影响的文件: {len(self.stats['affected_files'])}")
        
        # 错误类型分布
        if self.stats['error_types']:
            print(f"\n{colorize('🔴 错误类型分布', Colors.RED)}")
            for error_type, count in self.stats['error_types'].most_common(10):
                percentage = (count / self.stats['upload_errors']) * 100
                print(f"  {error_type:30s} {count:3d} ({percentage:5.1f}%)")
        
        # 常见错误信息
        if self.stats['error_messages']:
            print(f"\n{colorize('💬 常见错误信息', Colors.YELLOW)}")
            for msg, count in self.stats['error_messages'].most_common(5):
                msg_short = msg[:60] + '...' if len(msg) > 60 else msg
                print(f"  [{count:2d}次] {msg_short}")
        
        # 时间分布分析
        self._analyze_time_distribution()
        
        # 请求分析
        self._analyze_requests()
    
    def _analyze_time_distribution(self):
        """分析错误的时间分布"""
        print(f"\n{colorize('⏰ 时间分布分析', Colors.CYAN)}")
        
        hour_distribution = defaultdict(int)
        
        for error in self.upload_errors:
            if error.timestamp:
                try:
                    for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S']:
                        try:
                            dt = datetime.strptime(error.timestamp.split('+')[0].split('.')[0], fmt)
                            hour_distribution[dt.hour] += 1
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass
        
        if hour_distribution:
            max_count = max(hour_distribution.values())
            for hour in range(24):
                count = hour_distribution.get(hour, 0)
                if count > 0:
                    bar_length = int((count / max_count) * 30)
                    bar = '█' * bar_length
                    print(f"  {hour:02d}:00  {bar} {count}")
    
    def _analyze_requests(self):
        """分析失败的请求"""
        print(f"\n{colorize('🔍 失败请求详情', Colors.MAGENTA)}")
        
        # 按 request_id 分组
        requests = defaultdict(list)
        for error in self.upload_errors:
            if error.request_id:
                requests[error.request_id].append(error)
        
        # 显示前5个失败请求的详情
        count = 0
        for req_id, errors in list(requests.items())[:5]:
            count += 1
            print(f"\n  请求 #{count} [ID: {req_id}]")
            print(f"    错误数: {len(errors)}")
            
            first_error = errors[0]
            if first_error.timestamp:
                print(f"    时间: {first_error.timestamp}")
            if first_error.file_name:
                print(f"    文件: {first_error.file_name}")
            if first_error.file_size:
                file_size_mb = first_error.file_size / 1024 / 1024
                print(f"    大小: {file_size_mb:.2f} MB")
            if first_error.error_type:
                print(f"    错误类型: {first_error.error_type}")
            if first_error.error_message:
                msg = first_error.error_message[:100]
                print(f"    错误信息: {msg}")
    
    def generate_report(self, format: str = 'text', output_file: Optional[str] = None):
        """生成分析报告"""
        if format == 'json':
            report = self._generate_json_report()
        elif format == 'html':
            report = self._generate_html_report()
        else:
            report = self._generate_text_report()
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"\n{colorize(f'✓ 报告已保存: {output_file}', Colors.GREEN)}")
        else:
            print("\n" + report)
    
    def _generate_text_report(self) -> str:
        """生成文本格式报告"""
        lines = []
        lines.append("=" * 60)
        lines.append("视频上传日志分析报告")
        lines.append("=" * 60)
        lines.append(f"\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"分析时间范围: 最近 {self.time_range_hours} 小时")
        lines.append(f"\n总日志条目: {self.stats['total_entries']}")
        lines.append(f"总错误数: {self.stats['total_errors']}")
        lines.append(f"上传相关错误: {self.stats['upload_errors']}")
        
        if self.stats['error_types']:
            lines.append("\n错误类型分布:")
            for error_type, count in self.stats['error_types'].most_common():
                percentage = (count / self.stats['upload_errors']) * 100
                lines.append(f"  {error_type}: {count} ({percentage:.1f}%)")
        
        return '\n'.join(lines)
    
    def _generate_json_report(self) -> str:
        """生成JSON格式报告"""
        report = {
            'generated_at': datetime.now().isoformat(),
            'time_range_hours': self.time_range_hours,
            'statistics': {
                'total_entries': self.stats['total_entries'],
                'total_errors': self.stats['total_errors'],
                'upload_errors': self.stats['upload_errors'],
                'affected_requests': len(self.stats['requests_with_errors']),
                'affected_files': len(self.stats['affected_files']),
            },
            'error_types': dict(self.stats['error_types']),
            'error_messages': dict(self.stats['error_messages'].most_common(10)),
        }
        return json.dumps(report, indent=2, ensure_ascii=False)
    
    def _generate_html_report(self) -> str:
        """生成HTML格式报告"""
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>视频上传日志分析报告</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
        h2 {{ color: #34495e; margin-top: 30px; }}
        .stat {{ display: inline-block; margin: 10px; padding: 15px; background: #ecf0f1; border-radius: 5px; }}
        .stat-value {{ font-size: 24px; font-weight: bold; color: #e74c3c; }}
        .stat-label {{ font-size: 12px; color: #7f8c8d; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #3498db; color: white; }}
        .error-type {{ color: #e74c3c; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 视频上传日志分析报告</h1>
        <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p>分析范围: 最近 {self.time_range_hours} 小时</p>
        
        <h2>基本统计</h2>
        <div class="stat">
            <div class="stat-value">{self.stats['total_entries']}</div>
            <div class="stat-label">总日志条目</div>
        </div>
        <div class="stat">
            <div class="stat-value">{self.stats['total_errors']}</div>
            <div class="stat-label">总错误数</div>
        </div>
        <div class="stat">
            <div class="stat-value">{self.stats['upload_errors']}</div>
            <div class="stat-label">上传错误</div>
        </div>
        
        <h2>错误类型分布</h2>
        <table>
            <tr><th>错误类型</th><th>次数</th><th>占比</th></tr>
"""
        
        for error_type, count in self.stats['error_types'].most_common():
            percentage = (count / max(self.stats['upload_errors'], 1)) * 100
            html += f"<tr><td class='error-type'>{error_type}</td><td>{count}</td><td>{percentage:.1f}%</td></tr>\n"
        
        html += """
        </table>
    </div>
</body>
</html>
"""
        return html


# ==================== 主函数 ====================
def main():
    parser = argparse.ArgumentParser(description='视频上传日志分析工具')
    parser.add_argument('--log-file', help='日志文件路径')
    parser.add_argument('--time-range', type=int, default=24, help='分析最近N小时的日志 (默认: 24)')
    parser.add_argument('--format', choices=['text', 'json', 'html'], default='text', help='输出格式')
    parser.add_argument('--output', help='输出报告文件')
    parser.add_argument('--filter', help='过滤特定模式的日志')
    parser.add_argument('--verbose', action='store_true', help='显示详细信息')
    
    args = parser.parse_args()
    
    # 创建分析器
    analyzer = LogAnalyzer(log_file=args.log_file, time_range_hours=args.time_range)
    
    # 读取并分析日志
    analyzer.read_logs()
    
    if analyzer.stats['total_entries'] == 0:
        print(colorize("⚠ 未找到日志条目", Colors.YELLOW))
        return
    
    analyzer.analyze()
    
    # 生成报告
    if args.output or args.format != 'text':
        analyzer.generate_report(format=args.format, output_file=args.output)
    
    print("\n" + colorize("=" * 60, Colors.CYAN))
    print(colorize("✓ 分析完成", Colors.GREEN))
    print(colorize("=" * 60, Colors.CYAN))


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n" + colorize("⚠ 用户中断", Colors.YELLOW))
        sys.exit(1)
    except Exception as e:
        print("\n" + colorize(f"❌ 错误: {e}", Colors.RED))
        import traceback
        traceback.print_exc()
        sys.exit(1)
