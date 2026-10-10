"""Cancellation cleanup shared by local processes and bounded model calls."""

from __future__ import annotations

import asyncio
from typing import TypeVar

T = TypeVar("T")


async def settle_task(task: asyncio.Task[T], *, cancel: bool = False) -> None:
    """Join cleanup despite repeated caller cancellation, preserving its first cause.

    The caller is already handling cancellation or a deadline and re-raises that
    cause after this returns. Cancel the child at most once; subsequent caller
    cancellation must not interrupt its resource cleanup. Cooperative cleanup
    may exceed the deadline. Retrieve any child exception without replacing the
    original cause.
    """
    if cancel and not task.done():
        task.cancel()
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
        except Exception:
            break
    if not task.cancelled():
        task.exception()
