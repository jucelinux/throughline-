"""Coverage of state_sections allowlist (agent vs human)."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from throughline.events import MutationBus
from throughline.exceptions import ValidationError
from throughline.services import state_sections as svc


async def test_human_unrestricted(
    Session: async_sessionmaker[AsyncSession], bus: MutationBus
) -> None:
    async with Session() as s:
        section = await svc.patch_state(
            s, bus, name="current_focus", content="ship v1", actor="human"
        )
    assert section.content == "ship v1"


async def test_agent_allowlist(
    Session: async_sessionmaker[AsyncSession], bus: MutationBus
) -> None:
    async with Session() as s:
        section = await svc.patch_state(
            s,
            bus,
            name="latest_activity",
            content="just shipped",
            actor="agent",
            allowed_sections=svc.AGENT_ALLOWED_SECTIONS,
        )
    assert section.content == "just shipped"


async def test_agent_denied_outside_allowlist(
    Session: async_sessionmaker[AsyncSession], bus: MutationBus
) -> None:
    async with Session() as s:
        with pytest.raises(ValidationError):
            await svc.patch_state(
                s,
                bus,
                name="current_focus",
                content="hijack",
                actor="agent",
                allowed_sections=svc.AGENT_ALLOWED_SECTIONS,
            )


async def test_upsert_overwrites(
    Session: async_sessionmaker[AsyncSession], bus: MutationBus
) -> None:
    async with Session() as s:
        await svc.patch_state(s, bus, name="current_focus", content="v1", actor="human")
    async with Session() as s:
        section = await svc.patch_state(
            s, bus, name="current_focus", content="v2", actor="human"
        )
    assert section.content == "v2"
