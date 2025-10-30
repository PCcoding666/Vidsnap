#!/usr/bin/env python3
"""
Supabase 数据持久化验证脚本

验证 Supabase 中的以下数据：
1. 用户认证数据 (profiles)
2. 用户配额数据 (user_quotas)
3. 视频记录数据 (videos)
4. 关键帧数据 (keyframes)
5. 转录段落数据 (transcript_segments)
6. 视频总结数据 (video_summaries)

使用方法:
  python verify_supabase_persistence.py
  python verify_supabase_persistence.py --user-id <user_id>
  python verify_supabase_persistence.py --video-id <video_id>
"""

import sys
import os
import argparse
from pathlib import Path
from typing import Optional

# 配置路径
project_root = Path(__file__).parent.parent.parent.parent
backend_path = project_root / "backend"
sys.path.insert(0, str(backend_path))

# 导入服务
from app.services.supabase_service import supabase_service
from app.core.config import settings


def print_header(title: str):
    """打印段落标题"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def print_success(msg: str):
    """打印成功信息"""
    print(f"✅ {msg}")


def print_error(msg: str):
    """打印错误信息"""
    print(f"❌ {msg}")


def print_info(msg: str):
    """打印信息"""
    print(f"ℹ️  {msg}")


def print_table_header(columns, widths):
    """打印表格头部"""
    header = " | ".join(col.ljust(width) for col, width in zip(columns, widths))
    print(header)
    print("-" * len(header))


def print_table_row(values, widths):
    """打印表格行"""
    row = " | ".join(str(val).ljust(width) for val, width in zip(values, widths))
    print(row)


def verify_connection():
    """验证 Supabase 连接"""
    print_header("1. 验证 Supabase 连接")
    
    # 检查配置
    if settings.SUPABASE_URL:
        print(f"SUPABASE_URL: {settings.SUPABASE_URL[:50]}...")
    else:
        print_error("SUPABASE_URL 未设置")
        return False
    
    if settings.SUPABASE_ANON_KEY:
        print(f"SUPABASE_ANON_KEY: {settings.SUPABASE_ANON_KEY[:40]}...")
    else:
        print_error("SUPABASE_ANON_KEY 未设置")
        return False
    
    if settings.SUPABASE_SERVICE_KEY:
        print(f"SUPABASE_SERVICE_KEY: {settings.SUPABASE_SERVICE_KEY[:40]}...")
    else:
        print_error("SUPABASE_SERVICE_KEY 未设置")
        return False
    
    print()
    
    if not supabase_service.is_available():
        print_error("Supabase 服务不可用")
        return False
    
    print_success("Supabase 服务已启用")
    
    # 测试数据库连接
    try:
        admin_client = supabase_service.admin_client
        if admin_client is None:
            print_error("管理员客户端未初始化")
            return False
            
        response = admin_client.table("schema_versions").select("*").execute()
        print_success("数据库连接成功 (schema_versions 表可访问)")
        return True
    except Exception as e:
        print_error(f"数据库连接失败: {e}")
        return False


def verify_users(user_id: Optional[str] = None):
    """验证用户数据"""
    print_header("2. 验证用户认证数据")
    
    if not supabase_service.is_available():
        print_error("Supabase 服务不可用")
        return False
    
    try:
        admin_client = supabase_service.admin_client
        if admin_client is None:
            print_error("管理员客户端未初始化")
            return False
        
        query = admin_client.table("profiles").select("*")
        if user_id:
            query = query.eq("id", user_id)
        
        response = query.execute()
        users = response.data
        
        if not users:
            print_error("未找到用户数据")
            return False
        
        print_success(f"找到 {len(users)} 个用户")
        
        # 打印表格
        columns = ["用户ID", "邮箱", "用户名", "订阅等级", "创建时间"]
        widths = [36, 25, 15, 12, 19]
        print_table_header(columns, widths)
        
        for user in users:
            created_at = str(user.get("created_at", ""))[:19] if user.get("created_at") else ""
            print_table_row([
                str(user.get("id", ""))[:36],
                str(user.get("email", ""))[:25],
                str(user.get("username", ""))[:15],
                str(user.get("subscription_tier", ""))[:12],
                created_at[:19]
            ], widths)
        
        print()
        return True
    except Exception as e:
        print_error(f"查询用户数据失败: {e}")
        return False


def verify_quotas(user_id: Optional[str] = None):
    """验证配额数据"""
    print_header("3. 验证用户配额数据")
    
    if not supabase_service.is_available():
        print_error("Supabase 服务不可用")
        return False
    
    try:
        admin_client = supabase_service.admin_client
        if admin_client is None:
            print_error("管理员客户端未初始化")
            return False
        
        query = admin_client.table("user_quotas").select("*")
        if user_id:
            query = query.eq("user_id", user_id)
        
        response = query.execute()
        quotas = response.data
        
        if not quotas:
            print_error("未找到配额数据")
            return False
        
        print_success(f"找到 {len(quotas)} 个用户的配额记录")
        
        # 打印表格
        columns = ["用户ID", "视频限额", "已使用", "存储(MB)", "已用", "重置日期"]
        widths = [36, 10, 8, 12, 8, 19]
        print_table_header(columns, widths)
        
        for quota in quotas:
            reset_date = str(quota.get("reset_date", ""))[:19] if quota.get("reset_date") else ""
            print_table_row([
                str(quota.get("user_id", ""))[:36],
                str(quota.get("monthly_video_limit", ""))[:10],
                str(quota.get("monthly_videos_used", ""))[:8],
                str(quota.get("total_storage_mb", ""))[:12],
                str(quota.get("used_storage_mb", ""))[:8],
                reset_date[:19]
            ], widths)
        
        print()
        return True
    except Exception as e:
        print_error(f"查询配额数据失败: {e}")
        return False


def verify_videos(user_id: Optional[str] = None, video_id: Optional[str] = None):
    """验证视频数据"""
    print_header("4. 验证视频记录数据")
    
    if not supabase_service.is_available():
        print_error("Supabase 服务不可用")
        return False
    
    try:
        admin_client = supabase_service.admin_client
        if admin_client is None:
            print_error("管理员客户端未初始化")
            return False
        
        query = admin_client.table("videos").select("*")
        if user_id:
            query = query.eq("user_id", user_id)
        elif video_id:
            query = query.eq("video_id", video_id)
        
        response = query.execute()
        videos = response.data
        
        if not videos:
            print_error("未找到视频数据")
            return False
        
        print_success(f"找到 {len(videos)} 个视频记录")
        
        # 打印表格
        columns = ["视频ID", "标题", "状态", "进度", "来源", "上传时间"]
        widths = [36, 20, 12, 6, 8, 19]
        print_table_header(columns, widths)
        
        for video in videos:
            title = str(video.get("title", ""))[:20]
            upload_time = str(video.get("upload_time", ""))[:19] if video.get("upload_time") else ""
            print_table_row([
                str(video.get("video_id", ""))[:36],
                title,
                str(video.get("processing_status", ""))[:12],
                str(video.get("processing_progress", ""))[:6],
                str(video.get("source_type", ""))[:8],
                upload_time[:19]
            ], widths)
        
        print()
        
        # 详细信息
        for video in videos:
            print(f"📋 视频详情: {video.get('video_id')}")
            print(f"  标题: {video.get('title')}")
            print(f"  状态: {video.get('processing_status')} ({video.get('processing_progress')}%)")
            oss_url = str(video.get('oss_video_url', ''))
            print(f"  视频URL: {oss_url[:70]}...")
            if video.get("oss_audio_url"):
                print(f"  音频URL: {str(video.get('oss_audio_url'))[:70]}...")
            if video.get("error_message"):
                print(f"  错误信息: {video.get('error_message')}")
            print()
        
        return True
    except Exception as e:
        print_error(f"查询视频数据失败: {e}")
        return False


def verify_keyframes(video_id: Optional[str] = None):
    """验证关键帧数据"""
    print_header("5. 验证关键帧数据")
    
    if not supabase_service.is_available():
        print_error("Supabase 服务不可用")
        return False
    
    try:
        admin_client = supabase_service.admin_client
        if admin_client is None:
            print_error("管理员客户端未初始化")
            return False
        
        if video_id:
            response = admin_client.table("keyframes").select("*").eq("video_id", video_id).execute()
        else:
            response = admin_client.table("keyframes").select("*").limit(100).execute()
        
        keyframes = response.data
        
        if not keyframes:
            print_error("未找到关键帧数据")
            return False
        
        print_success(f"找到 {len(keyframes)} 个关键帧")
        
        # 按视频分组
        videos_dict = {}
        for kf in keyframes:
            vid = kf.get("video_id", "")
            if vid not in videos_dict:
                videos_dict[vid] = []
            videos_dict[vid].append(kf)
        
        # 打印分组信息
        for vid, kf_list in videos_dict.items():
            print(f"\n📹 视频 {vid}: {len(kf_list)} 个关键帧")
            
            columns = ["帧ID", "时间戳(s)", "URL (前60字)"]
            widths = [8, 12, 60]
            print_table_header(columns, widths)
            
            for kf in sorted(kf_list, key=lambda x: x.get("frame_id", 0))[:10]:
                url = str(kf.get("oss_image_url", ""))[:60]
                print_table_row([
                    str(kf.get("frame_id", ""))[:8],
                    str(kf.get("timestamp", ""))[:12],
                    url
                ], widths)
            
            if len(kf_list) > 10:
                print(f"... 还有 {len(kf_list) - 10} 个关键帧 (省略显示)\n")
        
        return True
    except Exception as e:
        print_error(f"查询关键帧数据失败: {e}")
        return False


def verify_transcripts(video_id: Optional[str] = None):
    """验证转录数据"""
    print_header("6. 验证转录段落数据")
    
    if not supabase_service.is_available():
        print_error("Supabase 服务不可用")
        return False
    
    try:
        admin_client = supabase_service.admin_client
        if admin_client is None:
            print_error("管理员客户端未初始化")
            return False
        
        # 查询转录元数据
        query = admin_client.table("transcripts").select("*")
        if video_id:
            query = query.eq("video_id", video_id)
        
        response = query.execute()
        transcripts = response.data
        
        if not transcripts:
            print_error("未找到转录元数据")
            return False
        
        print_success(f"找到 {len(transcripts)} 个转录任务")
        
        # 打印转录元数据表格
        columns = ["视频ID", "语言", "总段落数", "创建时间"]
        widths = [36, 8, 10, 19]
        print_table_header(columns, widths)
        
        for trans in transcripts:
            created_at = str(trans.get("created_at", ""))[:19] if trans.get("created_at") else ""
            print_table_row([
                str(trans.get("video_id", ""))[:36],
                str(trans.get("language", ""))[:8],
                str(trans.get("total_segments", ""))[:10],
                created_at[:19]
            ], widths)
        
        print()
        
        # 查询转录段落
        for trans in transcripts:
            vid = trans.get("video_id", "")
            seg_response = admin_client.table("transcript_segments").select("*").eq("video_id", vid).execute()
            segments = seg_response.data
            
            if segments:
                print(f"\n💬 视频 {vid}: {len(segments)} 个转录段落")
                
                columns = ["序号", "开始时间", "结束时间", "文本内容 (前50字)"]
                widths = [6, 12, 12, 50]
                print_table_header(columns, widths)
                
                for seg in sorted(segments, key=lambda x: x.get("segment_index", 0))[:5]:
                    text = str(seg.get("text", ""))[:50]
                    print_table_row([
                        str(seg.get("segment_index", ""))[:6],
                        f"{float(seg.get('start_time', 0)):.2f}"[:12],
                        f"{float(seg.get('end_time', 0)):.2f}"[:12],
                        text
                    ], widths)
                
                if len(segments) > 5:
                    print(f"... 还有 {len(segments) - 5} 个段落 (省略显示)\n")
        
        return True
    except Exception as e:
        print_error(f"查询转录数据失败: {e}")
        return False


def verify_summaries(video_id: Optional[str] = None):
    """验证视频总结数据"""
    print_header("7. 验证视频总结数据")
    
    if not supabase_service.is_available():
        print_error("Supabase 服务不可用")
        return False
    
    try:
        admin_client = supabase_service.admin_client
        if admin_client is None:
            print_error("管理员客户端未初始化")
            return False
        
        query = admin_client.table("video_summaries").select("*")
        if video_id:
            query = query.eq("video_id", video_id)
        
        response = query.execute()
        summaries = response.data
        
        if not summaries:
            print_error("未找到视频总结数据")
            return False
        
        print_success(f"找到 {len(summaries)} 个视频总结")
        
        # 按视频分组
        videos_dict = {}
        for summary in summaries:
            vid = summary.get("video_id", "")
            if vid not in videos_dict:
                videos_dict[vid] = []
            videos_dict[vid].append(summary)
        
        # 打印分组信息
        for vid, summary_list in videos_dict.items():
            print(f"\n📝 视频 {vid}: {len(summary_list)} 种粒度的总结")
            
            for summary in summary_list:
                summary_type = summary.get("summary_type", "")
                content = str(summary.get("content", ""))
                print(f"\n  总结类型: {summary_type}")
                print(f"  模型: {summary.get('model_used', '')}")
                print(f"  内容 (前200字):")
                print(f"  {content[:200]}...")
        
        print()
        return True
    except Exception as e:
        print_error(f"查询视频总结数据失败: {e}")
        return False


def print_summary():
    """打印验证总结"""
    print_header("验证总结")
    print("\n✅ 验证过程完成！")
    print("\n如果上述所有步骤都成功，说明 Supabase 数据持久化工作正常。")
    print("如果某些步骤显示 ❌，请检查：")
    print("  1. Supabase 连接配置是否正确")
    print("  2. 数据库中是否有对应的数据")
    print("  3. API 密钥是否有过期或权限问题\n")


def main():
    parser = argparse.ArgumentParser(
        description="Supabase 数据持久化验证工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  验证所有数据:
    python verify_supabase_persistence.py
  
  验证特定用户的数据:
    python verify_supabase_persistence.py --user-id <user_id>
  
  验证特定视频的数据:
    python verify_supabase_persistence.py --video-id <video_id>
        """
    )
    
    parser.add_argument("--user-id", type=str, help="用户ID (可选)")
    parser.add_argument("--video-id", type=str, help="视频ID (可选)")
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("  Supabase 数据持久化验证工具")
    print("="*70)
    
    # 基础验证
    if not verify_connection():
        print_error("\n无法连接到 Supabase，停止验证")
        return
    
    # 用户数据
    verify_users(args.user_id)
    
    # 配额数据
    verify_quotas(args.user_id)
    
    # 视频数据
    verify_videos(args.user_id, args.video_id)
    
    # 关键帧数据
    verify_keyframes(args.video_id)
    
    # 转录数据
    verify_transcripts(args.video_id)
    
    # 总结数据
    verify_summaries(args.video_id)
    
    # 打印总结
    print_summary()


if __name__ == "__main__":
    main()
