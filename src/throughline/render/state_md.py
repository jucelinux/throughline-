"""Render the full snapshot — `.docs/state.md`."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from throughline.db.models import (
    Decision,
    Discovery,
    ExecutionLog,
    Package,
    StateSection,
)

PACKAGE_GROUPS = [
    ("in-progress", "## In progress"),
    ("ready", "## Ready"),
    ("draft", "## Draft"),
    ("done", "## Done"),
    ("abandoned", "## Abandoned"),
]


def _fmt(ts: datetime | None) -> str:
    if ts is None:
        return ""
    return ts.strftime("%Y-%m-%d %H:%M")


def _packages_table(rows: Iterable[Package]) -> str:
    rows = list(rows)
    if not rows:
        return "_none_\n"
    out = ["| id | title | updated |", "|---|---|---|"]
    for p in rows:
        title = (p.title or "").replace("|", "\\|")
        out.append(f"| {p.id} | {title} | {_fmt(p.updated_at)} |")
    return "\n".join(out) + "\n"


async def render_state_md(session: AsyncSession) -> str:
    sections: list[str] = []

    focus = await session.get(StateSection, "current_focus")
    sections.append("# Current focus\n")
    sections.append((focus.content if focus else "_unset_") + "\n")

    sections.append("\n# Packages\n")
    pkgs = (
        (await session.execute(select(Package).order_by(Package.updated_at.desc())))
        .scalars()
        .all()
    )
    by_status = {s: [p for p in pkgs if p.status == s] for s, _ in PACKAGE_GROUPS}
    for status, header in PACKAGE_GROUPS:
        sections.append(f"\n{header}\n\n")
        sections.append(_packages_table(by_status[status]))

    sections.append("\n# Ratified decisions\n\n")
    ratified = (
        (
            await session.execute(
                select(Decision)
                .where(Decision.status == "ratified")
                .order_by(Decision.ratified_at.desc())
                .limit(10)
            )
        )
        .scalars()
        .all()
    )
    if not ratified:
        sections.append("_none_\n")
    else:
        sections.append("| id | title | ratified |\n|---|---|---|\n")
        for d in ratified:
            sections.append(
                f"| {d.id} | {(d.title or '').replace('|','\\|')} | {_fmt(d.ratified_at)} |\n"
            )

    sections.append("\n# Open discoveries\n\n")
    opens = (
        (
            await session.execute(
                select(Discovery)
                .where(Discovery.status == "open")
                .order_by(Discovery.id.asc())
            )
        )
        .scalars()
        .all()
    )
    if not opens:
        sections.append("_none_\n")
    else:
        sections.append("| id | kind | title | package |\n|---|---|---|---|\n")
        for d in opens:
            sections.append(
                f"| {d.id} | {d.kind} | {(d.title or '').replace('|','\\|')} | "
                f"{d.package_id or '—'} |\n"
            )

    sections.append("\n# Latest activity\n\n")
    log = (
        (
            await session.execute(
                select(ExecutionLog).order_by(ExecutionLog.id.desc()).limit(20)
            )
        )
        .scalars()
        .all()
    )
    if not log:
        sections.append("_none_\n")
    else:
        for row in log:
            sections.append(
                f"- {_fmt(row.timestamp)} [{row.actor}] {row.package_id}: {row.entry}\n"
            )

    sections.append("\n# Free-form sections\n")
    free = (
        (
            await session.execute(
                select(StateSection)
                .where(StateSection.name != "current_focus")
                .order_by(StateSection.name)
            )
        )
        .scalars()
        .all()
    )
    if not free:
        sections.append("\n_none_\n")
    else:
        for s in free:
            sections.append(f"\n## {s.name}\n\n{s.content}\n")

    return "".join(sections)
