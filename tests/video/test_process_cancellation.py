"""Cancellation must reap the local process instead of leaving it running."""

import asyncio

import pytest

from vidsnap.video.probe import FFmpegMediaPort


@pytest.mark.asyncio
async def test_cancelling_media_operation_kills_and_reaps_process(monkeypatch):
    entered = asyncio.Event()

    class Process:
        returncode = None
        killed = False
        reaped = False

        async def communicate(self):
            entered.set()
            await asyncio.Event().wait()

        def kill(self):
            self.killed = True
            self.returncode = -9

        async def wait(self):
            self.reaped = True
            return self.returncode

    process = Process()

    async def spawn(*args, **kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    running = asyncio.create_task(FFmpegMediaPort().probe("synthetic.mp4"))
    await asyncio.wait_for(entered.wait(), timeout=1)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert process.killed, "cancelled media operations must not leave FFmpeg alive"
    assert process.reaped, "the stopped process must be reaped before returning"


@pytest.mark.asyncio
async def test_repeated_cancellation_still_waits_for_process_reaping(monkeypatch):
    entered = asyncio.Event()
    reaping = asyncio.Event()
    release = asyncio.Event()

    class Process:
        returncode = None
        reaped = False

        async def communicate(self):
            entered.set()
            await asyncio.Event().wait()

        def kill(self):
            self.returncode = -9

        async def wait(self):
            reaping.set()
            await release.wait()
            self.reaped = True
            return self.returncode

    process = Process()

    async def spawn(*args, **kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    running = asyncio.create_task(FFmpegMediaPort().probe("synthetic.mp4"))
    await entered.wait()
    running.cancel()
    await reaping.wait()
    running.cancel()
    try:
        await asyncio.sleep(0)
        assert not running.done(), "repeated cancellation must not bypass process reaping"
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await running
    assert process.reaped
