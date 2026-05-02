"""Render the harness-focused context — `.docs/active-context.md`.

Includes only the single in-progress package (latest if more than one),
its open discoveries, and the last 5 ratified decisions.
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from throughline.db.models import Decision, Discovery, Package

logger = logging.getLogger(__name__)


def _fmt(ts: datetime | None) -> str:
    return ts.strftime("%Y-%m-%d %H:%M") if ts else ""


def _format_paths_glob(paths_glob: list[str] | None) -> str:
    if not paths_glob:
        return "_none_"
    return ", ".join(f"`{g}`" for g in paths_glob)


async def render_active_context_md(session: AsyncSession) -> str:
    sections: list[str] = []

    in_progress = (
        (
            await session.execute(
                select(Package)
                .where(Package.status == "in-progress")
                .order_by(Package.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    if len(in_progress) > 1:
        logger.warning(
            "multiple in-progress packages (%d); rendering the most recently updated",
            len(in_progress),
        )

    sections.append("# Active package\n\n")
    if not in_progress:
        sections.append("_no active package_\n")
        active_id: str | None = None
    else:
        p = in_progress[0]
        active_id = p.id
        sections.append(f"**{p.id}** — {p.title}\n\n")
        sections.append(f"_status: {p.status}, updated: {_fmt(p.updated_at)}_\n\n")
        if p.goal:
            sections.append(f"## Goal\n\n{p.goal}\n\n")
        if p.acceptance_criteria:
            sections.append(f"## Acceptance criteria\n\n{p.acceptance_criteria}\n\n")
        if p.out_of_scope:
            sections.append(f"## Out of scope\n\n{p.out_of_scope}\n\n")
        if p.decisions_made:
            sections.append(f"## Decisions made\n\n{p.decisions_made}\n\n")
        if p.verification:
            sections.append(f"## Verification\n\n{p.verification}\n\n")
        sections.append(f"## paths_glob\n\n{_format_paths_glob(p.paths_glob)}\n\n")

    sections.append("# Related open discoveries\n\n")
    if active_id is not None:
        stmt = (
            select(Discovery)
            .where(Discovery.status == "open", Discovery.package_id == active_id)
            .order_by(Discovery.id.asc())
        )
    else:
        stmt = (
            select(Discovery)
            .where(Discovery.status == "open")
            .order_by(Discovery.id.asc())
        )
    related = (await session.execute(stmt)).scalars().all()
    if not related:
        sections.append("_none_\n")
    else:
        for d in related:
            sections.append(f"- **#{d.id}** [{d.kind}] {d.title}\n  {d.body[:200]}\n")
    sections.append("\n")

    sections.append("# Recent ratified decisions\n\n")
    recent = (
        (
            await session.execute(
                select(Decision)
                .where(Decision.status == "ratified")
                .order_by(Decision.ratified_at.desc())
                .limit(5)
            )
        )
        .scalars()
        .all()
    )
    if not recent:
        sections.append("_none_\n")
    else:
        for d in recent:
            sections.append(f"- **#{d.id}** {d.title} — {_fmt(d.ratified_at)}\n")

    return "".join(sections)
