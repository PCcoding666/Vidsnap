"""
完整的端到端视频处理管道测试
包含: YouTube下载 -> 关键帧提取 -> OSS上传 -> SenseVoice转录 -> Qwen3-VL-Flash总结
"""
import os
import sys
import pytest
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services.llm_service import llm_service
from app.services.pipeline_service import pipeline
from app.core.logging import logger


class TestQwenVLService:
    """测试 Qwen VL 服务"""
    
    @pytest.mark.asyncio
    async def test_qwen_service_availability(self):
        """测试 Qwen VL 服务可用性"""
        logger.info("=" * 80)
        logger.info("测试 1: Qwen VL 服务可用性检查")
        logger.info("=" * 80)
        
        # 检查 API 密钥
        api_key = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
        assert api_key, "QWEN_API_KEY 或 DASHSCOPE_API_KEY 环境变量未设置"
        logger.info(f"✓ API 密钥已设置: {api_key[:10]}...")
        
        # 检查服务可用性
        is_available = llm_service.is_available()
        assert is_available, "Qwen VL 服务不可用"
        logger.info("✓ Qwen VL 服务可用")
        
        logger.info("测试 1 通过!\n")
    
    @pytest.mark.asyncio
    async def test_keyframe_description_generation(self):
        """测试单个关键帧描述生成"""
        logger.info("=" * 80)
        logger.info("测试 2: 关键帧描述生成")
        logger.info("=" * 80)
        
        # 跳过条件：服务不可用
        if not llm_service.is_available():
            pytest.skip("Qwen VL 服务不可用")
        
        # 使用一个测试图片 URL (OSS 公共图片)
        # 注意：这里需要替换为实际的 OSS 图片 URL
        test_image_url = "https://dashscope.oss-cn-beijing.aliyuncs.com/images/dog_and_girl.jpeg"
        context = "这是一个测试上下文，用于描述关键帧。"
        
        logger.info(f"测试图片 URL: {test_image_url}")
        logger.info(f"上下文: {context}")
        
        # 调用关键帧分析
        description = await llm_service.analyze_keyframe(test_image_url, context)
        
        # 验证结果
        assert description is not None, "关键帧描述生成失败"
        assert len(description) > 0, "关键帧描述为空"
        
        logger.info(f"✓ 关键帧描述生成成功")
        logger.info(f"描述长度: {len(description)} 字符")
        logger.info(f"描述内容: {description[:200]}...")
        logger.info("测试 2 通过!\n")


