"""Async engine + sessionmaker. WAL/FK pragmas attached at connect time.

Also registers datetime adapters/converters for sqlite3 — Python 3.12 deprecated
the default ones, and we always store/return timezone-aware UTC.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from throughline.db.models import Base


def _adapt_datetime(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _convert_datetime(value: bytes) -> datetime:
    parsed = datetime.fromisoformat(value.decode())
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


sqlite3.register_adapter(datetime, _adapt_datetime)
sqlite3.register_converter("timestamp", _convert_datetime)


def _attach_pragmas(engine: AsyncEngine) -> None:
    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragmas(dbapi_conn, _record):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def build_engine(db_path: Path | str) -> AsyncEngine:
    """Create an async engine for a SQLite file path; attach WAL/FK pragmas."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(url, future=True)
    _attach_pragmas(engine)
    return engine


def build_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_db(engine: AsyncEngine) -> None:
    """Create all tables on first run; idempotent."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
