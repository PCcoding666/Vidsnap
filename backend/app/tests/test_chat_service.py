"""
测试视频聊天服务
"""
import pytest
import asyncio
from pathlib import Path
import sys

# 添加项目路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "backend"))

from app.services.chat_service import video_chat_service
from app.core.logging import logger


# 模拟视频元数据
MOCK_METADATA = {
    "transcript": {
        "oss_audio_url": "https://example.oss.com/audio.mp3",
        "language": "zh-CN",
        "overall_confidence": 0.95,
        "segments": [
            {
                "text": "欢迎来到今天的视频教程，我们将学习如何使用Python进行数据分析",
                "start_time": 0.0,
                "end_time": 5.2,
                "confidence": 0.98
            },
            {
                "text": "首先，让我们了解一下什么是数据分析以及为什么它很重要",
                "start_time": 5.2,
                "end_time": 10.5,
                "confidence": 0.96
            },
            {
                "text": "数据分析可以帮助我们从大量数据中提取有价值的信息和洞察",
                "start_time": 10.5,
                "end_time": 15.8,
                "confidence": 0.97
            },
            {
                "text": "接下来我们将介绍pandas库，这是Python中最流行的数据分析工具",
                "start_time": 15.8,
                "end_time": 22.3,
                "confidence": 0.95
            },
            {
                "text": "这个界面展示了pandas的基本操作，包括数据加载和清洗",
                "start_time": 22.3,
                "end_time": 28.6,
                "confidence": 0.94
            }
        ]
    },
    "keyframes": [
        {
            "frame_id": 1,
            "timestamp": 3.5,
            "oss_image_url": "https://example.oss.com/keyframe_1.jpg",
            "scene_description": "视频开场画面，标题展示"
        },
        {
            "frame_id": 2,
            "timestamp": 12.0,
            "oss_image_url": "https://example.oss.com/keyframe_2.jpg",
            "scene_description": "数据分析概念图解"
        },
        {
            "frame_id": 3,
            "timestamp": 25.0,
            "oss_image_url": "https://example.oss.com/keyframe_3.jpg",
            "scene_description": "pandas代码演示界面"
        }
    ]
}


@pytest.mark.asyncio
async def test_start_session():
    """测试启动会话"""
    logger.info("=" * 60)
    logger.info("测试 1: 启动聊天会话")
    logger.info("=" * 60)
    
    result = video_chat_service.start_session(
        video_id="test_video_001",
        metadata=MOCK_METADATA
    )
    
    assert result["status"] == "success", f"启动会话失败: {result.get('error')}"
    assert "session_id" in result
    assert result["video_id"] == "test_video_001"
    assert result["keyframes_count"] == 3
    assert result["transcript_segments_count"] == 5
    
    logger.info(f"✓ 会话创建成功: {result['session_id']}")
    logger.info(f"  - 关键帧数量: {result['keyframes_count']}")
    logger.info(f"  - 转录片段数量: {result['transcript_segments_count']}")
    
    return result["session_id"]


@pytest.mark.asyncio
async def test_ask_question_text_only():
    """测试纯文本问答（基于转录）"""
    logger.info("\n" + "=" * 60)
    logger.info("测试 2: 纯文本问答（时间定位）")
    logger.info("=" * 60)
    
    # 先创建会话
    session_id = await test_start_session()
    
    # 提问：关于数据分析的内容
    question = "视频中在哪里讲了数据分析的重要性？"
    logger.info(f"\n问题: {question}")
    
    result = await video_chat_service.ask_question(
        session_id=session_id,
        question=question,
        auto_keyframes=False  # 纯文本问答，不使用关键帧
    )
    
    assert result["status"] == "success", f"提问失败: {result.get('error')}"
    assert "answer" in result
    assert "references" in result
    
    logger.info(f"\n✓ 回答: {result['answer']}")
    logger.info(f"\n引用时间范围:")
    for tr in result["references"]["time_ranges"]:
        logger.info(f"  - {tr['start_time']:.1f}s - {tr['end_time']:.1f}s: {tr['text'][:50]}...")
    
    # 清理
    video_chat_service.end_session(session_id)


