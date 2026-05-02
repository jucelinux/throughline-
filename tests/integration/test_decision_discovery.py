"""AC #6 — propose/ratify decision + record/absorb discovery via HTTP."""
from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator

import httpx
import pytest_asyncio
from asgi_lifespan import LifespanManager

from throughline.config import Settings
from throughline.http_app.app import build_app

from ._jsonrpc import MCPClient


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        db_path=tmp_path / "state.db",
        docs_dir=tmp_path / "docs",
        debounce_ms=20,
    )


@pytest_asyncio.fixture
async def env(tmp_path: Path) -> AsyncIterator[tuple[httpx.AsyncClient, Path]]:
    app = build_app(_settings(tmp_path))
    async with LifespanManager(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://localhost:8765",
        ) as c:
            yield c, _settings(tmp_path).docs_dir


async def test_decision_and_discovery_absorb(
    env: tuple[httpx.AsyncClient, Path],
) -> None:
    http, docs = env
    human = MCPClient(http, "human")
    agent = MCPClient(http, "agent")

    # set up a package for the discovery to attach to
    await human.call(
        "create_package",
        {"id": "P1", "title": "host", "goal": "test"},
    )

    # human proposes + ratifies a decision
    dec = await human.call(
        "propose_decision",
        {
            "title": "use HTTP transport",
            "context": "Desktop on Win + Code on WSL",
            "decision": "expose Streamable HTTP on 8765",
            "alternatives": "stdio",
            "consequences": "needs container",
        },
    )
    assert dec["status"] == "proposed"
    dec = await human.call("ratify_decision", {"id": dec["id"]})
    assert dec["status"] == "ratified"

    # agent records a discovery
    disc = await agent.call(
        "record_discovery",
        {
            "kind": "insight",
            "title": "WAL needs full dir mount",
            "body": "siblings -wal -shm must persist",
            "package_id": "P1",
        },
    )
    assert disc["status"] == "open"

    # human absorbs into the decision
    absorbed = await human.call(
        "absorb_discovery",
        {
            "discovery_id": disc["id"],
            "into_kind": "decision",
            "into_id": str(dec["id"]),
        },
    )
    assert absorbed["status"] == "absorbed"
    assert absorbed["absorbed_into_kind"] == "decision"
    assert absorbed["absorbed_into_id"] == str(dec["id"])

    # state.md eventually reflects both
    import asyncio
    await asyncio.sleep(0.15)
    state = (docs / "state.md").read_text()
    assert "use HTTP transport" in state
