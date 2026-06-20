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
