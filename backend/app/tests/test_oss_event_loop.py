"""回归测试：OSS 上传/下载不得阻塞 asyncio 事件循环。

历史问题：同步阻塞的 oss2 SDK 调用直接跑在事件循环上，一次 255MB 上传把
整个 FastAPI 服务卡死约 10 分钟（连 GET /health 都超时）。修复方式是把阻塞调用
放进 ``asyncio.to_thread``。这些测试用一个“慢”的假 bucket 模拟阻塞上传，并在上传
进行期间用心跳协程验证事件循环仍能调度其它任务。
"""
import asyncio
import time

import pytest

from app.services import oss_service as oss_module
from app.services.oss_service import AliyunOSSService


# 模拟上传期间 oss2 同步阻塞的时长；若调用未离开事件循环，这段时间内心跳无法推进。
BLOCK_SECONDS = 0.4
# 心跳间隔；BLOCK_SECONDS 内理应推进约 BLOCK_SECONDS / HEARTBEAT_INTERVAL 次。
HEARTBEAT_INTERVAL = 0.02


class _BlockingFakeBucket:
    """同步阻塞的假 bucket，模拟慢速 oss2 SDK 调用。"""

    def __init__(self) -> None:
        self.put_calls = 0

    def put_object(self, object_key, data, headers=None):
        # 文件对象需要被读取，模拟真实 SDK 的流式上传。
        if hasattr(data, "read"):
            data.read()
        self.put_calls += 1
        time.sleep(BLOCK_SECONDS)

    def sign_url(self, method, object_key, expires, slash_safe=True):
        return f"https://signed.example/{object_key}"


def _service_with_blocking_bucket(monkeypatch) -> AliyunOSSService:
    """构造一个可用的 OSS 服务实例，绕过真实配置与网络。"""
    svc = AliyunOSSService.__new__(AliyunOSSService)
    svc.available = True
    svc.endpoint = "https://oss-cn-hangzhou.aliyuncs.com"
    svc.bucket_name = "test-bucket"
    svc.bucket = _BlockingFakeBucket()
    monkeypatch.setattr(oss_module.settings, "OSS_USE_SIGNED_URLS", True)
    monkeypatch.setattr(oss_module.settings, "OSS_SIGNED_URL_EXPIRES_SECONDS", 600)
    return svc


async def _count_heartbeats_during(coro):
    """并发运行心跳协程，返回 (coro 结果, 期间心跳推进次数)。

    若 ``coro`` 在事件循环上同步阻塞，心跳将无法推进，计数接近 0。
    """
    ticks = 0

    async def heartbeat():
        nonlocal ticks
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            ticks += 1

    hb = asyncio.create_task(heartbeat())
    try:
        result = await coro
    finally:
        hb.cancel()
        try:
            await hb
        except asyncio.CancelledError:
            pass
    return result, ticks


@pytest.mark.asyncio
async def test_upload_video_does_not_block_event_loop(tmp_path, monkeypatch):
    svc = _service_with_blocking_bucket(monkeypatch)
    video = tmp_path / "big.mp4"
    video.write_bytes(b"0" * 4096)

    url, ticks = await _count_heartbeats_during(svc.upload_video(str(video), "vid-1"))

    assert url is not None and url.startswith("https://signed.example/")
    assert svc.bucket.put_calls == 1
    # 阻塞期间心跳必须推进若干次；若上传卡住事件循环，ticks 会接近 0。
    assert ticks >= 5, f"event loop appears blocked during upload (ticks={ticks})"


@pytest.mark.asyncio
async def test_upload_metadata_does_not_block_event_loop(tmp_path, monkeypatch):
    svc = _service_with_blocking_bucket(monkeypatch)

    _, ticks = await _count_heartbeats_during(
        svc.upload_metadata({"hello": "world"}, "vid-2")
    )

    assert svc.bucket.put_calls == 1
    assert ticks >= 5, f"event loop appears blocked during metadata upload (ticks={ticks})"
