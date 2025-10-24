"""
使用真实视频测试 Paraformer-v2 转录
测试文件: backend/app/tests/downloaded_video (1).mp4
"""
import sys
import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# 首先加载环境变量
env_path = Path(__file__).parent.parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path, override=True)
    print(f"已加载环境变量: {env_path}")

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

# 导入服务 (在加载环境变量之后)
from app.services.paraformer_service import paraformer_service
from app.services.oss_service import oss_service
from app.core.logging import logger


async def test_real_video_transcription():
    """测试真实视频的 Paraformer 转录"""
    
    print("\n" + "=" * 80)
    print("🎬 测试真实视频 Paraformer 转录")
    print("=" * 80)
    
    # 检查 API Key
    api_key = (
        os.getenv("TRANSCRIPT_SERVICE_API_KEY") or 
        os.getenv("QWEN_API_KEY") or 
        os.getenv("DASHSCOPE_API_KEY")
    )
    
    if api_key:
        print(f"✅ API Key 已设置: {api_key[:10]}...")
    else:
        print("❌ 未找到 API Key")
        return
    
    # 检查服务可用性
    if not paraformer_service.is_available():
        print("\n❌ Paraformer 服务不可用")
        return
    
    if not oss_service.is_available():
        print("\n❌ OSS 服务不可用")
        return
    
    print("✅ Paraformer 服务已就绪")
    print("✅ OSS 服务已就绪")
    
    # 视频文件路径
    video_path = Path(__file__).parent / "downloaded_video (1).mp4"
    
    if not video_path.exists():
        print(f"\n❌ 视频文件不存在: {video_path}")
        return
    
    # 获取视频信息
    video_size_mb = video_path.stat().st_size / (1024 * 1024)
    print(f"\n📹 视频文件信息:")
    print(f"   路径: {video_path}")
    print(f"   大小: {video_size_mb:.2f} MB")
    
    # 生成视频 ID
    video_id = "test_real_video_001"
    
    print(f"\n{'=' * 80}")
    print("📝 开始处理流程")
    print(f"{'=' * 80}")
    
    try:
        # 步骤 1: 使用 ffmpeg 提取音频
        print("\n[步骤 1/4] 🎵 使用 ffmpeg 提取音频...")
        audio_path = await paraformer_service._extract_audio_with_ffmpeg(
            str(video_path), 
            video_id
        )
        
        if not audio_path:
            print("❌ 音频提取失败")
            return
        
        audio_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        print(f"✅ 音频提取成功: {audio_path}")
        print(f"   大小: {audio_size_mb:.2f} MB")
        
        # 步骤 2: 上传音频到 OSS
        print("\n[步骤 2/4] ☁️  上传音频到阿里云 OSS...")
        audio_oss_url = await oss_service.upload_audio(audio_path, video_id)
        
        if not audio_oss_url:
            print("❌ OSS 上传失败")
            return
        
        print(f"✅ OSS 上传成功")
        print(f"   URL: {audio_oss_url}")
        
        # 步骤 3: 调用 Paraformer 转录
        print("\n[步骤 3/4] 🤖 调用 Paraformer-v2 转录...")
        print("   - 模型: paraformer-v2")
        print("   - 说话人分离: 启用")
        print("   - 预计耗时: 1-3 分钟")
        
        transcription_output = await paraformer_service.transcribe_audio_with_timestamps(
            audio_oss_url,
            language="auto",
            enable_diarization=True
        )
        
        if not transcription_output:
            print("❌ 转录失败")
            return
        
        print("✅ 转录完成")
        
        # 步骤 4: 解析转录结果
        print("\n[步骤 4/4] 📊 解析转录结果...")
        result = paraformer_service._parse_transcription_to_segments(
            transcription_output,
            audio_oss_url
        )
        
        if not result:
            print("❌ 结果解析失败")
            return
        
        print("✅ 解析成功")
        
        # 清理临时音频文件
        if os.path.exists(audio_path):
            try:
                os.remove(audio_path)
                print(f"✅ 已清理临时音频文件")
            except Exception as e:
                print(f"⚠️  清理临时文件失败: {e}")
        
        # 显示结果
        print("\n" + "=" * 80)
        print("🎉 转录成功！")
        print("=" * 80)
        
        print(f"\n📊 转录统计:")
        print(f"   - 总段落数: {len(result.segments)}")
        print(f"   - 说话人数: {result.speaker_count}")
        print(f"   - 平均置信度: {result.confidence:.2%}")
        print(f"   - 文本总长度: {len(result.full_text)} 字符")
        
        if result.full_text:
            print(f"\n📄 完整转录文本:")
            print("-" * 80)
            # 显示完整文本（最多前 500 字符）
            if len(result.full_text) > 500:
                print(result.full_text[:500] + "...")
                print(f"\n(完整文本共 {len(result.full_text)} 字符，已省略)")
            else:
                print(result.full_text)
        
        if result.segments:
            print(f"\n📝 详细段落 (前 20 段):")
            print("-" * 80)
            
            for i, segment in enumerate(result.segments[:20], 1):
                duration = segment.end_time - segment.start_time
                print(f"\n[段落 {i}]")
                print(f"  ⏱️  时间: {segment.start_time:.2f}s - {segment.end_time:.2f}s (时长: {duration:.2f}s)")
                print(f"  📈 置信度: {segment.confidence:.2%}")
                print(f"  💬 文本: {segment.text}")
            
            if len(result.segments) > 20:
                remaining = len(result.segments) - 20
                total_duration = result.segments[-1].end_time
                print(f"\n... 还有 {remaining} 个段落 (总时长: {total_duration:.2f}s) ...")
        
        print("\n" + "=" * 80)
        print("✅ 测试完成！")
        print("=" * 80)
        
        # 保存完整转录文本到文件
        output_file = Path(__file__).parent / "docs" / "real_video_transcription.txt"
        output_file.parent.mkdir(exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("真实视频 Paraformer 转录结果\n")
            f.write("=" * 80 + "\n\n")
            
            f.write(f"视频文件: {video_path.name}\n")
            f.write(f"视频大小: {video_size_mb:.2f} MB\n")
            f.write(f"音频 URL: {audio_oss_url}\n")
            f.write(f"\n统计信息:\n")
            f.write(f"  - 段落数: {len(result.segments)}\n")
            f.write(f"  - 说话人数: {result.speaker_count}\n")
            f.write(f"  - 置信度: {result.confidence:.2%}\n")
            f.write(f"  - 文本长度: {len(result.full_text)} 字符\n")
            f.write(f"\n" + "=" * 80 + "\n")
            f.write("完整转录文本\n")
            f.write("=" * 80 + "\n\n")
            f.write(result.full_text)
            f.write(f"\n\n" + "=" * 80 + "\n")
            f.write("详细段落\n")
            f.write("=" * 80 + "\n\n")
            
            for i, segment in enumerate(result.segments, 1):
                duration = segment.end_time - segment.start_time
                f.write(f"[段落 {i}]\n")
                f.write(f"  时间: {segment.start_time:.2f}s - {segment.end_time:.2f}s (时长: {duration:.2f}s)\n")
                f.write(f"  置信度: {segment.confidence:.2%}\n")
                f.write(f"  文本: {segment.text}\n\n")
        
        print(f"\n💾 完整转录结果已保存到:")
        print(f"   {output_file}")
        
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {e}")
        logger.exception(e)


if __name__ == "__main__":
    # 运行测试
    asyncio.run(test_real_video_transcription())
