"""Coverage of explicit append_log + auto-audit."""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from throughline.db.models import ExecutionLog
from throughline.events import MutationBus
from throughline.exceptions import NotFoundError, ValidationError
from throughline.services import log as svc
from throughline.services import packages as pkg_svc


async def test_append_log_auto_audit_on_create(
    Session: async_sessionmaker[AsyncSession], bus: MutationBus
) -> None:
    async with Session() as s:
        await pkg_svc.create_package(
            s, bus, id="L", title="t", goal="g", actor="human"
        )
    async with Session() as s:
        rows = (await s.execute(select(ExecutionLog))).scalars().all()
    assert len(rows) == 1
    assert rows[0].actor == "human"
    assert "created" in rows[0].entry


async def test_append_log_explicit_entry(
    Session: async_sessionmaker[AsyncSession], bus: MutationBus
) -> None:
    async with Session() as s:
        await pkg_svc.create_package(
            s, bus, id="L2", title="t", goal="g", actor="human"
        )
    async with Session() as s:
        row = await svc.append_log(
            s, bus, package_id="L2", entry="started spike", actor="agent"
        )
    assert row.actor == "agent"
    assert row.entry == "started spike"


async def test_append_log_unknown_package(
    Session: async_sessionmaker[AsyncSession], bus: MutationBus
) -> None:
    async with Session() as s:
        with pytest.raises(NotFoundError):
            await svc.append_log(
                s, bus, package_id="missing", entry="x", actor="human"
            )


async def test_append_log_empty_rejected(
    Session: async_sessionmaker[AsyncSession], bus: MutationBus
) -> None:
    async with Session() as s:
        await pkg_svc.create_package(
            s, bus, id="L3", title="t", goal="g", actor="human"
        )
    async with Session() as s:
        with pytest.raises(ValidationError):
            await svc.append_log(s, bus, package_id="L3", entry="  ", actor="human")
