"""Render output structure + debouncer behavior."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from throughline.events import MutationBus
from throughline.render.active_context_md import render_active_context_md
from throughline.render.state_md import render_state_md
from throughline.render.worker import render_worker
from throughline.services import decisions as decisions_svc
from throughline.services import discoveries as discoveries_svc
from throughline.services import packages as packages_svc


@pytest_asyncio.fixture
async def populated(
    Session: async_sessionmaker[AsyncSession], bus: MutationBus
) -> async_sessionmaker[AsyncSession]:
    async with Session() as s:
        await packages_svc.create_package(
            s, bus, id="999", title="ship v1", goal="dogfood", actor="human"
        )
        await packages_svc.update_package(
            s,
            bus,
            id="999",
            fields={"acceptance_criteria": "ten gates pass " * 4},
            actor="human",
        )
        await packages_svc.commit_package(s, bus, id="999", actor="human")
        await packages_svc.set_package_status(
            s, bus, id="999", new_status="in-progress", actor="agent"
        )
    async with Session() as s:
        d = await decisions_svc.propose_decision(
            s, bus, title="HTTP transport", context="why", decision="HTTP"
        )
        await decisions_svc.ratify_decision(s, bus, id=d.id)
    async with Session() as s:
        await discoveries_svc.record_discovery(
            s,
            bus,
            kind="blocker",
            title="WAL on /mnt/c fails",
            body="locks break",
            package_id="999",
        )
    return Session


async def test_state_md_has_all_sections(
    populated: async_sessionmaker[AsyncSession],
) -> None:
    async with populated() as s:
        out = await render_state_md(s)
    for header in [
        "# Current focus",
        "# Packages",
        "## In progress",
        "## Ready",
        "## Draft",
        "## Done",
        "## Abandoned",
        "# Ratified decisions",
        "# Open discoveries",
        "# Latest activity",
        "# Free-form sections",
    ]:
        assert header in out, f"missing section: {header}"
    assert "999" in out
    assert "ship v1" in out
    assert "HTTP transport" in out
    assert "WAL on /mnt/c fails" in out


async def test_active_context_focuses_on_in_progress(
    populated: async_sessionmaker[AsyncSession],
) -> None:
    async with populated() as s:
        out = await render_active_context_md(s)
    assert "999" in out
    assert "ship v1" in out
    assert "ten gates pass" in out  # acceptance_criteria
    assert "WAL on /mnt/c fails" in out  # related open discovery
    assert "HTTP transport" in out  # recent ratified decision


async def test_active_context_when_no_active_package(
    Session: async_sessionmaker[AsyncSession], bus: MutationBus
) -> None:
    async with Session() as s:
        out = await render_active_context_md(s)
    assert "_no active package_" in out


async def test_debouncer_coalesces_signals(
    Session: async_sessionmaker[AsyncSession],
    bus: MutationBus,
    tmp_path: Path,
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()

    debounce_s = 0.05
    task = asyncio.create_task(render_worker(bus, Session, docs, debounce_s))
    try:
        # 5 quick signals within the debounce window → one render
        for _ in range(5):
            await bus.signal()
        # wait long enough for debouncer to fire
        await asyncio.sleep(debounce_s * 4)
        first_state = (docs / "state.md").read_text()
        first_mtime = (docs / "state.md").stat().st_mtime_ns

        # populate something then signal again
        async with Session() as s:
            from throughline.services import packages as packages_svc

            await packages_svc.create_package(
                s, bus, id="X", title="x", goal="g", actor="human"
            )
        await asyncio.sleep(debounce_s * 4)

        second_state = (docs / "state.md").read_text()
        second_mtime = (docs / "state.md").stat().st_mtime_ns

        assert second_mtime > first_mtime
        assert "X" not in first_state
        assert "X" in second_state
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
