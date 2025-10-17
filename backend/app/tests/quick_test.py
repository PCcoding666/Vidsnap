"""
快速测试 YouTube 下载功能
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.services.video_service import AliyunVideoService


async def main():
    """测试 YouTube 下载"""
    test_url = "https://www.youtube.com/watch?v=1PaoWKvcJP0"
    
    print("=" * 70)
    print("YouTube 视频下载测试")
    print("=" * 70)
    print(f"\n测试链接: {test_url}\n")
    
    # 创建服务实例
    service = AliyunVideoService()
    
    # 创建测试会话目录
    session_dir = Path(service.temp_dir) / "quick_test_session"
    session_dir.mkdir(parents=True, exist_ok=True)
    
    print("开始下载...\n")
    
    # 下载视频
    result = await service._download_from_youtube(test_url, session_dir)
    
    # 输出结果
    print("\n" + "=" * 70)
    print("下载结果:")
    print("=" * 70)
    
    if result.get('status') == 'success':
        print("\n✅ 下载成功！\n")
        
        video_path = result.get('video_path')
        print(f"视频路径: {video_path}")
        
        import os
        if video_path and os.path.exists(video_path):
            file_size = os.path.getsize(video_path)
            print(f"文件大小: {file_size / (1024*1024):.2f} MB")
            
            metadata = result.get('metadata', {})
            print(f"\n视频信息:")
            print(f"  📹 标题: {metadata.get('title', 'N/A')}")
            print(f"  ⏱️  时长: {metadata.get('duration', 'N/A')} 秒")
            print(f"  👤 上传者: {metadata.get('uploader', 'N/A')}")
            print(f"  📅 上传日期: {metadata.get('upload_date', 'N/A')}")
            print(f"  👁️  观看次数: {metadata.get('view_count', 'N/A'):,}")
            print(f"  📐 分辨率: {metadata.get('width', 'N/A')}x{metadata.get('height', 'N/A')}")
        else:
            print("⚠️ 视频文件路径不存在")
    else:
        print(f"\n❌ 下载失败")
        print(f"错误信息: {result.get('error')}")
    
    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
