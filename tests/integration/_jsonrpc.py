"""Tiny JSON-RPC helper to drive the MCP HTTP endpoint in tests."""
from __future__ import annotations

import itertools
import json
from typing import Any

import httpx

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
HEADERS_BASE = {"Accept": "application/json, text/event-stream"}


class MCPClient:
    def __init__(self, http: httpx.AsyncClient, actor: str) -> None:
        self._http = http
        self._actor = actor
        self._headers = {**HEADERS_BASE, "X-Throughline-Actor": actor}
        self._counter = itertools.count(2)
        self._initialized = False

    async def _ensure_init(self) -> None:
        if self._initialized:
            return
        r = await self._http.post("/mcp/", json=JSONRPC_INIT, headers=self._headers)
        r.raise_for_status()
        await self._http.post(
            "/mcp/", json=JSONRPC_INITIALIZED, headers=self._headers
        )
        self._initialized = True

    async def call(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Invoke a tool. Returns the parsed result (or raises on JSON-RPC error)."""
        await self._ensure_init()
        body = {
            "jsonrpc": "2.0",
            "id": next(self._counter),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        }
        r = await self._http.post("/mcp/", json=body, headers=self._headers)
        r.raise_for_status()
        envelope = r.json()
        if "error" in envelope:
            raise RuntimeError(f"jsonrpc error: {envelope['error']}")
        result = envelope["result"]
        if result.get("isError"):
            text = result["content"][0]["text"] if result.get("content") else ""
            raise ToolFailure(text)
        # FastMCP returns content[0].text as a JSON string for dict tools.
        contents = result.get("content", [])
        if contents and contents[0].get("type") == "text":
            try:
                return json.loads(contents[0]["text"])
            except json.JSONDecodeError:
                return {"_raw_text": contents[0]["text"]}
        # Some tools may produce structuredContent
        return result.get("structuredContent") or {}


class ToolFailure(RuntimeError):
    """A tool reported isError=true; the message is the server's text."""
