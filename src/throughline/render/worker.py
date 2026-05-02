"""Render worker — drain-quiet debouncer that regenerates state.md + active-context.md."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from throughline.events import MutationBus
from throughline.render.active_context_md import render_active_context_md
from throughline.render.atomic import write_atomic
from throughline.render.state_md import render_state_md

logger = logging.getLogger(__name__)

STATE_FILE = "state.md"
ACTIVE_CONTEXT_FILE = "active-context.md"


async def render_all(
    sessionmaker: async_sessionmaker[AsyncSession], docs_dir: Path
) -> None:
    """Read DB, regenerate both snapshot files atomically."""
    async with sessionmaker() as s:
        state = await render_state_md(s)
        active = await render_active_context_md(s)
    write_atomic(docs_dir / STATE_FILE, state)
    write_atomic(docs_dir / ACTIVE_CONTEXT_FILE, active)


async def render_worker(
    bus: MutationBus,
    sessionmaker: async_sessionmaker[AsyncSession],
    docs_dir: Path,
    debounce_s: float,
) -> None:
    """Drain-quiet loop: wait for first signal, then debounce until queue is silent."""
    while True:
        await bus.queue.get()  # block on first signal
        # quiesce
        while True:
            try:
                await asyncio.wait_for(bus.queue.get(), timeout=debounce_s)
            except asyncio.TimeoutError:
                break
        try:
            await render_all(sessionmaker, docs_dir)
        except Exception:  # never let a render bug freeze mutations
            logger.exception("render_worker: render failed")
