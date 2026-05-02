"""build_human_mcp — FastMCP instance with the 9 human-facing tools."""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from throughline.config import Settings
from throughline.mcp_server.context import ServiceContext
from throughline.mcp_server.resources import register_resources
from throughline.mcp_server.serialization import (
    decision_dict,
    discovery_dict,
    package_dict,
    state_section_dict,
)
from throughline.services import decisions as decisions_svc
from throughline.services import discoveries as discoveries_svc
from throughline.services import packages as packages_svc
from throughline.services import state_sections as state_sections_svc


def _security(settings: Settings) -> TransportSecuritySettings:
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=bool(settings.allowed_hosts),
        allowed_hosts=settings.allowed_hosts or ["*"],
        allowed_origins=[
            o
            for h in (settings.allowed_hosts or ["*"])
            for o in (f"http://{h}", f"https://{h}")
        ],
    )


def build_human_mcp(ctx: ServiceContext, settings: Settings) -> FastMCP:
    mcp: FastMCP = FastMCP(
        "throughline-human",
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
        transport_security=_security(settings),
    )
    register_resources(mcp, ctx)

    @mcp.tool()
    async def create_package(
        id: str,
        title: str,
        goal: str | None = None,
        paths_glob: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new draft package."""
        async with ctx.session() as s:
            p = await packages_svc.create_package(
                s, ctx.bus,
                id=id, title=title, goal=goal, paths_glob=paths_glob,
                actor="human",
            )
            return package_dict(p)

    @mcp.tool()
    async def update_package(
        id: str,
        title: str | None = None,
        goal: str | None = None,
        acceptance_criteria: str | None = None,
        out_of_scope: str | None = None,
        decisions_made: str | None = None,
        verification: str | None = None,
        paths_glob: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update a draft package's fields. Only valid while status='draft'."""
        fields: dict[str, Any] = {
            k: v
            for k, v in {
                "title": title,
                "goal": goal,
                "acceptance_criteria": acceptance_criteria,
                "out_of_scope": out_of_scope,
                "decisions_made": decisions_made,
                "verification": verification,
                "paths_glob": paths_glob,
            }.items()
            if v is not None
        }
        async with ctx.session() as s:
            p = await packages_svc.update_package(
                s, ctx.bus, id=id, fields=fields, actor="human"
            )
            return package_dict(p)

    @mcp.tool()
    async def commit_package(id: str) -> dict[str, Any]:
        """Move a draft package to ready (validates acceptance_criteria)."""
        async with ctx.session() as s:
            p = await packages_svc.commit_package(s, ctx.bus, id=id, actor="human")
            return package_dict(p)

    @mcp.tool()
    async def abandon_package(id: str, reason: str) -> dict[str, Any]:
        """Abandon a non-terminal package."""
        async with ctx.session() as s:
            p = await packages_svc.abandon_package(
                s, ctx.bus, id=id, reason=reason, actor="human"
            )
            return package_dict(p)

    @mcp.tool()
    async def propose_decision(
        title: str,
        context: str,
        decision: str,
        alternatives: str | None = None,
        consequences: str | None = None,
    ) -> dict[str, Any]:
        """Record a proposed decision."""
        async with ctx.session() as s:
            d = await decisions_svc.propose_decision(
                s, ctx.bus,
                title=title, context=context, decision=decision,
                alternatives=alternatives, consequences=consequences,
            )
            return decision_dict(d)

    @mcp.tool()
    async def ratify_decision(id: int) -> dict[str, Any]:
        """Ratify a proposed decision."""
        async with ctx.session() as s:
            d = await decisions_svc.ratify_decision(s, ctx.bus, id=id)
            return decision_dict(d)

    @mcp.tool()
    async def supersede_decision(old_id: int, new_id: int) -> dict[str, Any]:
        """Mark old_id as superseded by new_id."""
        async with ctx.session() as s:
            d = await decisions_svc.supersede_decision(
                s, ctx.bus, old_id=old_id, new_id=new_id
            )
            return decision_dict(d)

    @mcp.tool()
    async def absorb_discovery(
        discovery_id: int,
        into_kind: str,
        into_id: str,
    ) -> dict[str, Any]:
        """Absorb a discovery into a package or decision."""
        async with ctx.session() as s:
            d = await discoveries_svc.absorb_discovery(
                s, ctx.bus,
                discovery_id=discovery_id, into_kind=into_kind, into_id=into_id,  # type: ignore[arg-type]
            )
            return discovery_dict(d)

    @mcp.tool()
    async def patch_state(section: str, content: str) -> dict[str, Any]:
        """Patch any free-form state section."""
        async with ctx.session() as s:
            row = await state_sections_svc.patch_state(
                s, ctx.bus, name=section, content=content, actor="human"
            )
            return state_section_dict(row)

    return mcp
