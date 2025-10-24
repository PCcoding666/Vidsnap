"""
测试 Paraformer-v2 语音识别服务
"""
import sys
import os
import asyncio

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from app.services.paraformer_service import paraformer_service
from app.core.logging import logger


async def test_paraformer_transcription():
    """测试 Paraformer 转录功能"""
    
    print("\n" + "=" * 80)
    print("测试 Paraformer-v2 语音识别服务")
    print("=" * 80)
    
    # 检查服务是否可用
    if not paraformer_service.is_available():
        print("\n❌ Paraformer 服务不可用")
        print("请确保已设置以下环境变量之一:")
        print("  - TRANSCRIPT_SERVICE_API_KEY")
        print("  - QWEN_API_KEY")
        print("  - DASHSCOPE_API_KEY")
        return
    
    print("\n✅ Paraformer 服务已初始化")
    
    # 测试音频URL (使用阿里云官方示例)
    test_audio_url = "https://dashscope.oss-cn-beijing.aliyuncs.com/samples/audio/paraformer/hello_world_female2.wav"
    
    print(f"\n📝 测试音频: {test_audio_url}")
    print("   (阿里云官方示例音频)")
    
    print("\n⏳ 开始转录...")
    print("   - 模型: Paraformer-v2")
    print("   - 说话人分离: 启用")
    print("   - 词级时间戳: 启用")
    
    try:
        # 调用转录服务
        result = await paraformer_service.transcribe_file(
            audio_url=test_audio_url,
            language="auto",
            enable_diarization=True  # 启用说话人分离
        )
        
        if result:
            print("\n" + "=" * 80)
            print("✅ 转录成功!")
            print("=" * 80)
            
            print(f"\n📊 转录统计:")
            print(f"   - 段落数量: {len(result.segments)}")
            print(f"   - 说话人数: {result.speaker_count}")
            print(f"   - 置信度: {result.confidence:.2%}")
            print(f"   - 文本长度: {len(result.full_text)} 字符")
            
            print(f"\n📄 完整文本:")
            print(f"   {result.full_text}")
            
            if result.segments:
                print(f"\n📝 详细段落 (前 20 段):")
                print("-" * 80)
                
                for i, segment in enumerate(result.segments[:20], 1):
                    duration = segment.end_time - segment.start_time
                    print(f"\n[段落 {i}]")
                    print(f"  时间: {segment.start_time:.2f}s - {segment.end_time:.2f}s (时长: {duration:.2f}s)")
                    print(f"  置信度: {segment.confidence:.2%}")
                    print(f"  文本: {segment.text}")
                
                if len(result.segments) > 20:
                    print(f"\n... 还有 {len(result.segments) - 20} 个段落未显示 ...")
            
            print("\n" + "=" * 80)
            print("测试完成!")
            print("=" * 80)
            
        else:
            print("\n❌ 转录失败")
            print("请查看日志了解详细错误信息")
            
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {e}")
        logger.exception(e)


if __name__ == "__main__":
    # 运行测试
    asyncio.run(test_paraformer_transcription())
