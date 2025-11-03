"""
调试聊天上下文传递问题
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.services.supabase_service import supabase_service
from app.services.chat_service import video_chat_service
from app.core.logging import logger


def debug_video_context(video_id: str):
    """调试视频上下文加载"""
    print("\n" + "="*70)
    print(f"调试视频上下文: {video_id}")
    print("="*70)
    
    if not supabase_service.is_available():
        print("❌ Supabase 服务不可用")
        return
    
    # 测试单独的方法
    print("\n1. 测试 get_video_by_id:")
    video = supabase_service.get_video_by_id(video_id)
    if video:
        print(f"   ✅ 视频信息: title={video.get('title')}, duration={video.get('duration')}")
    else:
        print("   ❌ 未找到视频")
    
    print("\n2. 测试 get_keyframes:")
    keyframes = supabase_service.get_keyframes(video_id)
    print(f"   关键帧数量: {len(keyframes)}")
    if keyframes:
        print(f"   第一个关键帧: {keyframes[0]}")
    
    print("\n3. 测试 get_transcript_segments:")
    segments = supabase_service.get_transcript_segments(video_id)
    print(f"   转录段落数量: {len(segments)}")
    if segments:
        print(f"   第一个段落: {segments[0]}")
        # 检查segments的完整内容
        total_text_length = sum(len(s.get("text", "")) for s in segments)
        print(f"   总文本长度: {total_text_length} 字符")
        # 显示前3个段落的文本
        print(f"\n   前3个段落的文本:")
        for i, seg in enumerate(segments[:3]):
            print(f"     [{i}] {seg.get('text', '')[:100]}...")
    else:
        print("   ⚠️ 没有转录段落!这就是问题所在!")
    
    print("\n4. 测试 get_video_summaries:")
    summaries = supabase_service.get_video_summaries(video_id)
    if summaries:
        print(f"   总结类型: {list(summaries.keys())}")
        if "standard" in summaries:
            print(f"   标准总结(前200字): {summaries['standard'][:200]}...")
    else:
        print("   ❌ 未找到总结")
    
    print("\n5. 测试 get_compiled_metadata:")
    compiled = supabase_service.get_compiled_metadata(video_id)
    if compiled:
        print(f"   ✅ 编译成功")
        print(f"   - transcript.segments: {len(compiled['transcript']['segments'])} 个")
        print(f"   - keyframes: {len(compiled['keyframes'])} 个")
        print(f"   - video.title: {compiled['video']['title']}")
        print(f"   - summaries: {list(compiled['summaries'].keys())}")
        
        # 检查segments内容
        if compiled['transcript']['segments']:
            first_seg = compiled['transcript']['segments'][0]
            print(f"   - 第一个segment: text='{first_seg['text'][:50]}...', start={first_seg['start_time']}, end={first_seg['end_time']}")
            
            # 显示完整文本的前500字符
            full_text = " ".join(s['text'] for s in compiled['transcript']['segments'])
            print(f"\n   - 完整转录文本(前500字): {full_text[:500]}...")
            print(f"   - 完整转录文本总长度: {len(full_text)} 字符")
        else:
            print("   ⚠️ compiled metadata 中 segments 为空!")
    else:
        print("   ❌ 编译失败")


async def debug_chat_session(video_id: str, question: str):
    """调试聊天会话"""
    print("\n" + "="*70)
    print(f"调试聊天会话: {question}")
    print("="*70)
    
    # 步骤 1: 启动会话
    print("\n步骤 1: 启动聊天会话...")
    session_result = video_chat_service.start_session(video_id=video_id)
    
    if session_result.get("status") != "success":
        print(f"❌ 启动会话失败: {session_result.get('error')}")
        return
    
    session_id = session_result["session_id"]
    print(f"✅ 会话启动成功: {session_id}")
    print(f"   - keyframes: {session_result['keyframes_count']}")
    print(f"   - transcript_segments: {session_result['transcript_segments_count']}")
    
    # 步骤 2: 提问
    print(f"\n步骤 2: 提问 '{question}'...")
    answer_result = await video_chat_service.ask_question(
        session_id=session_id,
        question=question
    )
    
    if answer_result.get("status") != "success":
        print(f"❌ 提问失败: {answer_result.get('error')}")
        return
    
    print(f"\n✅ 获得回答:")
    print(f"   {answer_result['answer']}")
    
    if answer_result.get('references'):
        refs = answer_result['references']
        print(f"\n引用信息:")
        print(f"   - 时间范围: {len(refs.get('time_ranges', []))} 个")
        print(f"   - 关键帧: {len(refs.get('keyframe_ids', []))} 个")


if __name__ == "__main__":
    # 使用你测试的视频ID
    test_video_id = "18ebce9f-9be4-4e85-b944-1d2d161d0430"
    
    # 测试上下文加载
    debug_video_context(test_video_id)
    
    # 测试聊天功能
    print("\n\n" + "#"*70)
    print("# 开始测试聊天功能")
    print("#"*70)
    asyncio.run(debug_chat_session(test_video_id, "这个视频介绍了什么工具?"))
