"""图文交织渲染测试：截图插到对应转录段落下方。"""
from app.models.workspace import TranscriptIndexEntry
from app.services.workspace_service import workspace_service


def _segs():
    return [
        TranscriptIndexEntry(segment_index=0, text="开场介绍", start_time=0.0, end_time=10.0),
        TranscriptIndexEntry(segment_index=1, text="讲解图表", start_time=10.0, end_time=20.0),
        TranscriptIndexEntry(segment_index=2, text="总结", start_time=20.0, end_time=30.0),
    ]


def test_frame_interleaved_under_matching_segment():
    frames = [
        {"timestamp": 15.0, "reason": "图表特写", "frame_url": "/static/frames/v/a.jpg",
         "zoom_url": "/static/frames/v/a_zoom.jpg", "ocr_text": "SMT背离"},
    ]
    body, cited = workspace_service._render_illustrated_notes(_segs(), frames)

    # 图应紧跟在"讲解图表"(10-20s)段落之后，而不是末尾
    assert "讲解图表" in body
    idx_seg = body.index("讲解图表")
    idx_img = body.index("a.jpg")
    idx_summary = body.index("总结")
    assert idx_seg < idx_img < idx_summary  # 图在该段之后、下一段之前
    # zoom 与 OCR 都进了笔记
    assert "a_zoom.jpg" in body
    assert "SMT背离" in body
    # 引用段落包含该帧所属段落
    assert any(s.start_time == 10.0 for s in cited)


def test_frame_outside_shown_segments_goes_to_leftover():
    # 帧时间点落在所有段落之外
    frames = [{"timestamp": 999.0, "reason": "末尾图", "frame_url": "/static/frames/v/z.jpg"}]
    body, _ = workspace_service._render_illustrated_notes(_segs(), frames)
    assert "其他关键画面" in body
    assert "z.jpg" in body


def test_no_segments_falls_back_to_plain_frame_list():
    frames = [{"timestamp": 5.0, "reason": "x", "frame_url": "/static/frames/v/a.jpg"}]
    body, cited = workspace_service._render_illustrated_notes([], frames)
    assert "a.jpg" in body
    assert cited == []


def test_embed_frame_placeholders_replaces_with_real_blocks():
    frames = [
        {"timestamp": 10.0, "reason": "概念图", "frame_url": "/static/frames/v/a.jpg",
         "zoom_url": None, "ocr_text": ""},
        {"timestamp": 20.0, "reason": "代码图", "frame_url": "/static/frames/v/b.jpg",
         "zoom_url": "/static/frames/v/b_zoom.jpg", "ocr_text": "import x"},
    ]
    md = "## 概念\n讲到概念。\n[[FRAME:F0]]\n## 代码\n讲到代码。\n[[frame: 1]]\n## 无图主题\n纯文字。"
    out = workspace_service._embed_frame_placeholders(md, frames)

    assert "[[FRAME" not in out and "[[frame" not in out  # 占位符都被替换
    assert "a.jpg" in out and "b.jpg" in out
    assert "b_zoom.jpg" in out  # zoom 跟着进来
    assert "import x" in out    # OCR 跟着进来
    # a.jpg 出现在"代码"小标题之前（位置正确）
    assert out.index("a.jpg") < out.index("## 代码")


def test_embed_drops_out_of_range_placeholder():
    frames = [{"timestamp": 1.0, "reason": "x", "frame_url": "/static/frames/v/a.jpg"}]
    out = workspace_service._embed_frame_placeholders("text [[FRAME:F9]] end", frames)
    assert "[[FRAME" not in out  # 越界编号被移除，不报错
    assert "a.jpg" not in out
