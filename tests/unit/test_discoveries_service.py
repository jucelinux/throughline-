"""Coverage of discoveries: record → resolve → absorb (AC #6)."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from throughline.events import MutationBus
from throughline.exceptions import TransitionError, ValidationError
from throughline.services import decisions as decisions_svc
from throughline.services import discoveries as svc
from throughline.services import packages as packages_svc


async def test_record_resolve(
    Session: async_sessionmaker[AsyncSession], bus: MutationBus
) -> None:
    async with Session() as s:
        await packages_svc.create_package(
            s, bus, id="p1", title="t", goal="g", actor="human"
        )
    async with Session() as s:
        d = await svc.record_discovery(
            s, bus, kind="blocker", title="x", body="y", package_id="p1"
        )
    assert d.status == "open"
    async with Session() as s:
        d = await svc.resolve_discovery(s, bus, id=d.id, resolution="figured it out")
    assert d.status == "resolved"
    assert d.resolved_at is not None


async def test_absorb_into_decision(
    Session: async_sessionmaker[AsyncSession], bus: MutationBus
) -> None:
    async with Session() as s:
        await packages_svc.create_package(
            s, bus, id="p2", title="t", goal="g", actor="human"
        )
    async with Session() as s:
        d = await svc.record_discovery(
            s, bus, kind="insight", title="t", body="b", package_id="p2"
        )
    async with Session() as s:
        dec = await decisions_svc.propose_decision(
            s, bus, title="dec", context="c", decision="d"
        )
    async with Session() as s:
        d = await svc.absorb_discovery(
            s, bus, discovery_id=d.id, into_kind="decision", into_id=dec.id
        )
    assert d.status == "absorbed"
    assert d.absorbed_into_kind == "decision"
    assert d.absorbed_into_id == str(dec.id)


async def test_absorb_into_package(
    Session: async_sessionmaker[AsyncSession], bus: MutationBus
) -> None:
    async with Session() as s:
        await packages_svc.create_package(
            s, bus, id="src-pkg", title="t", goal="g", actor="human"
        )
        await packages_svc.create_package(
            s, bus, id="abs-pkg", title="absorbing pkg", goal="g", actor="human"
        )
    async with Session() as s:
        d = await svc.record_discovery(
            s, bus, kind="hypothesis", title="t", body="b", package_id="src-pkg"
        )
    async with Session() as s:
        d = await svc.absorb_discovery(
            s, bus, discovery_id=d.id, into_kind="package", into_id="abs-pkg"
        )
    assert d.status == "absorbed"
    assert d.absorbed_into_kind == "package"
    assert d.absorbed_into_id == "abs-pkg"
    # original package_id preserved (it's where the discovery was found)
    assert d.package_id == "src-pkg"


async def test_absorb_into_missing_package_raises(
    Session: async_sessionmaker[AsyncSession], bus: MutationBus
) -> None:
    async with Session() as s:
        d = await svc.record_discovery(
            s, bus, kind="risk", title="t", body="b", package_id=None
        )
    async with Session() as s:
        from throughline.exceptions import NotFoundError as _NF

        with pytest.raises(_NF):
            await svc.absorb_discovery(
                s, bus, discovery_id=d.id, into_kind="package", into_id="ghost"
            )


async def test_invalid_kind_rejected(
    Session: async_sessionmaker[AsyncSession], bus: MutationBus
) -> None:
    async with Session() as s:
        with pytest.raises(ValidationError):
            await svc.record_discovery(
                s, bus, kind="bogus", title="t", body="b", package_id=None  # type: ignore[arg-type]
            )


async def test_resolve_requires_open(
    Session: async_sessionmaker[AsyncSession], bus: MutationBus
) -> None:
    async with Session() as s:
        d = await svc.record_discovery(
            s, bus, kind="risk", title="t", body="b", package_id=None
        )
    async with Session() as s:
        await svc.resolve_discovery(s, bus, id=d.id, resolution="ok")
    async with Session() as s:
        with pytest.raises(TransitionError):
            await svc.resolve_discovery(s, bus, id=d.id, resolution="again")
