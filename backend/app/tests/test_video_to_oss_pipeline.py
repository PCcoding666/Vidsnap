"""
端到端集成测试：YouTube视频下载 → 场景关键帧提取 → OSS上传 → URL访问验证

测试目标：验证从YouTube下载视频到OSS存储的完整流程
作者：AI Assistant
创建时间：2025-10-17
"""
import pytest
import asyncio
import os
import time
import requests
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

from ..services.video_service import video_service
from ..services.oss_service import oss_service
from ..core.config import settings


# 测试配置
TEST_YOUTUBE_URL = "https://www.youtube.com/watch?v=1PaoWKvcJP0"
NETWORK_TIMEOUT = 120  # 网络超时120秒
MIN_KEYFRAMES = 1  # 最少关键帧数量
MAX_KEYFRAMES = 10  # 最多关键帧数量
TEST_REPORT_PATH = Path(__file__).parent / "docs" / "TEST_OSS_PIPELINE_RESULTS.md"


# ================= 辅助函数 =================

def check_oss_configuration() -> tuple[bool, str]:
    """检查OSS配置是否完整"""
    required_env_vars = {
        "ALIYUN_ACCESS_KEY_ID": settings.ALIYUN_ACCESS_KEY_ID,
        "ALIYUN_ACCESS_KEY_SECRET": settings.ALIYUN_ACCESS_KEY_SECRET,
        "ALIYUN_OSS_ENDPOINT": settings.ALIYUN_OSS_ENDPOINT,
        "ALIYUN_OSS_BUCKET": settings.ALIYUN_OSS_BUCKET
    }
    
    missing_vars = [key for key, value in required_env_vars.items() if not value]
    
    if missing_vars:
        error_msg = f"缺少以下环境变量: {', '.join(missing_vars)}\n\n"
        error_msg += "配置方法：\n"
        error_msg += "1. 创建或编辑 backend/.env 文件\n"
        error_msg += "2. 添加以下配置：\n"
        error_msg += "   ALIYUN_ACCESS_KEY_ID=your_access_key_id\n"
        error_msg += "   ALIYUN_ACCESS_KEY_SECRET=your_access_key_secret\n"
        error_msg += "   ALIYUN_OSS_ENDPOINT=oss-cn-xxx.aliyuncs.com\n"
        error_msg += "   ALIYUN_OSS_BUCKET=your_bucket_name\n"
        return False, error_msg
    
    return True, "OSS配置完整"


