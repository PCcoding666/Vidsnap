#!/usr/bin/env python3
"""
Layer 1 数据集工具：从视频抽出全部关键帧 + 生成人工标注模板。

用途：为"针对性理解"构造帧级理解数据集。对一个视频做场景检测抽帧，
把帧落盘，并产出一份 annotation_template.json（每帧一条，字段留空待人工标注），
方便评估 AnalyzeFrame（qwen3.7-plus 逐帧理解）的准确率。

用法：
    cd backend
    PYTHONPATH=. python scripts/extract_frames_for_annotation.py <video_path> \
        [--video-id vid001] [--out datasets/frames] [--bucket slide|chart|code|talkinghead|demo]

输出：
    <out>/<video_id>/frame_XXX_<ts>s.jpg          抽出的关键帧
    <out>/<video_id>/annotation_template.json     待标注模板（Layer 1 schema）

标注字段（人工填）：
    frame_type, is_informative, ocr_text, visual_summary, salient_region,
    should_include_in_notes, redundant_with
"""
import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

# 允许 `python scripts/xxx.py` 直接运行
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.video_service import video_service  # noqa: E402


async def extract(video_path: str, video_id: str, out_dir: Path, bucket: str) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) 场景检测抽关键帧时间点（ffmpeg），退化为均匀采样
    timestamps = await video_service._detect_scenes_with_ffmpeg(video_path)
    source = "scene_detection"
    if not timestamps:
        timestamps = await video_service._uniform_sampling(video_path, 15)
        source = "uniform_sampling"
    timestamps = sorted(timestamps)

    print(f"[{video_id}] {source}: {len(timestamps)} 个关键帧时间点")

    entries = []
    for i, ts in enumerate(timestamps):
        frame_path = await video_service._extract_frame_at_timestamp(
            video_path, ts, i, out_dir
        )
        if not frame_path:
            continue
        entries.append(
            {
                "frame_id": f"{video_id}_t{ts:.2f}",
                "video_id": video_id,
                "bucket": bucket,
                "timestamp": round(ts, 2),
                "image_path": str(Path(frame_path).relative_to(out_dir.parent)),
                # ↓↓↓ 以下为人工标注字段（留空待填）↓↓↓
                "frame_type": "",          # slide|chart|code|talking_head|demo|transition|blank|other
                "is_informative": None,    # true / false
                "ocr_text": "",            # 画面里的文字/数字/代码
                "visual_summary": "",      # 一句话描述关键视觉内容
                "salient_region": None,    # [x,y,w,h] 归一化，可 zoom in 的区域；无则 null
                "should_include_in_notes": None,  # 是否值得放进笔记
                "redundant_with": None,    # 若与某帧重复，填那帧的 frame_id
            }
        )
        print(f"  - frame {i} @ {ts:.2f}s -> {Path(frame_path).name}")

    template_path = out_dir / "annotation_template.json"
    template_path.write_text(
        json.dumps(
            {
                "video_id": video_id,
                "video_path": video_path,
                "bucket": bucket,
                "keyframe_source": source,
                "frame_count": len(entries),
                "frames": entries,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n标注模板已生成: {template_path} ({len(entries)} 帧)")
    return {"video_id": video_id, "frames": len(entries), "template": str(template_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description="抽关键帧 + 生成 Layer1 标注模板")
    parser.add_argument("video_path", help="本地视频文件路径")
    parser.add_argument("--video-id", default=None, help="视频 ID（默认自动生成）")
    parser.add_argument("--out", default="datasets/frames", help="输出根目录")
    parser.add_argument(
        "--bucket",
        default="unlabeled",
        help="视频类型分桶: slide|chart|code|talking_head|demo|vlog|unlabeled",
    )
    args = parser.parse_args()

    if not Path(args.video_path).exists():
        print(f"视频不存在: {args.video_path}", file=sys.stderr)
        sys.exit(1)

    video_id = args.video_id or f"vid_{uuid.uuid4().hex[:8]}"
    out_dir = Path(args.out) / video_id
    asyncio.run(extract(args.video_path, video_id, out_dir, args.bucket))


if __name__ == "__main__":
    main()
