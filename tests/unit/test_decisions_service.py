"""Coverage of decisions: propose → ratify → supersede (AC #6)."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from throughline.events import MutationBus
from throughline.exceptions import TransitionError, ValidationError
from throughline.services import decisions as svc


async def test_propose_then_ratify(
    Session: async_sessionmaker[AsyncSession], bus: MutationBus
) -> None:
    async with Session() as s:
        d = await svc.propose_decision(
            s, bus, title="use HTTP", context="why", decision="HTTP", alternatives="stdio",
        )
    assert d.status == "proposed"
    assert d.ratified_at is None

    async with Session() as s:
        d = await svc.ratify_decision(s, bus, id=d.id)
    assert d.status == "ratified"
    assert d.ratified_at is not None


async def test_ratify_requires_proposed(
    Session: async_sessionmaker[AsyncSession], bus: MutationBus
) -> None:
    async with Session() as s:
        d = await svc.propose_decision(s, bus, title="t", context="c", decision="d")
    async with Session() as s:
        await svc.ratify_decision(s, bus, id=d.id)
    async with Session() as s:
        with pytest.raises(TransitionError):
            await svc.ratify_decision(s, bus, id=d.id)


async def test_supersede(
    Session: async_sessionmaker[AsyncSession], bus: MutationBus
) -> None:
    async with Session() as s:
        old = await svc.propose_decision(s, bus, title="A", context="c", decision="x")
    async with Session() as s:
        old = await svc.ratify_decision(s, bus, id=old.id)
    async with Session() as s:
        new = await svc.propose_decision(s, bus, title="B", context="c", decision="y")
    async with Session() as s:
        new = await svc.ratify_decision(s, bus, id=new.id)
    async with Session() as s:
        old = await svc.supersede_decision(s, bus, old_id=old.id, new_id=new.id)
    assert old.status == "superseded"
    assert old.superseded_by == new.id


async def test_supersede_requires_new_ratified(
    Session: async_sessionmaker[AsyncSession], bus: MutationBus
) -> None:
    async with Session() as s:
        a = await svc.propose_decision(s, bus, title="a", context="c", decision="d")
    async with Session() as s:
        a = await svc.ratify_decision(s, bus, id=a.id)
    async with Session() as s:
        b = await svc.propose_decision(s, bus, title="b", context="c", decision="d")
    async with Session() as s:
        with pytest.raises(TransitionError):
            await svc.supersede_decision(s, bus, old_id=a.id, new_id=b.id)


async def test_validation(
    Session: async_sessionmaker[AsyncSession], bus: MutationBus
) -> None:
    async with Session() as s:
        with pytest.raises(ValidationError):
            await svc.propose_decision(s, bus, title="", context="x", decision="y")