class TestCompletePipeline:
    """测试完整的视频处理管道"""
    
    @pytest.mark.asyncio
    async def test_full_video_summarization(self):
        """测试完整视频总结（使用模拟数据）"""
        logger.info("=" * 80)
        logger.info("测试 3: 完整视频总结（模拟数据）")
        logger.info("=" * 80)
        
        # 跳过条件：服务不可用
        if not llm_service.is_available():
            pytest.skip("Qwen VL 服务不可用")
        
        # 创建模拟的关键帧和转录数据
        from app.models.analysis import KeyframeMetadata, TranscriptMetadata, TranscriptSegment
        
        # 模拟关键帧
        keyframes = [
            KeyframeMetadata(
                frame_id=0,
                timestamp=0.0,
                oss_image_url="https://dashscope.oss-cn-beijing.aliyuncs.com/images/dog_and_girl.jpeg",
                scene_description="初始场景"
            ),
            KeyframeMetadata(
                frame_id=1,
                timestamp=30.0,
                oss_image_url="https://dashscope.oss-cn-beijing.aliyuncs.com/images/dog_and_girl.jpeg",
                scene_description="中间场景"
            )
        ]
        
        # 模拟转录数据
        segments = [
            TranscriptSegment(
                text="欢迎观看这个测试视频。",
                start_time=0.0,
                end_time=5.0,
                confidence=0.95
            ),
            TranscriptSegment(
                text="这是一个关于视频总结的演示。",
                start_time=5.0,
                end_time=10.0,
                confidence=0.92
            ),
            TranscriptSegment(
                text="我们将展示如何使用 AI 技术生成视频摘要。",
                start_time=10.0,
                end_time=20.0,
                confidence=0.90
            )
        ]
        
        transcription = TranscriptMetadata(
            oss_audio_url="https://example.com/audio.wav",
            language="zh-CN",
            overall_confidence=0.92,
            segments=segments
        )
        
        # 生成视频总结
        logger.info("开始生成视频总结...")
        video_summary = await llm_service.generate_video_summary(
            keyframes=keyframes,
            transcription=transcription,
            video_id="test_video_001",
            granularity="standard"
        )
        
        # 验证结果
        assert video_summary is not None, "视频总结生成失败"
        assert video_summary.brief_summary, "简要总结为空"
        assert video_summary.standard_summary, "标准总结为空"
        assert len(video_summary.keyframe_descriptions) > 0, "没有关键帧描述"
        
        logger.info(f"✓ 视频总结生成成功")
        logger.info(f"简要总结: {video_summary.brief_summary}")
        logger.info(f"标准总结长度: {len(video_summary.standard_summary)} 字符")
        logger.info(f"关键帧描述数量: {len(video_summary.keyframe_descriptions)}")
        logger.info(f"时间线段落数量: {len(video_summary.sections)}")
        logger.info("测试 3 通过!\n")
    
    @pytest.mark.asyncio
    async def test_multiple_granularities(self):
        """测试多种总结粒度"""
        logger.info("=" * 80)
        logger.info("测试 4: 多种总结粒度")
        logger.info("=" * 80)
        
        # 跳过条件：服务不可用
        if not llm_service.is_available():
            pytest.skip("Qwen VL 服务不可用")
        
        from app.models.analysis import KeyframeMetadata, TranscriptMetadata, TranscriptSegment
        
        # 模拟数据
        keyframes = [
            KeyframeMetadata(
                frame_id=0,
                timestamp=0.0,
                oss_image_url="https://dashscope.oss-cn-beijing.aliyuncs.com/images/dog_and_girl.jpeg",
                scene_description="测试场景"
            )
        ]
        
        segments = [
            TranscriptSegment(
                text="这是一个测试视频。",
                start_time=0.0,
                end_time=5.0,
                confidence=0.95
            )
        ]
        
        transcription = TranscriptMetadata(
            oss_audio_url="https://example.com/audio.wav",
            language="zh-CN",
            overall_confidence=0.95,
            segments=segments
        )
        
        # 测试不同粒度
        granularities = ["brief", "standard", "detailed"]
        
        for granularity in granularities:
            logger.info(f"测试粒度: {granularity}")
            
            summary = await llm_service.generate_video_summary(
                keyframes=keyframes,
                transcription=transcription,
                video_id=f"test_{granularity}",
                granularity=granularity
            )
            
            assert summary is not None, f"{granularity} 总结生成失败"
            assert summary.brief_summary, f"{granularity} 模式下简要总结为空"
            
            if granularity in ["standard", "detailed"]:
                assert summary.standard_summary, f"{granularity} 模式下标准总结为空"
            
            if granularity == "detailed":
                assert summary.detailed_summary, "详细模式下详细总结为空"
            
            logger.info(f"  ✓ {granularity} 模式总结长度: {len(summary.brief_summary)} 字符")
        
        logger.info("✓ 所有粒度测试通过")
        logger.info("测试 4 通过!\n")
    
    @pytest.mark.asyncio
    async def test_timeline_synchronization(self):
        """测试时间线同步"""
        logger.info("=" * 80)
        logger.info("测试 5: 时间线同步")
        logger.info("=" * 80)
        
        # 跳过条件：服务不可用
        if not llm_service.is_available():
            pytest.skip("Qwen VL 服务不可用")
        
        from app.models.analysis import KeyframeMetadata, TranscriptMetadata, TranscriptSegment
        
        # 创建多个关键帧和转录段落
        keyframes = [
            KeyframeMetadata(
                frame_id=i,
                timestamp=float(i * 20),
                oss_image_url="https://dashscope.oss-cn-beijing.aliyuncs.com/images/dog_and_girl.jpeg",
                scene_description=f"场景 {i}"
            )
            for i in range(3)
        ]
        
        segments = [
            TranscriptSegment(
                text=f"这是第 {i+1} 段内容。",
                start_time=float(i * 10),
                end_time=float((i + 1) * 10),
                confidence=0.9
            )
            for i in range(6)
        ]
        
        transcription = TranscriptMetadata(
            oss_audio_url="https://example.com/audio.wav",
            language="zh-CN",
            overall_confidence=0.9,
            segments=segments
        )
        
        # 生成总结
        summary = await llm_service.generate_video_summary(
            keyframes=keyframes,
            transcription=transcription,
            video_id="test_timeline",
            granularity="standard"
        )
        
        # 验证时间线段落
        assert summary is not None, "总结生成失败"
        assert len(summary.sections) > 0, "没有生成时间线段落"
        
        # 验证时间线的连续性
        for i, section in enumerate(summary.sections):
            assert section.start_time >= 0, f"段落 {i} 开始时间无效"
            assert section.end_time > section.start_time, f"段落 {i} 结束时间无效"
            
            logger.info(f"段落 {i+1}: {section.start_time:.1f}s - {section.end_time:.1f}s")
            logger.info(f"  标题: {section.title}")
            logger.info(f"  关键帧ID: {section.keyframe_ids}")
        
        logger.info("✓ 时间线同步正常")
        logger.info("测试 5 通过!\n")
    
    @pytest.mark.asyncio
    async def test_complete_pipeline_end_to_end(self):
        """测试完整的端到端管道（使用真实YouTube视频）"""
        logger.info("=" * 80)
        logger.info("测试 6: 完整端到端管道（YouTube视频）")
        logger.info("=" * 80)
        
        # 检查所有服务可用性
        services = pipeline.check_services_availability()
        logger.info(f"服务状态: {services}")
        
        # 跳过条件：任何服务不可用
        if not all(services.values()):
            missing_services = [k for k, v in services.items() if not v]
            pytest.skip(f"以下服务不可用: {', '.join(missing_services)}")
        
        # 测试 YouTube 视频
        youtube_url = "https://www.youtube.com/watch?v=Gdzm0-8_61c"
        
        logger.info(f"处理 YouTube 视频: {youtube_url}")
        logger.info("这个测试可能需要 5-10 分钟，请耐心等待...")
        
        # 调用完整管道
        result = await pipeline.process_video_with_summary(
            youtube_url=youtube_url,
            granularity="standard"
        )
        
        # 验证结果
        assert result["status"] == "success", f"管道处理失败: {result.get('error')}"
        assert result["video_id"], "没有生成视频ID"
        assert result["keyframes_count"] > 0, "没有提取关键帧"
        
        logger.info(f"✓ 视频处理成功")
        logger.info(f"视频ID: {result['video_id']}")
        logger.info(f"关键帧数量: {result['keyframes_count']}")
        logger.info(f"转录段落数量: {result['transcript_segments_count']}")
        logger.info(f"总结已生成: {result.get('summary_generated', False)}")
        
        # 验证元数据
        if result.get("metadata"):
            metadata = result["metadata"]
            logger.info(f"✓ 元数据已生成")
            logger.info(f"  视频OSS URL: {metadata.oss_video_url if hasattr(metadata, 'oss_video_url') else 'N/A'}")
            logger.info(f"  元数据OSS URL: {metadata.metadata_oss_url if hasattr(metadata, 'metadata_oss_url') else 'N/A'}")
        
        # 验证视频总结
        if result.get("video_summary"):
            summary = result["video_summary"]
            logger.info(f"✓ 视频总结已生成")
            logger.info(f"  简要总结: {summary.brief_summary if hasattr(summary, 'brief_summary') else summary.get('brief_summary', 'N/A')}")
            logger.info(f"  标准总结长度: {len(summary.standard_summary) if hasattr(summary, 'standard_summary') else len(summary.get('standard_summary', ''))}")
            logger.info(f"  关键帧描述数量: {len(summary.keyframe_descriptions) if hasattr(summary, 'keyframe_descriptions') else len(summary.get('keyframe_descriptions', []))}")
            logger.info(f"  时间线段落数量: {len(summary.sections) if hasattr(summary, 'sections') else len(summary.get('sections', []))}")
        
        logger.info("测试 6 通过!\n")
        logger.info("=" * 80)
        logger.info("所有测试完成!")
        logger.info("=" * 80)


class TestServiceIntegration:
    """测试服务集成"""
    
    @pytest.mark.asyncio
    async def test_services_availability(self):
        """测试所有服务的可用性"""
        logger.info("=" * 80)
        logger.info("服务可用性检查")
        logger.info("=" * 80)
        
        services = pipeline.check_services_availability()
        
        for service_name, available in services.items():
            status = "✓ 可用" if available else "✗ 不可用"
            logger.info(f"{service_name}: {status}")
        
        logger.info("=" * 80)


if __name__ == "__main__":
    # 运行所有测试
    pytest.main([__file__, "-v", "-s", "--tb=short"])
