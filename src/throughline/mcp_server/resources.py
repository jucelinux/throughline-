"""Read-only resources — registered identically on both human and agent MCP servers."""
from __future__ import annotations

from sqlalchemy import select

from mcp.server.fastmcp import FastMCP
from throughline.db.models import Decision, Discovery, Package
from throughline.mcp_server.context import ServiceContext
from throughline.mcp_server.serialization import (
    decision_dict,
    discovery_dict,
    package_dict,
)
from throughline.render.active_context_md import render_active_context_md
from throughline.render.state_md import render_state_md
from throughline.services import discoveries as discoveries_svc


def register_resources(mcp: FastMCP, ctx: ServiceContext) -> None:
    @mcp.resource("throughline://state")
    async def state() -> str:
        async with ctx.session() as s:
            return await render_state_md(s)

    @mcp.resource("throughline://active-context")
    async def active_context() -> str:
        async with ctx.session() as s:
            return await render_active_context_md(s)

    @mcp.resource("throughline://packages")
    async def packages_list() -> list[dict]:
        async with ctx.session() as s:
            rows = (
                await s.execute(select(Package).order_by(Package.updated_at.desc()))
            ).scalars().all()
            return [
                {"id": p.id, "title": p.title, "status": p.status} for p in rows
            ]

    @mcp.resource("throughline://package/{id}")
    async def package_full(id: str) -> dict:
        async with ctx.session() as s:
            p = await s.get(Package, id)
            if p is None:
                return {"error": f"package '{id}' not found"}
            return package_dict(p)

    @mcp.resource("throughline://decisions")
    async def decisions_list() -> list[dict]:
        async with ctx.session() as s:
            rows = (
                await s.execute(select(Decision).order_by(Decision.id.asc()))
            ).scalars().all()
            return [
                {"id": d.id, "title": d.title, "status": d.status} for d in rows
            ]

    @mcp.resource("throughline://decision/{id}")
    async def decision_full(id: str) -> dict:
        async with ctx.session() as s:
            d = await s.get(Decision, int(id))
            if d is None:
                return {"error": f"decision {id} not found"}
            return decision_dict(d)

    @mcp.resource("throughline://discoveries/open")
    async def discoveries_open() -> list[dict]:
        async with ctx.session() as s:
            rows = await discoveries_svc.list_discoveries(s, status="open")
            return [discovery_dict(d) for d in rows]
