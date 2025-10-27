"""
测试聊天服务 - 完整转录文本传递
验证将完整转录文本直接传递给LLM的实现
"""
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 加载环境变量
env_path = project_root / '.env'
if env_path.exists():
    load_dotenv(env_path)
else:
    backend_env_path = project_root / 'backend' / '.env'
    if backend_env_path.exists():
        load_dotenv(backend_env_path)

from app.services.chat_service import video_chat_service
from app.core.logging import logger


async def test_full_transcript():
    """测试完整转录文本传递"""
    
    # 模拟视频元数据
    mock_metadata = {
        "transcript": {
            "oss_audio_url": "https://example.com/audio.mp3",
            "language": "zh-CN",
            "overall_confidence": 0.95,
            "segments": [
                {
                    "text": "欢迎来到编程教程。今天我们将介绍如何使用VS Code编辑器。",
                    "start_time": 0.0,
                    "end_time": 5.0,
                    "confidence": 0.96
                },
                {
                    "text": "VS Code是微软开发的一款免费的代码编辑器。",
                    "start_time": 5.0,
                    "end_time": 10.0,
                    "confidence": 0.95
                },
                {
                    "text": "它支持多种编程语言，包括Python、JavaScript、Java、C++等。",
                    "start_time": 10.0,
                    "end_time": 15.0,
                    "confidence": 0.94
                },
                {
                    "text": "VS Code还支持丰富的插件扩展，比如GitLens、Prettier、ESLint等。",
                    "start_time": 15.0,
                    "end_time": 20.0,
                    "confidence": 0.95
                },
                {
                    "text": "除了VS Code，还有其他优秀的编辑器，如Sublime Text、Atom、WebStorm等。",
                    "start_time": 20.0,
                    "end_time": 25.0,
                    "confidence": 0.93
                },
                {
                    "text": "接下来我们演示如何在VS Code中调试Python程序。",
                    "start_time": 25.0,
                    "end_time": 30.0,
                    "confidence": 0.96
                },
                {
                    "text": "首先需要安装Python扩展，然后配置launch.json文件。",
                    "start_time": 30.0,
                    "end_time": 35.0,
                    "confidence": 0.95
                },
                {
                    "text": "调试功能包括断点设置、单步执行、变量查看等。",
                    "start_time": 35.0,
                    "end_time": 40.0,
                    "confidence": 0.94
                },
                {
                    "text": "最后总结一下，VS Code是一款功能强大且易于使用的编辑器。",
                    "start_time": 40.0,
                    "end_time": 45.0,
                    "confidence": 0.96
                },
                {
                    "text": "感谢收看，下次见！",
                    "start_time": 45.0,
                    "end_time": 48.0,
                    "confidence": 0.97
                }
            ]
        },
        "keyframes": [
            {
                "frame_id": 0,
                "timestamp": 2.0,
                "oss_image_url": "https://example.com/keyframe_0.jpg",
                "scene_description": "教程封面"
            },
            {
                "frame_id": 1,
                "timestamp": 12.0,
                "oss_image_url": "https://example.com/keyframe_1.jpg",
                "scene_description": "VS Code界面展示"
            },
            {
                "frame_id": 2,
                "timestamp": 32.0,
                "oss_image_url": "https://example.com/keyframe_2.jpg",
                "scene_description": "调试配置界面"
            }
        ]
    }
    
    logger.info("=" * 60)
    logger.info("开始测试完整转录文本传递功能")
    logger.info("=" * 60)
    
    # 1. 创建会话
    logger.info("\n[步骤 1] 创建聊天会话...")
    session_result = video_chat_service.start_session(
        video_id="test_video_001",
        metadata=mock_metadata
    )
    
    if session_result["status"] != "success":
        logger.error(f"创建会话失败: {session_result.get('error')}")
        return
    
    session_id = session_result["session_id"]
    logger.info(f"✅ 会话创建成功: {session_id}")
    logger.info(f"   转录片段数: {session_result['transcript_segments_count']}")
    logger.info(f"   关键帧数: {session_result['keyframes_count']}")
    
    # 2. 验证完整文本获取
    logger.info("\n[步骤 2] 测试完整转录文本获取...")
    session = video_chat_service.get_session(session_id)
    full_text_result = video_chat_service._get_full_transcript_text(session.transcript)
    
    logger.info(f"✅ 完整文本长度: {len(full_text_result['context_text'])} 字符")
    logger.info(f"   片段索引数: {len(full_text_result['segment_indices'])}")
    logger.info(f"   时间范围数: {len(full_text_result['time_ranges'])}")
    logger.info(f"\n完整转录文本预览:")
    logger.info(f"{full_text_result['context_text'][:200]}...")
    
    # 3. 测试问题1：事实性问题（需要列举所有编辑器）
    logger.info("\n[步骤 3] 测试问题 1: 视频中提到了哪些编辑器？")
    question1 = "视频中提到了哪些编辑器？请列举所有提到的编辑器。"
    
    answer1 = await video_chat_service.ask_question(
        session_id=session_id,
        question=question1,
        auto_keyframes=False  # 不使用关键帧
    )
    
    if answer1["status"] == "success":
        logger.info(f"✅ 问题1回答成功:")
        logger.info(f"\n问题: {question1}")
        logger.info(f"\n答案:\n{answer1['answer']}")
        logger.info(f"\n引用时间范围数: {len(answer1['references']['time_ranges'])}")
    else:
        logger.error(f"❌ 问题1回答失败: {answer1.get('error')}")
    
    # 4. 测试问题2：时间定位问题
    logger.info("\n[步骤 4] 测试问题 2: 在哪里讲了调试功能？")
    question2 = "视频在哪里讲了调试功能？请给出具体的时间段。"
    
    answer2 = await video_chat_service.ask_question(
        session_id=session_id,
        question=question2,
        auto_keyframes=False
    )
    
    if answer2["status"] == "success":
        logger.info(f"✅ 问题2回答成功:")
        logger.info(f"\n问题: {question2}")
        logger.info(f"\n答案:\n{answer2['answer']}")
        logger.info(f"\n引用时间范围数: {len(answer2['references']['time_ranges'])}")
    else:
        logger.error(f"❌ 问题2回答失败: {answer2.get('error')}")
    
    # 5. 测试问题3：总结性问题
    logger.info("\n[步骤 5] 测试问题 3: 请总结视频的主要内容")
    question3 = "请总结一下这个视频的主要内容，包括讲了什么主题和重点。"
    
    answer3 = await video_chat_service.ask_question(
        session_id=session_id,
        question=question3,
        auto_keyframes=False
    )
    
    if answer3["status"] == "success":
        logger.info(f"✅ 问题3回答成功:")
        logger.info(f"\n问题: {question3}")
        logger.info(f"\n答案:\n{answer3['answer']}")
    else:
        logger.error(f"❌ 问题3回答失败: {answer3.get('error')}")
    
    # 6. 检查会话信息
    logger.info("\n[步骤 6] 检查会话信息...")
    session_info = video_chat_service.get_session_info(session_id)
    
    if session_info["status"] == "success":
        logger.info(f"✅ 会话信息:")
        logger.info(f"   历史消息数: {session_info['history_length']}")
        logger.info(f"   最近对话:")
        for msg in session_info["recent_messages"][-4:]:
            logger.info(f"     [{msg['role']}] {msg['content'][:50]}...")
    
    # 7. 结束会话
    logger.info("\n[步骤 7] 结束会话...")
    video_chat_service.end_session(session_id)
    logger.info(f"✅ 会话已结束")
    
    logger.info("\n" + "=" * 60)
    logger.info("测试完成！")
    logger.info("=" * 60)
    logger.info("\n总结：")
    logger.info("- 已移除基于关键词检索的索引方法")
    logger.info("- 现在将完整转录文本直接传递给LLM")
    logger.info("- LLM可以访问全部视频内容进行分析")
    logger.info("- 能够更准确地列举所有信息和定位时间")


if __name__ == "__main__":
    # 检查API密钥
    if not os.getenv("QWEN_API_KEY") and not os.getenv("DASHSCOPE_API_KEY"):
        logger.error("请设置 QWEN_API_KEY 或 DASHSCOPE_API_KEY 环境变量")
        sys.exit(1)
    
    # 运行测试
    asyncio.run(test_full_transcript())
