"""ExtractFrames MVP 测试：模型选点 + 截帧 + notes artifact 引用。"""
import pytest

from app.models.workspace import TranscriptIndexEntry
from app.services import frame_service as frame_module
from app.services.frame_service import FrameService


def _index() -> list:
    return [
        TranscriptIndexEntry(segment_index=0, text="开场介绍 transformer", start_time=0.0, end_time=10.0),
        TranscriptIndexEntry(segment_index=1, text="讲解 attention 机制", start_time=10.0, end_time=22.0),
        TranscriptIndexEntry(segment_index=2, text="PyTorch 训练演示", start_time=22.0, end_time=40.0),
    ]


@pytest.mark.asyncio
async def test_model_picks_timestamps_and_extracts(tmp_path, monkeypatch):
    service = FrameService()
    video = tmp_path / "v.mp4"
    video.write_bytes(b"fake video")

    monkeypatch.setattr(frame_module.settings, "WORKSPACE_FRAMES_ENABLED", True)
    monkeypatch.setattr(frame_module.settings, "STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setattr(frame_module.llm_service, "is_available", lambda: True)

    async def fake_llm(prompt, max_tokens=600, model=None):
        # 模型挑了片段 1 和 2，时间点落在各自范围内
        return '[{"segment_index": 1, "timestamp": 15.0, "reason": "attention 核心"}, '\
               '{"segment_index": 2, "timestamp": 30.0, "reason": "训练演示"}]'

    monkeypatch.setattr(frame_module.llm_service, "_call_text_generation", fake_llm)

    extracted = []

    async def fake_extract(video_path, timestamp, order, output_dir):
        path = output_dir / f"frame_{order}_{timestamp}.jpg"
        path.write_bytes(b"jpg")
        extracted.append(timestamp)
        return str(path)

    monkeypatch.setattr(frame_module.video_service, "_extract_frame_at_timestamp", fake_extract)

    frames = await service.select_and_extract_frames(
        video_path=str(video), video_id="vid-1", transcript_index=_index(), query="给我配图笔记", max_frames=4
    )

    assert len(frames) == 2
    assert extracted == [15.0, 30.0]
    assert frames[0]["frame_url"] == "/static/frames/vid-1/frame_0_15.0.jpg"
    assert frames[0]["segment_index"] == 1
    assert frames[0]["reason"] == "attention 核心"


@pytest.mark.asyncio
async def test_clamps_out_of_range_timestamp(tmp_path, monkeypatch):
    service = FrameService()
    video = tmp_path / "v.mp4"
    video.write_bytes(b"fake")

    monkeypatch.setattr(frame_module.settings, "WORKSPACE_FRAMES_ENABLED", True)
    monkeypatch.setattr(frame_module.settings, "STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setattr(frame_module.llm_service, "is_available", lambda: True)

    async def fake_llm(prompt, max_tokens=600, model=None):
        # 模型给了越界时间点 999，应被钳制到片段范围内
        return '[{"segment_index": 0, "timestamp": 999.0, "reason": "x"}]'

    monkeypatch.setattr(frame_module.llm_service, "_call_text_generation", fake_llm)

    captured = []

    async def fake_extract(video_path, timestamp, order, output_dir):
        captured.append(timestamp)
        path = output_dir / f"f{order}.jpg"
        path.write_bytes(b"j")
        return str(path)

    monkeypatch.setattr(frame_module.video_service, "_extract_frame_at_timestamp", fake_extract)

    await service.select_and_extract_frames(
        video_path=str(video), video_id="vid", transcript_index=_index(), query="q", max_frames=1
    )

    assert captured == [10.0]  # 钳制到 segment 0 的 end_time


@pytest.mark.asyncio
async def test_falls_back_to_even_sampling_when_llm_unavailable(tmp_path, monkeypatch):
    service = FrameService()
    video = tmp_path / "v.mp4"
    video.write_bytes(b"fake")

    monkeypatch.setattr(frame_module.settings, "WORKSPACE_FRAMES_ENABLED", True)
    monkeypatch.setattr(frame_module.settings, "STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setattr(frame_module.llm_service, "is_available", lambda: False)

    async def fake_extract(video_path, timestamp, order, output_dir):
        path = output_dir / f"f{order}.jpg"
        path.write_bytes(b"j")
        return str(path)

    monkeypatch.setattr(frame_module.video_service, "_extract_frame_at_timestamp", fake_extract)

    frames = await service.select_and_extract_frames(
        video_path=str(video), video_id="vid", transcript_index=_index(), query="q", max_frames=2
    )

    assert len(frames) == 2
    assert all(f["reason"] == "均匀采样回退" for f in frames)


@pytest.mark.asyncio
async def test_disabled_returns_empty(tmp_path, monkeypatch):
    service = FrameService()
    monkeypatch.setattr(frame_module.settings, "WORKSPACE_FRAMES_ENABLED", False)
    frames = await service.select_and_extract_frames(
        video_path="x", video_id="v", transcript_index=_index(), query="q"
    )
    assert frames == []


@pytest.mark.asyncio
async def test_analyze_frame_parses_structured_json(monkeypatch):
    """analyze_frame 能从 VLM 输出里解析结构化理解。"""
    from app.services.llm_service import llm_service

    monkeypatch.setattr(llm_service, "available", True)
    monkeypatch.setattr(llm_service, "api_key", "k")

    class FakeResp:
        status_code = 200
        class output:
            class _c:
                message = {"content": '{"frame_type":"chart","is_informative":true,"ocr_text":"SMT","visual_summary":"K线对比","salient_region":[0.1,0.2,0.3,0.4]}'}
            choices = [_c]

    import app.services.llm_service as mod

    def fake_call(*a, **k):
        return FakeResp()

    monkeypatch.setattr(mod.MultiModalConversation, "call", fake_call)

    import tempfile, os as _os
    f = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    f.write(b"img"); f.close()
    try:
        result = await llm_service.analyze_frame(f.name, context="讲解SMT背离")
    finally:
        _os.remove(f.name)

    assert result["frame_type"] == "chart"
    assert result["is_informative"] is True
    assert result["salient_region"] == [0.1, 0.2, 0.3, 0.4]


@pytest.mark.asyncio
async def test_extract_keyframes_with_understanding_filters_uninformative(tmp_path, monkeypatch):
    """看图路径：丢弃 VLM 判定无信息的帧。"""
    service = FrameService()
    video = tmp_path / "v.mp4"
    video.write_bytes(b"fake")

    monkeypatch.setattr(frame_module.settings, "WORKSPACE_FRAMES_ENABLED", True)
    monkeypatch.setattr(frame_module.settings, "STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setattr(frame_module.settings, "MAX_KEYFRAME_CANDIDATES", 12)
    monkeypatch.setattr(frame_module.llm_service, "is_available", lambda: True)

    async def fake_scenes(_path):
        return [2.0, 5.0]

    monkeypatch.setattr(frame_module.video_service, "_detect_scenes_with_ffmpeg", fake_scenes)

    async def fake_extract(video_path, timestamp, order, output_dir):
        p = output_dir / f"f{order}.jpg"
        p.write_bytes(b"j")
        return str(p)

    monkeypatch.setattr(frame_module.video_service, "_extract_frame_at_timestamp", fake_extract)

    calls = []

    async def fake_analyze(image_path, context=""):
        calls.append(image_path)
        # 第一帧有信息，第二帧无信息（应被丢弃）
        if len(calls) == 1:
            return {"frame_type": "slide", "is_informative": True, "ocr_text": "标题",
                    "visual_summary": "幻灯片首页", "salient_region": None}
        return {"is_informative": False}

    monkeypatch.setattr(frame_module.llm_service, "analyze_frame", fake_analyze)

    frames = await service.extract_keyframes_with_understanding(
        video_path=str(video), video_id="v1", query="笔记", transcript_index=None
    )

    assert len(frames) == 1
    assert frames[0]["frame_type"] == "slide"
    assert frames[0]["reason"] == "幻灯片首页"  # caption 来自像素理解


@pytest.mark.asyncio
async def test_extract_keyframes_returns_empty_when_vlm_unavailable(tmp_path, monkeypatch):
    """VLM 不可用 → 看图路径返回空，交回调用方回退盲选。"""
    service = FrameService()
    video = tmp_path / "v.mp4"
    video.write_bytes(b"fake")
    monkeypatch.setattr(frame_module.settings, "WORKSPACE_FRAMES_ENABLED", True)
    monkeypatch.setattr(frame_module.llm_service, "is_available", lambda: False)

    frames = await service.extract_keyframes_with_understanding(
        video_path=str(video), video_id="v1", query="q", transcript_index=None
    )
    assert frames == []


def test_crop_salient_region_produces_zoom(tmp_path, monkeypatch):
    """zoom in：对图表帧裁剪 salient_region 生成放大特写。"""
    from PIL import Image
    monkeypatch.setattr(frame_module.settings, "STORAGE_DIR", str(tmp_path / "storage"))
    service = FrameService()
    # 造一张 400x300 测试图
    frame_dir = service._frames_dir("v1")
    src = frame_dir / "frame_000.jpg"
    Image.new("RGB", (400, 300), (10, 20, 30)).save(str(src), "JPEG")

    url = service._crop_salient_region(
        str(src), "v1", 0, [0.25, 0.25, 0.5, 0.5], "chart"
    )
    assert url == "/static/frames/v1/frame_000_zoom.jpg"
    zoom_path = frame_dir / "frame_000_zoom.jpg"
    assert zoom_path.exists()
    # 裁剪区域 0.5x0.5 = 200x150，放大≥2x，应明显大于原裁剪
    with Image.open(str(zoom_path)) as z:
        assert z.width >= 400 and z.height >= 300


def test_crop_skips_non_zoomable_type(tmp_path, monkeypatch):
    """口播帧不生成特写。"""
    from PIL import Image
    monkeypatch.setattr(frame_module.settings, "STORAGE_DIR", str(tmp_path / "storage"))
    service = FrameService()
    frame_dir = service._frames_dir("v2")
    src = frame_dir / "f.jpg"
    Image.new("RGB", (400, 300)).save(str(src), "JPEG")

    assert service._crop_salient_region(str(src), "v2", 0, [0.2, 0.2, 0.5, 0.5], "talking_head") is None
    # 区域太小也跳过
    assert service._crop_salient_region(str(src), "v2", 0, [0.1, 0.1, 0.05, 0.05], "chart") is None
    # 无区域跳过
    assert service._crop_salient_region(str(src), "v2", 0, None, "chart") is None
