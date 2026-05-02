"""MutationBus — a thin asyncio.Queue wrapper used to signal that the DB changed.

A single payload-less signal is used (`None`); the render worker always re-reads
the full DB to produce the snapshot files, so the signal carries no detail.
"""
from __future__ import annotations

import asyncio


class MutationBus:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[None] = asyncio.Queue()

    async def signal(self) -> None:
        await self.queue.put(None)

    def signal_nowait(self) -> None:
        """Non-blocking variant for sync callers (rarely needed)."""
        self.queue.put_nowait(None)
