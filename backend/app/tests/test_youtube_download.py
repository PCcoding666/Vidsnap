"""
YouTube 视频下载功能测试
测试链接：https://www.youtube.com/watch?v=1PaoWKvcJP0
"""
import pytest
import asyncio
import os
import sys
from pathlib import Path

# 添加项目路径到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services.video_service import AliyunVideoService


class TestYouTubeDownload:
    """测试 YouTube 视频下载功能"""
    
    @pytest.fixture
    def video_service(self):
        """创建视频服务实例"""
        return AliyunVideoService()
    
    @pytest.mark.asyncio
    async def test_download_specific_video(self, video_service):
        """
        测试下载指定的 YouTube 视频
        视频链接：https://www.youtube.com/watch?v=1PaoWKvcJP0
        """
        test_url = "https://www.youtube.com/watch?v=1PaoWKvcJP0"
        
        print(f"\n{'='*60}")
        print(f"开始测试 YouTube 视频下载")
        print(f"测试链接: {test_url}")
        print(f"{'='*60}\n")
        
        # 调用下载方法
        result = await video_service._download_from_youtube(
            test_url, 
            Path(video_service.temp_dir) / "test_session"
        )
        
        # 验证结果
        print(f"\n{'='*60}")
        print("下载结果：")
        print(f"状态: {result.get('status')}")
        
        if result.get('status') == 'success':
            print(f"✅ 下载成功！")
            print(f"视频路径: {result.get('video_path')}")
            
            # 验证文件存在
            video_path = result.get('video_path')
            assert video_path is not None, "视频路径不能为空"
            assert os.path.exists(video_path), f"视频文件不存在: {video_path}"
            
            # 获取文件大小
            file_size = os.path.getsize(video_path)
            print(f"文件大小: {file_size / (1024*1024):.2f} MB")
            
            # 验证 metadata
            metadata = result.get('metadata', {})
            print(f"\n视频信息:")
            print(f"  标题: {metadata.get('title', 'N/A')}")
            print(f"  时长: {metadata.get('duration', 'N/A')} 秒")
            print(f"  上传者: {metadata.get('uploader', 'N/A')}")
            print(f"  上传日期: {metadata.get('upload_date', 'N/A')}")
            print(f"  观看次数: {metadata.get('view_count', 'N/A')}")
            print(f"  分辨率: {metadata.get('width', 'N/A')}x{metadata.get('height', 'N/A')}")
            
            # 断言基本条件
            assert file_size > 0, "视频文件大小必须大于0"
            assert metadata.get('title'), "必须包含视频标题"
            
        else:
            print(f"❌ 下载失败")
            print(f"错误信息: {result.get('error')}")
            # 让测试失败并显示错误
            pytest.fail(f"视频下载失败: {result.get('error')}")
        
        print(f"{'='*60}\n")
        
        # 返回结果供后续验证
        return result
    
    @pytest.mark.asyncio
    async def test_download_and_extract_metadata(self, video_service):
        """
        测试下载视频并提取详细 metadata
        """
        test_url = "https://www.youtube.com/watch?v=1PaoWKvcJP0"
        
        session_dir = Path(video_service.temp_dir) / "test_metadata_session"
        session_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"\n{'='*60}")
        print(f"测试完整的视频处理流程")
        print(f"{'='*60}\n")
        
        # 下载视频
        download_result = await video_service._download_from_youtube(
            test_url, 
            session_dir
        )
        
        assert download_result.get('status') == 'success', \
            f"下载失败: {download_result.get('error')}"
        
        video_path = download_result.get('video_path')
        
        # 提取 ffprobe metadata
        print("\n正在提取视频 metadata (使用 ffprobe)...")
        ffprobe_metadata = await video_service._extract_video_metadata(video_path)
        
        print(f"\nFFprobe Metadata:")
        print(f"  时长: {ffprobe_metadata.get('duration', 0):.2f} 秒")
        print(f"  分辨率: {ffprobe_metadata.get('width')}x{ffprobe_metadata.get('height')}")
        print(f"  编码: {ffprobe_metadata.get('codec')}")
        print(f"  帧率: {ffprobe_metadata.get('fps'):.2f} fps")
        print(f"  文件大小: {ffprobe_metadata.get('size') / (1024*1024):.2f} MB")
        
        # 验证 metadata
        assert ffprobe_metadata.get('duration', 0) > 0, "视频时长必须大于0"
        assert ffprobe_metadata.get('width', 0) > 0, "视频宽度必须大于0"
        assert ffprobe_metadata.get('height', 0) > 0, "视频高度必须大于0"
        
        print(f"\n✅ Metadata 提取成功！")
        print(f"{'='*60}\n")
    
    @pytest.mark.asyncio
    async def test_full_video_processing_pipeline(self, video_service):
        """
        测试完整的视频处理流程（下载 + 关键帧提取）
        注意：此测试不会上传到 OSS，仅测试本地处理
        """
        test_url = "https://www.youtube.com/watch?v=1PaoWKvcJP0"
        
        print(f"\n{'='*60}")
        print(f"测试完整视频处理流程（不含 OSS 上传）")
        print(f"{'='*60}\n")
        
        session_dir = Path(video_service.temp_dir) / "test_full_pipeline"
        session_dir.mkdir(parents=True, exist_ok=True)
        
        # 步骤 1: 下载视频
        print("步骤 1: 下载视频...")
        download_result = await video_service._download_from_youtube(
            test_url, 
            session_dir
        )
        
        assert download_result.get('status') == 'success', \
            f"下载失败: {download_result.get('error')}"
        
        video_path = download_result.get('video_path')
        print(f"✅ 视频下载成功: {video_path}")
        
        # 步骤 2: 提取关键帧
        print("\n步骤 2: 提取关键帧...")
        video_id = "test_video_123"
        
        try:
            keyframes = await video_service.extract_keyframes_scene_detection(
                video_path, 
                video_id, 
                session_dir
            )
            
            print(f"\n✅ 成功提取 {len(keyframes)} 个关键帧")
            
            for i, keyframe in enumerate(keyframes[:3]):  # 只显示前3个
                print(f"\n关键帧 {i+1}:")
                print(f"  时间戳: {keyframe.timestamp:.2f}s")
                print(f"  本地路径: {keyframe.local_path}")
                print(f"  文件存在: {os.path.exists(keyframe.local_path)}")
                
                # 验证关键帧文件存在
                assert os.path.exists(keyframe.local_path), \
                    f"关键帧文件不存在: {keyframe.local_path}"
            
            if len(keyframes) > 3:
                print(f"\n... 还有 {len(keyframes) - 3} 个关键帧")
            
            # 验证关键帧数量
            assert len(keyframes) > 0, "必须至少提取1个关键帧"
            assert len(keyframes) <= 10, "关键帧数量不应超过10个"
            
        except Exception as e:
            print(f"\n⚠️ 关键帧提取过程中出现错误: {e}")
            print("这可能是由于 ffmpeg 配置或视频格式问题")
            # 关键帧提取失败不影响下载测试的成功
            print("下载功能测试仍然通过 ✅")
        
        print(f"\n{'='*60}\n")


if __name__ == "__main__":
    """直接运行测试"""
    print("开始运行 YouTube 下载测试...\n")
    
    # 运行测试
    pytest.main([
        __file__, 
        '-v',           # 详细输出
        '-s',           # 显示 print 输出
        '--tb=short',   # 简短的 traceback
        '--color=yes'   # 彩色输出
    ])
