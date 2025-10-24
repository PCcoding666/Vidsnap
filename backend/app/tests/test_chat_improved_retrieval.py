"""
测试改进后的聊天检索功能
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from app.services.chat_service import video_chat_service
from app.models.analysis import TranscriptSegment, TranscriptMetadata


def test_retrieval_improvement():
    """测试检索改进"""
    
    print("\n" + "=" * 80)
    print("测试改进后的检索功能")
    print("=" * 80)
    
    # 创建测试转录数据（使用你提供的真实数据）
    test_segments = [
        TranscriptSegment(text="And we'll roll cameras.", start_time=0.0, end_time=1.0, confidence=0.95),
        TranscriptSegment(text="Great.", start_time=1.0, end_time=2.0, confidence=0.95),
        TranscriptSegment(text="Thank you.", start_time=2.0, end_time=2.79, confidence=0.95),
        TranscriptSegment(text="Hey everyone.", start_time=2.79, end_time=3.55, confidence=0.95),
        TranscriptSegment(text="I' M Roman.", start_time=3.55, end_time=4.05, confidence=0.95),
        TranscriptSegment(text="We've been steadily improving codex to make it feel like a more capable and reliable coding collaborator.", start_time=4.05, end_time=10.64, confidence=0.95),
        TranscriptSegment(text="And for us, it's very important for codex to be everywhere you work.", start_time=10.64, end_time=14.95, confidence=0.95),
        TranscriptSegment(text="And that's why we launch an ID extension.", start_time=14.95, end_time=18.0, confidence=0.95),
        TranscriptSegment(text="You can now have codex right in your code editor, whether it's like vcode, cursor, Windsor for many others.", start_time=18.0, end_time=24.08, confidence=0.95),
        TranscriptSegment(text="And with me today, I have Gabriel engineering lead on the extension .", start_time=24.08, end_time=27.83, confidence=0.95),
        TranscriptSegment(text="to give us a quick tour.", start_time=27.83, end_time=29.21, confidence=0.95),
    ]
    
    transcript = TranscriptMetadata(
        oss_audio_url="test_url",
        language="en",
        overall_confidence=0.95,
        segments=test_segments
    )
    
    # 测试问题
    questions = [
        "Codex IDE 扩展支持哪些代码编辑器？",
        "支持哪些编辑器",
        "code editor",
        "vscode cursor windsor",
    ]
    
    for question in questions:
        print(f"\n{'─' * 80}")
        print(f"问题: {question}")
        print(f"{'─' * 80}")
        
        # 调用检索方法
        result = video_chat_service._retrieve_relevant_context(
            question,
            transcript,
            top_k=10
        )
        
        print(f"\n检索到 {len(result['segment_indices'])} 个相关片段:")
        print(f"总文本长度: {len(result['context_text'])} 字符\n")
        
        for i, time_range in enumerate(result['time_ranges'][:5], 1):  # 只显示前5个
            start_min = int(time_range['start_time']) // 60
            start_sec = int(time_range['start_time']) % 60
            end_min = int(time_range['end_time']) // 60
            end_sec = int(time_range['end_time']) % 60
            
            print(f"[{i}] [{start_min:02d}:{start_sec:02d} - {end_min:02d}:{end_sec:02d}]")
            print(f"    {time_range['text']}")
        
        if len(result['time_ranges']) > 5:
            print(f"\n... 还有 {len(result['time_ranges']) - 5} 个片段")
    
    print("\n" + "=" * 80)
    print("测试完成！")
    print("=" * 80)
    
    # 检查关键片段是否被检索到
    print("\n✅ 关键验证:")
    question = "Codex IDE 扩展支持哪些代码编辑器？"
    result = video_chat_service._retrieve_relevant_context(question, transcript, top_k=10)
    
    # 检查是否包含 [18.0 - 24.08] 这个关键片段
    target_segment = next((tr for tr in result['time_ranges'] if 18.0 <= tr['start_time'] <= 19.0), None)
    
    if target_segment:
        print("✅ 成功检索到关键答案片段:")
        print(f"   [{target_segment['start_time']:.2f}s - {target_segment['end_time']:.2f}s]")
        print(f"   '{target_segment['text']}'")
    else:
        print("❌ 未检索到关键答案片段")
        print("   期望: [18.0s - 24.08s] 包含 'vcode, cursor, Windsor'")


if __name__ == "__main__":
    test_retrieval_improvement()
