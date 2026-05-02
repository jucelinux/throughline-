"""Shared fixtures: tmp SQLite DB + MutationBus per test."""
from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from throughline.db.session import build_engine, build_sessionmaker, init_db
from throughline.events import MutationBus


@pytest_asyncio.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    eng = build_engine(tmp_path / "state.db")
    await init_db(eng)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def Session(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return build_sessionmaker(engine)


@pytest_asyncio.fixture
async def bus() -> MutationBus:
    return MutationBus()
