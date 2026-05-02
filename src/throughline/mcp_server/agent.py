"""build_agent_mcp — FastMCP instance with the 6 agent-facing tools."""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from throughline.config import Settings
from throughline.mcp_server.context import ServiceContext
from throughline.mcp_server.resources import register_resources
from throughline.mcp_server.serialization import (
    discovery_dict,
    log_dict,
    package_dict,
    state_section_dict,
)
from throughline.services import discoveries as discoveries_svc
from throughline.services import log as log_svc
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


def build_agent_mcp(ctx: ServiceContext, settings: Settings) -> FastMCP:
    mcp: FastMCP = FastMCP(
        "throughline-agent",
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
        transport_security=_security(settings),
    )
    register_resources(mcp, ctx)

    @mcp.tool()
    async def set_package_status(id: str, new_status: str) -> dict[str, Any]:
        """Move a package along the agent transition table."""
        async with ctx.session() as s:
            p = await packages_svc.set_package_status(
                s, ctx.bus, id=id, new_status=new_status, actor="agent"  # type: ignore[arg-type]
            )
            return package_dict(p)

    @mcp.tool()
    async def update_package_field(
        id: str, field: str, value: str | None
    ) -> dict[str, Any]:
        """Update decisions_made or verification on a non-terminal package."""
        async with ctx.session() as s:
            p = await packages_svc.update_package_field(
                s, ctx.bus, id=id, field=field, value=value, actor="agent"
            )
            return package_dict(p)

    @mcp.tool()
    async def record_discovery(
        kind: str,
        title: str,
        body: str,
        package_id: str | None = None,
    ) -> dict[str, Any]:
        """Record a discovery (blocker, insight, hypothesis, risk)."""
        async with ctx.session() as s:
            d = await discoveries_svc.record_discovery(
                s, ctx.bus,
                kind=kind, title=title, body=body, package_id=package_id,  # type: ignore[arg-type]
            )
            return discovery_dict(d)

    @mcp.tool()
    async def resolve_discovery(id: int, resolution: str) -> dict[str, Any]:
        """Mark a discovery resolved."""
        async with ctx.session() as s:
            d = await discoveries_svc.resolve_discovery(
                s, ctx.bus, id=id, resolution=resolution
            )
            return discovery_dict(d)

    @mcp.tool()
    async def append_log(package_id: str, entry: str) -> dict[str, Any]:
        """Append a free-text log entry attributed to the agent."""
        async with ctx.session() as s:
            row = await log_svc.append_log(
                s, ctx.bus, package_id=package_id, entry=entry, actor="agent"
            )
            return log_dict(row)

    @mcp.tool()
    async def patch_state(section: str, content: str) -> dict[str, Any]:
        """Patch a state section restricted to the agent allowlist."""
        async with ctx.session() as s:
            row = await state_sections_svc.patch_state(
                s, ctx.bus,
                name=section, content=content, actor="agent",
                allowed_sections=state_sections_svc.AGENT_ALLOWED_SECTIONS,
            )
            return state_section_dict(row)

    return mcp
