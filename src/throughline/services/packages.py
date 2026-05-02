"""Package-lifecycle services."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from throughline.db.models import Actor, Package, PackageStatus
from throughline.events import MutationBus
from throughline.exceptions import (
    ConflictError,
    NotFoundError,
    TransitionError,
    ValidationError,
)
from throughline.services._audit import audit_row, now

# Fields editable on a package via update_package (human, draft only).
HUMAN_DRAFT_FIELDS = {
    "title",
    "goal",
    "acceptance_criteria",
    "out_of_scope",
    "decisions_made",
    "verification",
    "paths_glob",
}

# Fields editable by the agent via update_package_field, in any non-terminal status.
AGENT_EDITABLE_FIELDS = {"decisions_made", "verification"}

TERMINAL_STATUSES = {"done", "abandoned"}

# Allowed transitions for set_package_status (agent).
AGENT_TRANSITIONS: dict[str, set[str]] = {
    "ready": {"in-progress"},
    "in-progress": {"done", "abandoned"},
}


async def get_package(session: AsyncSession, id: str) -> Package:
    pkg = await session.get(Package, id)
    if pkg is None:
        raise NotFoundError(f"package '{id}' not found")
    return pkg


async def create_package(
    session: AsyncSession,
    bus: MutationBus,
    *,
    id: str,
    title: str,
    goal: str | None = None,
    paths_glob: list[str] | None = None,
    actor: Actor,
) -> Package:
    if not id or not id.strip():
        raise ValidationError("id is required")
    if not title or not title.strip():
        raise ValidationError("title is required")

    existing = await session.get(Package, id)
    if existing is not None:
        raise ConflictError(f"package '{id}' already exists")

    ts = now()
    pkg = Package(
        id=id,
        title=title,
        status="draft",
        goal=goal,
        paths_glob=paths_glob,
        created_at=ts,
        updated_at=ts,
    )
    session.add(pkg)
    await session.flush()  # ensure packages row exists before FK-dependent log row
    session.add(audit_row(id, actor, "created (status=draft)"))
    await session.commit()
    await session.refresh(pkg)
    await bus.signal()
    return pkg


async def update_package(
    session: AsyncSession,
    bus: MutationBus,
    *,
    id: str,
    fields: dict[str, Any],
    actor: Actor,
) -> Package:
    pkg = await get_package(session, id)
    if pkg.status != "draft":
        raise TransitionError(
            f"update_package requires status='draft' (got '{pkg.status}')"
        )
    unknown = set(fields) - HUMAN_DRAFT_FIELDS
    if unknown:
        raise ValidationError(f"unknown fields: {sorted(unknown)}")

    changed = []
    for k, v in fields.items():
        if getattr(pkg, k) != v:
            setattr(pkg, k, v)
            changed.append(k)
    if not changed:
        return pkg

    pkg.updated_at = now()
    session.add(audit_row(id, actor, f"updated fields: {', '.join(sorted(changed))}"))
    await session.commit()
    await session.refresh(pkg)
    await bus.signal()
    return pkg


async def commit_package(
    session: AsyncSession,
    bus: MutationBus,
    *,
    id: str,
    actor: Actor,
) -> Package:
    pkg = await get_package(session, id)
    if pkg.status != "draft":
        raise TransitionError(
            f"commit_package requires status='draft' (got '{pkg.status}')"
        )
    ac = pkg.acceptance_criteria or ""
    if len(ac.strip()) <= 30:
        raise ValidationError(
            "acceptance_criteria must be set and longer than 30 characters"
        )
    pkg.status = "ready"
    pkg.updated_at = now()
    session.add(audit_row(id, actor, "status: draft → ready"))
    await session.commit()
    await session.refresh(pkg)
    await bus.signal()
    return pkg


async def abandon_package(
    session: AsyncSession,
    bus: MutationBus,
    *,
    id: str,
    reason: str,
    actor: Actor,
) -> Package:
    pkg = await get_package(session, id)
    if pkg.status == "abandoned":
        raise TransitionError("package is already abandoned")
    if pkg.status == "done":
        raise TransitionError("cannot abandon a 'done' package")
    prior = pkg.status
    pkg.status = "abandoned"
    pkg.closed_at = now()
    pkg.updated_at = pkg.closed_at
    session.add(
        audit_row(id, actor, f"status: {prior} → abandoned ({reason or 'no reason given'})")
    )
    await session.commit()
    await session.refresh(pkg)
    await bus.signal()
    return pkg


async def set_package_status(
    session: AsyncSession,
    bus: MutationBus,
    *,
    id: str,
    new_status: PackageStatus,
    actor: Actor,
) -> Package:
    pkg = await get_package(session, id)
    allowed = AGENT_TRANSITIONS.get(pkg.status, set())
    if new_status not in allowed:
        raise TransitionError(
            f"invalid agent transition: {pkg.status} → {new_status} "
            f"(allowed from '{pkg.status}': {sorted(allowed) or 'none'})"
        )
    pkg.status = new_status
    pkg.updated_at = now()
    if new_status in TERMINAL_STATUSES:
        pkg.closed_at = pkg.updated_at
    session.add(audit_row(id, actor, f"status → {new_status}"))
    await session.commit()
    await session.refresh(pkg)
    await bus.signal()
    return pkg


async def update_package_field(
    session: AsyncSession,
    bus: MutationBus,
    *,
    id: str,
    field: str,
    value: str | None,
    actor: Actor,
) -> Package:
    if field not in AGENT_EDITABLE_FIELDS:
        raise ValidationError(
            f"agent may only update {sorted(AGENT_EDITABLE_FIELDS)} (got '{field}')"
        )
    pkg = await get_package(session, id)
    if pkg.status in TERMINAL_STATUSES:
        raise TransitionError(
            f"cannot update fields on a {pkg.status} package"
        )
    setattr(pkg, field, value)
    pkg.updated_at = now()
    session.add(audit_row(id, actor, f"updated field '{field}'"))
    await session.commit()
    await session.refresh(pkg)
    await bus.signal()
    return pkg


async def list_packages(session: AsyncSession) -> list[Package]:
    result = await session.execute(select(Package).order_by(Package.updated_at.desc()))
    return list(result.scalars().all())
