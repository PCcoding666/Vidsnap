"""
测试聊天服务的上下文传递机制
验证关键帧、转录文本、视频元数据和AI总结是否正确传递给VL模型
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.services.chat_service import video_chat_service
from app.services.supabase_service import supabase_service
from app.core.logging import logger


async def test_context_compilation():
    """测试上下文编译功能"""
    print("\n" + "="*60)
    print("测试 1: Supabase 上下文编译")
    print("="*60)
    
    # 测试视频ID（请替换为实际的视频ID）
    test_video_id = "test_video_123"
    
    if supabase_service.is_available():
        compiled = supabase_service.get_compiled_metadata(test_video_id)
        if compiled:
            print(f"✅ 成功编译视频上下文:")
            print(f"  - 关键帧数量: {len(compiled.get('keyframes', []))}")
            print(f"  - 转录段落数量: {len(compiled.get('transcript', {}).get('segments', []))}")
            print(f"  - 视频标题: {compiled.get('video', {}).get('title')}")
            print(f"  - AI总结类型: {list(compiled.get('summaries', {}).keys())}")
        else:
            print(f"⚠️  未找到视频 {test_video_id} 的数据")
    else:
        print("⚠️  Supabase 服务不可用")


async def test_session_auto_load():
    """测试会话自动加载上下文"""
    print("\n" + "="*60)
    print("测试 2: 会话自动加载上下文")
    print("="*60)
    
    test_video_id = "test_video_123"
    
    # 测试仅传入video_id（不传metadata）
    result = video_chat_service.start_session(
        video_id=test_video_id,
        metadata=None  # 不传metadata，应自动从Supabase加载
    )
    
    if result.get("status") == "success":
        session_id = result["session_id"]
        print(f"✅ 会话创建成功: {session_id}")
        print(f"  - 关键帧数量: {result['keyframes_count']}")
        print(f"  - 转录段落数量: {result['transcript_segments_count']}")
        
        # 检查会话内容
        session = video_chat_service.get_session(session_id)
        if session:
            print(f"  - 视频元数据已加载: {bool(session.video_meta)}")
            print(f"  - AI总结已加载: {bool(session.summaries)}")
            if session.video_meta:
                print(f"    视频标题: {session.video_meta.get('title')}")
            if session.summaries:
                print(f"    总结类型: {list(session.summaries.keys())}")
    else:
        print(f"❌ 会话创建失败: {result.get('error')}")


async def test_context_in_qa():
    """测试问答时的上下文传递"""
    print("\n" + "="*60)
    print("测试 3: 问答中的上下文传递")
    print("="*60)
    
    test_video_id = "test_video_123"
    
    # 创建会话
    result = video_chat_service.start_session(
        video_id=test_video_id,
        metadata=None
    )
    
    if result.get("status") == "success":
        session_id = result["session_id"]
        
        # 提问测试
        question = "这个视频的主要内容是什么？"
        print(f"\n提问: {question}")
        
        qa_result = await video_chat_service.ask_question(
            session_id=session_id,
            question=question,
            auto_keyframes=True
        )
        
        if qa_result.get("status") == "success":
            print(f"✅ 问答成功:")
            print(f"  - 答案长度: {len(qa_result.get('answer', ''))} 字符")
            print(f"  - 引用关键帧: {len(qa_result.get('references', {}).get('keyframe_ids', []))}")
            print(f"  - 时间范围: {len(qa_result.get('references', {}).get('time_ranges', []))}")
            print(f"\n答案预览:")
            print(f"  {qa_result.get('answer', '')[:200]}...")
        else:
            print(f"❌ 问答失败: {qa_result.get('error')}")
    else:
        print(f"❌ 会话创建失败: {result.get('error')}")


async def main():
    """主测试函数"""
    print("\n" + "="*60)
    print("视频聊天服务上下文传递测试")
    print("="*60)
    
    # 测试1: 上下文编译
    await test_context_compilation()
    
    # 测试2: 会话自动加载
    await test_session_auto_load()
    
    # 测试3: 问答上下文传递
    # await test_context_in_qa()  # 需要LLM服务可用
    
    print("\n" + "="*60)
    print("测试完成")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
