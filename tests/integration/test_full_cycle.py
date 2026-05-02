"""AC #3 + AC #4 — full package lifecycle + observable .docs/ regeneration."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from throughline.config import Settings
from throughline.http_app.app import build_app

from ._jsonrpc import MCPClient, ToolFailure


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        db_path=tmp_path / "state.db",
        docs_dir=tmp_path / "docs",
        debounce_ms=20,
    )


@pytest_asyncio.fixture
async def env(tmp_path: Path) -> AsyncIterator[tuple[httpx.AsyncClient, Path]]:
    settings = _settings(tmp_path)
    app = build_app(settings)
    async with LifespanManager(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://localhost:8765",
        ) as c:
            yield c, settings.docs_dir


async def _wait_for_render(docs: Path, file: str, prior_mtime: int = 0) -> int:
    """Poll until the file has been written (or rewritten) at a higher mtime."""
    target = docs / file
    deadline = asyncio.get_event_loop().time() + 2.0
    while asyncio.get_event_loop().time() < deadline:
        if target.exists() and target.stat().st_mtime_ns > prior_mtime:
            return target.stat().st_mtime_ns
        await asyncio.sleep(0.02)
    raise AssertionError(f"{file} never (re)rendered above mtime={prior_mtime}")


async def test_full_cycle_acceptance(
    env: tuple[httpx.AsyncClient, Path],
) -> None:
    http, docs = env
    human = MCPClient(http, "human")
    agent = MCPClient(http, "agent")

    # cold-start render fires on lifespan startup
    state_mtime = await _wait_for_render(docs, "state.md")
    active_mtime = await _wait_for_render(docs, "active-context.md")
    regenerations = 0

    # 1. create draft package
    pkg = await human.call(
        "create_package",
        {"id": "999", "title": "test package", "goal": "verify the cycle"},
    )
    assert pkg["id"] == "999"
    assert pkg["status"] == "draft"
    state_mtime = await _wait_for_render(docs, "state.md", state_mtime)
    regenerations += 1

    # 2. commit fails without acceptance_criteria
    with pytest.raises(ToolFailure):
        await human.call("commit_package", {"id": "999"})

    # 3. set AC, commit succeeds → ready
    await human.call(
        "update_package",
        {"id": "999", "acceptance_criteria": "x" * 40},
    )
    state_mtime = await _wait_for_render(docs, "state.md", state_mtime)
    regenerations += 1

    pkg = await human.call("commit_package", {"id": "999"})
    assert pkg["status"] == "ready"
    state_mtime = await _wait_for_render(docs, "state.md", state_mtime)
    regenerations += 1

    # 4. agent moves to in-progress
    pkg = await agent.call(
        "set_package_status", {"id": "999", "new_status": "in-progress"}
    )
    assert pkg["status"] == "in-progress"
    state_mtime = await _wait_for_render(docs, "state.md", state_mtime)
    active_mtime = await _wait_for_render(docs, "active-context.md", active_mtime)
    regenerations += 1

    # 5. agent appends log
    log_row = await agent.call(
        "append_log", {"package_id": "999", "entry": "started spike"}
    )
    assert log_row["actor"] == "agent"
    state_mtime = await _wait_for_render(docs, "state.md", state_mtime)
    regenerations += 1

    # 6. agent completes
    pkg = await agent.call("set_package_status", {"id": "999", "new_status": "done"})
    assert pkg["status"] == "done"
    assert pkg["closed_at"] is not None
    state_mtime = await _wait_for_render(docs, "state.md", state_mtime)
    regenerations += 1

    # AC #4: at least 3 regenerations of state.md observed during the cycle
    assert regenerations >= 3, f"only saw {regenerations} regenerations"

    # content reflects the package
    content = (docs / "state.md").read_text()
    assert "999" in content
    assert "test package" in content