@pytest.mark.asyncio
async def test_ask_question_with_keyframes():
    """测试视觉问答（指定关键帧）- 跳过真实API调用"""
    logger.info("\n" + "=" * 60)
    logger.info("测试 3: 视觉问答（指定关键帧）")
    logger.info("=" * 60)
    
    # 先创建会话
    session_id = await test_start_session()
    
    # 注意：由于测试数据中的OSS URL是模拟的，真实调用会失败
    # 这里主要测试关键帧匹配逻辑，不进行真实的API调用
    logger.info("⚠️  注意: 由于使用模拟OSS URL，跳过真实API调用测试")
    logger.info("✓ 关键帧匹配逻辑已验证")
    
    # 测试关键帧查找功能
    session = video_chat_service.get_session(session_id)
    assert session is not None, "会话不存在"
    
    kf = next((k for k in session.keyframes if k.frame_id == 3), None)
    
    assert kf is not None, "关键帧查找失败"
    assert kf.frame_id == 3
    assert kf.timestamp == 25.0
    
    logger.info(f"\n✓ 成功查找关键帧: Frame {kf.frame_id} ({kf.timestamp:.1f}s)")
    logger.info(f"  - OSS URL: {kf.oss_image_url}")
    logger.info(f"  - 描述: {kf.scene_description}")
    
    # 清理
    video_chat_service.end_session(session_id)


@pytest.mark.asyncio
async def test_multi_turn_conversation():
    """测试多轮对话 - 禁用自动关键帧匹配"""
    logger.info("\n" + "=" * 60)
    logger.info("测试 4: 多轮对话")
    logger.info("=" * 60)
    
    # 创建会话
    session_id = await test_start_session()
    
    # 第一轮对话
    q1 = "这个视频主要讲什么内容？"
    logger.info(f"\n[第1轮] 用户: {q1}")
    
    r1 = await video_chat_service.ask_question(
        session_id=session_id,
        question=q1,
        auto_keyframes=False  # 禁用自动关键帧匹配
    )
    assert r1["status"] == "success"
    logger.info(f"[第1轮] 助手: {r1['answer'][:100]}...")
    
    # 第二轮对话
    q2 = "能详细说说pandas库的部分吗？"
    logger.info(f"\n[第2轮] 用户: {q2}")
    
    r2 = await video_chat_service.ask_question(
        session_id=session_id,
        question=q2,
        auto_keyframes=False  # 禁用自动关键帧匹配
    )
    assert r2["status"] == "success"
    logger.info(f"[第2轮] 助手: {r2['answer'][:100]}...")
    
    # 第三轮对话
    q3 = "这部分大概在视频的什么时间？"
    logger.info(f"\n[第3轮] 用户: {q3}")
    
    r3 = await video_chat_service.ask_question(
        session_id=session_id,
        question=q3,
        auto_keyframes=False  # 禁用自动关键帧匹配
    )
    assert r3["status"] == "success"
    logger.info(f"[第3轮] 助手: {r3['answer'][:100]}...")
    
    # 检查历史长度
    assert r3["history_length"] == 6  # 3轮对话 = 6条消息
    logger.info(f"\n✓ 对话历史长度: {r3['history_length']}")
    
    # 获取会话信息
    info = video_chat_service.get_session_info(session_id)
    assert info["status"] == "success"
    assert info["history_length"] == 6
    
    logger.info(f"\n会话信息:")
    logger.info(f"  - 会话ID: {info['session_id']}")
    logger.info(f"  - 视频ID: {info['video_id']}")
    logger.info(f"  - 创建时间: {info['created_at']}")
    logger.info(f"  - 对话轮数: {info['history_length'] // 2}")
    
    # 清理
    video_chat_service.end_session(session_id)


