"""Verify the data layer: 5 tables, WAL active, FKs on."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


async def test_all_tables_created(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        )
        tables = {r[0] for r in rows.fetchall()}
    expected = {"packages", "decisions", "discoveries", "execution_log", "state_sections"}
    assert expected.issubset(tables), f"missing: {expected - tables}"


async def test_wal_mode_active(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        result = await conn.execute(text("PRAGMA journal_mode"))
        mode = result.scalar()
    assert mode == "wal"


async def test_foreign_keys_enforced(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        result = await conn.execute(text("PRAGMA foreign_keys"))
        on = result.scalar()
    assert on == 1


async def test_check_constraint_rejects_invalid_status(engine: AsyncEngine) -> None:
    """Sanity: CHECK on packages.status fires for unknown values."""
    from datetime import datetime, timezone

    from sqlalchemy.exc import IntegrityError

    async with engine.begin() as conn:
        try:
            await conn.execute(
                text(
                    "INSERT INTO packages (id, title, status, created_at, updated_at) "
                    "VALUES (:id, :t, :s, :n, :n)"
                ),
                {"id": "x", "t": "x", "s": "BOGUS", "n": datetime.now(timezone.utc)},
            )
            await conn.commit()
            assert False, "expected IntegrityError"
        except IntegrityError:
            pass
