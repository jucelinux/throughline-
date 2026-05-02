"""AC #2 — handshake by actor: 9 tools (human), 6 (agent), 400 (no header)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import AsyncIterator

import httpx
import pytest_asyncio
from asgi_lifespan import LifespanManager

from throughline.config import Settings
from throughline.http_app.app import build_app


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        db_path=tmp_path / "state.db",
        docs_dir=tmp_path / "docs",
        debounce_ms=20,
    )


JSONRPC_INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "tests", "version": "0"},
    },
}
JSONRPC_INITIALIZED = {"jsonrpc": "2.0", "method": "notifications/initialized"}
JSONRPC_TOOLS_LIST = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
HEADERS_BASE = {"Accept": "application/json, text/event-stream"}


@pytest_asyncio.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    app = build_app(_settings(tmp_path))
    async with LifespanManager(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://localhost:8765",
        ) as c:
            yield c


async def _list_tools(client: httpx.AsyncClient, actor: str) -> list[str]:
    h = {**HEADERS_BASE, "X-Throughline-Actor": actor}
    init = await client.post("/mcp/", json=JSONRPC_INIT, headers=h)
    assert init.status_code == 200, init.text
    await client.post("/mcp/", json=JSONRPC_INITIALIZED, headers=h)
    r = await client.post("/mcp/", json=JSONRPC_TOOLS_LIST, headers=h)
    assert r.status_code == 200, r.text
    return [t["name"] for t in r.json()["result"]["tools"]]


async def test_health_ok(client: httpx.AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_human_has_9_tools(client: httpx.AsyncClient) -> None:
    names = await _list_tools(client, "human")
    assert len(names) == 9, f"got {len(names)}: {names}"
    expected = {
        "create_package",
        "update_package",
        "commit_package",
        "abandon_package",
        "propose_decision",
        "ratify_decision",
        "supersede_decision",
        "absorb_discovery",
        "patch_state",
    }
    assert set(names) == expected


async def test_agent_has_6_tools(client: httpx.AsyncClient) -> None:
    names = await _list_tools(client, "agent")
    assert len(names) == 6, f"got {len(names)}: {names}"
    expected = {
        "set_package_status",
        "update_package_field",
        "record_discovery",
        "resolve_discovery",
        "append_log",
        "patch_state",
    }
    assert set(names) == expected


async def test_missing_header_400(client: httpx.AsyncClient) -> None:
    r = await client.post("/mcp/", json=JSONRPC_INIT, headers=HEADERS_BASE)
    assert r.status_code == 400
    body = r.json()
    assert "X-Throughline-Actor" in body["error"]


async def test_invalid_header_400(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/mcp/",
        json=JSONRPC_INIT,
        headers={**HEADERS_BASE, "X-Throughline-Actor": "bogus"},
    )
    assert r.status_code == 400