def generate_test_report(test_results: Dict[str, Any]) -> str:
    """生成Markdown格式的测试报告"""
    report = []
    report.append("# YouTube视频到OSS存储 - 端到端集成测试报告\n")
    report.append(f"**测试时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    report.append(f"**测试视频URL**: {TEST_YOUTUBE_URL}\n")
    report.append("\n---\n\n")
    
    # 1. 测试概览
    report.append("## 📊 测试概览\n")
    report.append(f"- **总体状态**: {'✅ 成功' if test_results.get('overall_success') else '❌ 失败'}\n")
    report.append(f"- **总耗时**: {test_results.get('total_duration', 0):.2f} 秒\n")
    report.append(f"- **视频ID**: {test_results.get('video_id', 'N/A')}\n")
    report.append("\n")
    
    # 2. 各阶段执行情况
    report.append("## 🔄 执行阶段\n")
    
    stages = test_results.get('stages', {})
    for stage_name, stage_data in stages.items():
        status_icon = "✅" if stage_data.get('success') else "❌"
        report.append(f"### {status_icon} {stage_name}\n")
        report.append(f"- **状态**: {'成功' if stage_data.get('success') else '失败'}\n")
        report.append(f"- **耗时**: {stage_data.get('duration', 0):.2f} 秒\n")
        
        if stage_data.get('details'):
            report.append(f"- **详情**: {stage_data['details']}\n")
        
        if stage_data.get('error'):
            report.append(f"- **错误**: {stage_data['error']}\n")
        
        report.append("\n")
    
    # 3. 关键帧详情
    if test_results.get('keyframes'):
        report.append("## 🖼️ 关键帧信息\n")
        report.append(f"**提取数量**: {len(test_results['keyframes'])} 帧\n\n")
        
        report.append("| 序号 | 时间戳 | OSS URL | 可访问性 |\n")
        report.append("|------|--------|---------|----------|\n")
        
        for idx, kf in enumerate(test_results['keyframes'], 1):
            timestamp = kf.get('timestamp', 0)
            oss_url = kf.get('oss_url', 'N/A')
            accessible = "✅" if kf.get('url_accessible') else "❌"
            
            # 截断长URL显示
            display_url = oss_url if len(oss_url) < 50 else f"{oss_url[:47]}..."
            
            report.append(f"| {idx} | {timestamp:.2f}s | {display_url} | {accessible} |\n")
        
        report.append("\n")
    
    # 4. URL可访问性测试
    if test_results.get('url_accessibility'):
        accessibility_data = test_results['url_accessibility']
        report.append("## 🌐 URL可访问性测试\n")
        report.append(f"- **总URL数量**: {accessibility_data.get('total_urls', 0)}\n")
        report.append(f"- **可访问数量**: {accessibility_data.get('accessible_count', 0)}\n")
        report.append(f"- **不可访问数量**: {accessibility_data.get('inaccessible_count', 0)}\n")
        report.append(f"- **可访问率**: {accessibility_data.get('accessibility_rate', 0):.1f}%\n")
        report.append("\n")
    
    # 5. 清理操作
    if test_results.get('cleanup'):
        cleanup_data = test_results['cleanup']
        report.append("## 🧹 清理操作\n")
        report.append(f"- **状态**: {'成功' if cleanup_data.get('success') else '失败'}\n")
        report.append(f"- **清理文件数**: {cleanup_data.get('cleaned_files', 0)}\n")
        report.append("\n")
    
    # 6. 错误日志
    if test_results.get('errors'):
        report.append("## ⚠️ 错误日志\n")
        for error in test_results['errors']:
            report.append(f"- {error}\n")
        report.append("\n")
    
    # 7. 结论
    report.append("## 📝 测试结论\n")
    if test_results.get('overall_success'):
        report.append("✅ **所有测试通过！** 完整的YouTube到OSS流程验证成功。\n")
    else:
        report.append("❌ **测试失败！** 请查看上述错误日志进行排查。\n")
    
    report.append("\n---\n")
    report.append(f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n")
    
    return "".join(report)


async def check_url_accessibility(url: str, timeout: int = 10) -> tuple[bool, int, str]:
    """
    检查URL是否可访问
    
    Returns:
        (是否可访问, HTTP状态码, 错误信息)
    """
    try:
        # 先尝试HEAD请求（更高效）
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        
        # 如果HEAD请求失败，尝试GET请求（某些OSS配置可能不支持HEAD）
        if response.status_code >= 400:
            response = requests.get(url, timeout=timeout, stream=True)
            # 只读取少量数据确认可访问性
            next(response.iter_content(chunk_size=1024), None)
            response.close()
        
        is_accessible = response.status_code == 200
        return is_accessible, response.status_code, "" if is_accessible else f"HTTP {response.status_code}"
        
    except requests.Timeout:
        return False, 0, "请求超时"
    except requests.RequestException as e:
        error_msg = str(e)
        # 提取更详细的错误信息
        if "ConnectionError" in error_msg:
            return False, 0, "连接错误：无法连接到OSS服务器"
        elif "403" in error_msg:
            return False, 403, "权限错误：Bucket可能未设置为公共读"
        elif "404" in error_msg:
            return False, 404, "文件不存在"
        else:
            return False, 0, f"请求异常: {error_msg[:100]}"


# ================= Pytest Fixtures =================

@pytest.fixture(scope="module")
def test_results_collector():
    """测试结果收集器"""
    return {
        'overall_success': False,
        'total_duration': 0,
        'video_id': None,
        'stages': {},
        'keyframes': [],
        'url_accessibility': {},
        'cleanup': {},
        'errors': []
    }


@pytest.fixture(scope="module")
def skip_if_no_oss_config():
    """如果没有OSS配置则跳过测试"""
    config_ok, message = check_oss_configuration()
    if not config_ok:
        pytest.skip(f"OSS配置不完整，跳过测试\n{message}")


# ================= 测试用例 =================

@pytest.mark.asyncio
async def test_oss_service_availability(skip_if_no_oss_config, test_results_collector):
    """
    测试1：验证OSS服务可用性
    """
    print("\n" + "="*60)
    print("测试1：验证OSS服务可用性")
    print("="*60)
    
    start_time = time.time()
    
    try:
        assert oss_service.is_available(), "OSS服务不可用"
        
        duration = time.time() - start_time
        test_results_collector['stages']['OSS服务检查'] = {
            'success': True,
            'duration': duration,
            'details': f'OSS Bucket: {settings.ALIYUN_OSS_BUCKET}'
        }
        
        print(f"✅ OSS服务可用 (耗时: {duration:.2f}s)")
        print(f"   Bucket: {settings.ALIYUN_OSS_BUCKET}")
        print(f"   Endpoint: {settings.ALIYUN_OSS_ENDPOINT}")
        
    except AssertionError as e:
        duration = time.time() - start_time
        test_results_collector['stages']['OSS服务检查'] = {
            'success': False,
            'duration': duration,
            'error': str(e)
        }
        test_results_collector['errors'].append(f"OSS服务检查失败: {e}")
        raise


@pytest.mark.asyncio
async def test_full_pipeline_youtube_to_oss(skip_if_no_oss_config, test_results_collector):
    """
    测试2：完整流程 - YouTube下载 → 关键帧提取 → OSS上传
    """
    print("\n" + "="*60)
    print("测试2：完整流程测试")
    print("="*60)
    
    pipeline_start = time.time()
    session_temp_dir = None
    
    try:
        # 阶段1: YouTube视频下载
        print("\n[阶段1] YouTube视频下载...")
        stage1_start = time.time()
        
        result = await asyncio.wait_for(
            video_service.process_video_dual_source(youtube_url=TEST_YOUTUBE_URL),
            timeout=NETWORK_TIMEOUT
        )
        
        stage1_duration = time.time() - stage1_start
        
        # 验证下载成功
        assert result['status'] == 'success', f"视频处理失败: {result.get('error', '未知错误')}"
        assert result.get('video_id'), "视频ID缺失"
        
        video_id = result['video_id']
        session_temp_dir = result.get('session_temp_dir')
        test_results_collector['video_id'] = video_id
        
        test_results_collector['stages']['YouTube视频下载'] = {
            'success': True,
            'duration': stage1_duration,
            'details': f'视频ID: {video_id}'
        }
        
        print(f"✅ 视频下载成功 (耗时: {stage1_duration:.2f}s)")
        print(f"   视频ID: {video_id}")
        print(f"   标题: {result['video_info'].title}")
        print(f"   时长: {result['video_info'].duration:.2f}s")
        
        # 阶段2: 验证关键帧提取
        print("\n[阶段2] 关键帧提取验证...")
        stage2_start = time.time()
        
        keyframes = result.get('keyframes', [])
        assert len(keyframes) >= MIN_KEYFRAMES, f"关键帧数量不足，期望至少{MIN_KEYFRAMES}个，实际{len(keyframes)}个"
        assert len(keyframes) <= MAX_KEYFRAMES, f"关键帧数量过多，期望最多{MAX_KEYFRAMES}个，实际{len(keyframes)}个"
        
        stage2_duration = time.time() - stage2_start
        
        test_results_collector['stages']['关键帧提取'] = {
            'success': True,
            'duration': stage2_duration,
            'details': f'提取了{len(keyframes)}个关键帧'
        }
        
        print(f"✅ 关键帧提取成功 (耗时: {stage2_duration:.2f}s)")
        print(f"   关键帧数量: {len(keyframes)}")
        
        # 阶段3: 验证OSS上传
        print("\n[阶段3] OSS上传验证...")
        stage3_start = time.time()
        
        # 验证视频OSS URL
        video_oss_url = result['video_info'].oss_video_url
        assert video_oss_url, "视频OSS URL缺失"
        assert video_oss_url.startswith('https://'), "视频OSS URL格式错误"
        
        # 验证每个关键帧都有OSS URL
        for idx, keyframe in enumerate(keyframes):
            assert keyframe.oss_image_url, f"关键帧{idx}的OSS URL缺失"
            assert keyframe.oss_image_url.startswith('https://'), f"关键帧{idx}的OSS URL格式错误"
            
            # 收集关键帧信息
            test_results_collector['keyframes'].append({
                'frame_id': keyframe.frame_id,
                'timestamp': keyframe.timestamp,
                'oss_url': keyframe.oss_image_url,
                'url_accessible': False  # 稍后测试
            })
        
        stage3_duration = time.time() - stage3_start
        
        test_results_collector['stages']['OSS上传验证'] = {
            'success': True,
            'duration': stage3_duration,
            'details': f'视频和{len(keyframes)}个关键帧均已上传OSS'
        }
        
        print(f"✅ OSS上传验证成功 (耗时: {stage3_duration:.2f}s)")
        print(f"   视频OSS URL: {video_oss_url[:60]}...")
        print(f"   关键帧OSS URL数量: {len(keyframes)}")
        
        # 记录总耗时
        pipeline_duration = time.time() - pipeline_start
        test_results_collector['total_duration'] = pipeline_duration
        
        print(f"\n✅ 完整流程测试通过！总耗时: {pipeline_duration:.2f}s")
        
    except asyncio.TimeoutError:
        duration = time.time() - pipeline_start
        error_msg = f"流程超时 (超过{NETWORK_TIMEOUT}秒)"
        test_results_collector['stages']['完整流程'] = {
            'success': False,
            'duration': duration,
            'error': error_msg
        }
        test_results_collector['errors'].append(error_msg)
        pytest.fail(error_msg)
        
    except Exception as e:
        duration = time.time() - pipeline_start
        test_results_collector['stages']['完整流程'] = {
            'success': False,
            'duration': duration,
            'error': str(e)
        }
        test_results_collector['errors'].append(f"流程异常: {e}")
        raise
    
    finally:
        # 保存session目录供后续清理
        if session_temp_dir:
            test_results_collector['session_temp_dir'] = session_temp_dir


@pytest.mark.asyncio
async def test_keyframe_oss_urls_accessibility(skip_if_no_oss_config, test_results_collector):
    """
    测试3：验证OSS URL可访问性
    """
    print("\n" + "="*60)
    print("测试3：OSS URL可访问性验证")
    print("="*60)
    
    keyframes = test_results_collector.get('keyframes', [])
    
    if not keyframes:
        pytest.skip("没有可测试的关键帧")
    
    start_time = time.time()
    accessible_count = 0
    inaccessible_count = 0
    
    print(f"\n检查{len(keyframes)}个关键帧URL的可访问性...")
    
    for idx, keyframe_data in enumerate(keyframes, 1):
        oss_url = keyframe_data['oss_url']
        
        is_accessible, status_code, error = await check_url_accessibility(oss_url, timeout=10)
        keyframe_data['url_accessible'] = is_accessible
        
        if is_accessible:
            accessible_count += 1
            print(f"   ✅ 关键帧{idx}: 可访问 (HTTP {status_code})")
        else:
            inaccessible_count += 1
            print(f"   ❌ 关键帧{idx}: 不可访问 (状态码: {status_code}, 错误: {error})")
            test_results_collector['errors'].append(f"关键帧{idx} URL不可访问: {error}")
    
    duration = time.time() - start_time
    accessibility_rate = (accessible_count / len(keyframes)) * 100 if keyframes else 0
    
    # 保存可访问性数据
    test_results_collector['url_accessibility'] = {
        'total_urls': len(keyframes),
        'accessible_count': accessible_count,
        'inaccessible_count': inaccessible_count,
        'accessibility_rate': accessibility_rate
    }
    
    test_results_collector['stages']['URL可访问性'] = {
        'success': accessible_count == len(keyframes),
        'duration': duration,
        'details': f'{accessible_count}/{len(keyframes)} 可访问 ({accessibility_rate:.1f}%)'
    }
    
    print(f"\n✅ URL可访问性检查完成 (耗时: {duration:.2f}s)")
    print(f"   可访问: {accessible_count}/{len(keyframes)} ({accessibility_rate:.1f}%)")
    
    # 断言所有URL都可访问
    assert accessible_count == len(keyframes), f"部分URL不可访问: {inaccessible_count}/{len(keyframes)}"


@pytest.mark.asyncio
async def test_cleanup_after_processing(skip_if_no_oss_config, test_results_collector):
    """
    测试4：验证临时文件清理
    """
    print("\n" + "="*60)
    print("测试4：临时文件清理")
    print("="*60)
    
    start_time = time.time()
    session_temp_dir = test_results_collector.get('session_temp_dir')
    
    if not session_temp_dir:
        pytest.skip("没有需要清理的临时目录")
    
    try:
        # 统计清理前的文件数量
        session_path = Path(session_temp_dir)
        files_before = []
        if session_path.exists():
            files_before = list(session_path.rglob('*'))
        
        print(f"\n清理临时目录: {session_temp_dir}")
        print(f"   文件数量: {len(files_before)}")
        
        # 执行清理
        video_service.cleanup_session(session_temp_dir)
        
        # 验证清理结果
        cleanup_success = not session_path.exists()
        
        duration = time.time() - start_time
        
        test_results_collector['cleanup'] = {
            'success': cleanup_success,
            'cleaned_files': len(files_before)
        }
        
        test_results_collector['stages']['临时文件清理'] = {
            'success': cleanup_success,
            'duration': duration,
            'details': f'清理了{len(files_before)}个文件'
        }
        
        if cleanup_success:
            print(f"✅ 临时文件清理成功 (耗时: {duration:.2f}s)")
        else:
            print(f"⚠️ 临时目录仍然存在")
            test_results_collector['errors'].append("临时目录清理不完整")
        
        assert cleanup_success, "临时目录清理失败"
        
    except Exception as e:
        duration = time.time() - start_time
        test_results_collector['stages']['临时文件清理'] = {
            'success': False,
            'duration': duration,
            'error': str(e)
        }
        test_results_collector['errors'].append(f"清理异常: {e}")
        raise


@pytest.fixture(scope="module", autouse=True)
def generate_final_report(request, test_results_collector):
    """测试结束后生成最终报告"""
    yield
    
    # 所有测试完成后执行
    print("\n" + "="*60)
    print("生成测试报告...")
    print("="*60)
    
    # 判断总体是否成功
    all_stages_success = all(
        stage.get('success', False) 
        for stage in test_results_collector['stages'].values()
    )
    test_results_collector['overall_success'] = all_stages_success
    
    # 生成报告
    report_content = generate_test_report(test_results_collector)
    
    # 保存报告
    try:
        TEST_REPORT_PATH.write_text(report_content, encoding='utf-8')
        print(f"\n✅ 测试报告已保存到: {TEST_REPORT_PATH}")
        print(f"   总体状态: {'✅ 成功' if all_stages_success else '❌ 失败'}")
    except Exception as e:
        print(f"\n⚠️ 保存测试报告失败: {e}")
    
    # 打印报告内容
    print("\n" + "="*60)
    print("测试报告预览")
    print("="*60)
    print(report_content)


# ================= 主入口 =================

if __name__ == "__main__":
    """直接运行测试"""
    import sys
    
    # 检查配置
    config_ok, message = check_oss_configuration()
    if not config_ok:
        print(f"\n❌ {message}")
        sys.exit(1)
    
    # 运行pytest
    pytest.main([
        __file__,
        "-v",  # 详细输出
        "-s",  # 显示print输出
        "--tb=short",  # 简短的错误追踪
        "--asyncio-mode=auto"  # 自动asyncio模式
    ])
