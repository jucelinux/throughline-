"""Coverage of the package lifecycle (AC #3 logic)."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from throughline.events import MutationBus
from throughline.exceptions import (
    ConflictError,
    NotFoundError,
    TransitionError,
    ValidationError,
)
from throughline.services import packages as svc


async def test_create_then_commit_cycle(
    Session: async_sessionmaker[AsyncSession], bus: MutationBus
) -> None:
    async with Session() as s:
        pkg = await svc.create_package(
            s, bus, id="999", title="test pkg", goal="ship it", actor="human"
        )
    assert pkg.id == "999"
    assert pkg.status == "draft"

    # commit fails without acceptance_criteria
    async with Session() as s:
        with pytest.raises(ValidationError):
            await svc.commit_package(s, bus, id="999", actor="human")

    # set AC, commit succeeds
    async with Session() as s:
        await svc.update_package(
            s,
            bus,
            id="999",
            fields={"acceptance_criteria": "x" * 40},
            actor="human",
        )
    async with Session() as s:
        pkg = await svc.commit_package(s, bus, id="999", actor="human")
    assert pkg.status == "ready"


async def test_agent_transitions(
    Session: async_sessionmaker[AsyncSession], bus: MutationBus
) -> None:
    async with Session() as s:
        await svc.create_package(s, bus, id="1", title="t", goal="g", actor="human")
        await svc.update_package(
            s, bus, id="1", fields={"acceptance_criteria": "y" * 40}, actor="human"
        )
        await svc.commit_package(s, bus, id="1", actor="human")

    # ready → in-progress (agent)
    async with Session() as s:
        pkg = await svc.set_package_status(
            s, bus, id="1", new_status="in-progress", actor="agent"
        )
    assert pkg.status == "in-progress"

    # invalid agent transition
    async with Session() as s:
        with pytest.raises(TransitionError):
            await svc.set_package_status(s, bus, id="1", new_status="ready", actor="agent")

    # in-progress → done
    async with Session() as s:
        pkg = await svc.set_package_status(s, bus, id="1", new_status="done", actor="agent")
    assert pkg.status == "done"
    assert pkg.closed_at is not None


async def test_agent_field_update_allowlist(
    Session: async_sessionmaker[AsyncSession], bus: MutationBus
) -> None:
    async with Session() as s:
        await svc.create_package(s, bus, id="2", title="t", goal="g", actor="human")
        await svc.update_package(
            s, bus, id="2", fields={"acceptance_criteria": "z" * 40}, actor="human"
        )
        await svc.commit_package(s, bus, id="2", actor="human")
        await svc.set_package_status(
            s, bus, id="2", new_status="in-progress", actor="agent"
        )

    async with Session() as s:
        pkg = await svc.update_package_field(
            s, bus, id="2", field="decisions_made", value="picked X", actor="agent"
        )
    assert pkg.decisions_made == "picked X"

    async with Session() as s:
        with pytest.raises(ValidationError):
            await svc.update_package_field(
                s, bus, id="2", field="goal", value="hijack", actor="agent"
            )


async def test_duplicate_id_rejected(
    Session: async_sessionmaker[AsyncSession], bus: MutationBus
) -> None:
    async with Session() as s:
        await svc.create_package(s, bus, id="3", title="t", goal="g", actor="human")
    async with Session() as s:
        with pytest.raises(ConflictError):
            await svc.create_package(s, bus, id="3", title="t2", actor="human")


async def test_abandon_from_any_non_terminal(
    Session: async_sessionmaker[AsyncSession], bus: MutationBus
) -> None:
    async with Session() as s:
        await svc.create_package(s, bus, id="4", title="t", goal="g", actor="human")
    async with Session() as s:
        pkg = await svc.abandon_package(s, bus, id="4", reason="pivot", actor="human")
    assert pkg.status == "abandoned"
    assert pkg.closed_at is not None

    async with Session() as s:
        with pytest.raises(TransitionError):
            await svc.abandon_package(s, bus, id="4", reason="again", actor="human")


async def test_get_missing_raises(
    Session: async_sessionmaker[AsyncSession], bus: MutationBus
) -> None:
    async with Session() as s:
        with pytest.raises(NotFoundError):
            await svc.get_package(s, "nope")


async def test_bus_emits_signal_per_mutation(
    Session: async_sessionmaker[AsyncSession], bus: MutationBus
) -> None:
    async with Session() as s:
        await svc.create_package(s, bus, id="5", title="t", goal="g", actor="human")
    assert bus.queue.qsize() == 1
    async with Session() as s:
        await svc.update_package(
            s, bus, id="5", fields={"goal": "new goal"}, actor="human"
        )
    assert bus.queue.qsize() == 2
