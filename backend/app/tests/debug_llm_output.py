"""
快速测试 LLM 输出
"""
import os
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services.llm_service import llm_service
from app.core.logging import logger


async def test_llm_output():
    """测试 LLM 输出"""
    
    # 检查服务可用性
    if not llm_service.is_available():
        print("❌ Qwen VL 服务不可用")
        return
    
    print("✅ Qwen VL 服务可用")
    
    # 测试图片 URL
    test_image_url = "https://dashscope.oss-cn-beijing.aliyuncs.com/images/dog_and_girl.jpeg"
    context = "这是一个测试上下文。"
    
    print(f"\n测试图片: {test_image_url}")
    print(f"上下文: {context}")
    print("\n正在调用 LLM...\n")
    
    # 调用 LLM
    description = await llm_service.analyze_keyframe(test_image_url, context)
    
    # 打印结果
    print("\n" + "="*80)
    print("返回结果:")
    print("="*80)
    print(f"类型: {type(description)}")
    print(f"长度: {len(description) if description else 0}")
    print(f"内容: {description}")
    print(f"repr: {repr(description)}")
    print("="*80)
    
    # 逐字符分析
    if description:
        print("\n逐字符分析:")
        for i, char in enumerate(description[:20]):  # 只看前20个字符
            print(f"  [{i}] = {repr(char)} (ord={ord(char)})")


if __name__ == "__main__":
    asyncio.run(test_llm_output())