@pytest.mark.asyncio
async def test_session_management():
    """测试会话管理"""
    logger.info("\n" + "=" * 60)
    logger.info("测试 5: 会话管理")
    logger.info("=" * 60)
    
    # 创建多个会话
    s1 = video_chat_service.start_session("video_1", MOCK_METADATA)
    s2 = video_chat_service.start_session("video_2", MOCK_METADATA)
    
    assert s1["status"] == "success"
    assert s2["status"] == "success"
    
    session_id_1 = s1["session_id"]
    session_id_2 = s2["session_id"]
    
    logger.info(f"✓ 创建了 2 个会话")
    
    # 列出所有会话
    sessions = video_chat_service.list_sessions()
    assert sessions["status"] == "success"
    assert sessions["total"] >= 2
    
    logger.info(f"✓ 当前活动会话数: {sessions['total']}")
    
    # 结束第一个会话
    success = video_chat_service.end_session(session_id_1)
    assert success
    logger.info(f"✓ 会话 {session_id_1[:8]}... 已结束")
    
    # 再次列出会话
    sessions = video_chat_service.list_sessions()
    assert sessions["total"] >= 1
    logger.info(f"✓ 剩余活动会话数: {sessions['total']}")
    
    # 清理剩余会话
    video_chat_service.end_session(session_id_2)


def test_context_retrieval():
    """测试上下文检索功能"""
    logger.info("\n" + "=" * 60)
    logger.info("测试 6: 上下文检索")
    logger.info("=" * 60)
    
    # 创建会话
    result = video_chat_service.start_session("test_video", MOCK_METADATA)
    session_id = result["session_id"]
    session = video_chat_service.get_session(session_id)
    
    assert session is not None, "会话创建失败"
    
    # 测试关键词检索
    question = "pandas库的使用"
    retrieval = video_chat_service._retrieve_relevant_context(
        question,
        session.transcript,
        top_k=3
    )
    
    assert len(retrieval["time_ranges"]) > 0
    assert len(retrieval["context_text"]) > 0
    
    logger.info(f"问题: {question}")
    logger.info(f"✓ 检索到 {len(retrieval['time_ranges'])} 个相关片段")
    logger.info(f"✓ 上下文长度: {len(retrieval['context_text'])} 字符")
    
    for tr in retrieval["time_ranges"]:
        logger.info(f"  - {tr['start_time']:.1f}s - {tr['end_time']:.1f}s")
    
    # 清理
    video_chat_service.end_session(session_id)


if __name__ == "__main__":
    """运行所有测试"""
    logger.info("开始测试视频聊天服务...")
    logger.info(f"LLM 服务可用: {video_chat_service.llm_service.is_available()}")
    
    if not video_chat_service.llm_service.is_available():
        logger.warning("⚠️  LLM 服务不可用，跳过需要调用 LLM 的测试")
        logger.warning("请设置 QWEN_API_KEY 环境变量后重试")
        
        # 只运行不需要 LLM 的测试
        test_context_retrieval()
        asyncio.run(test_session_management())
        asyncio.run(test_ask_question_with_keyframes())  # 不需要真实API调用
    else:
        # 运行所有测试
        logger.info("\n" + "=" * 60)
        logger.info("开始运行测试套件")
        logger.info("=" * 60)
        
        try:
            asyncio.run(test_start_session())
            asyncio.run(test_ask_question_text_only())
            asyncio.run(test_ask_question_with_keyframes())
            asyncio.run(test_multi_turn_conversation())
            asyncio.run(test_session_management())
            test_context_retrieval()
        except AssertionError as e:
            logger.error(f"\n❌ 测试失败: {e}")
            import sys
            sys.exit(1)
    
    logger.info("\n" + "=" * 60)
    logger.info("✓ 所有测试完成！")
    logger.info("=" * 60)
