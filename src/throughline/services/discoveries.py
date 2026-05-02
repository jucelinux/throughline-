"""Discovery (blocker / insight / hypothesis / risk) services."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from throughline.db.models import (
    AbsorbedKind,
    Decision,
    Discovery,
    DiscoveryKind,
    Package,
)
from throughline.events import MutationBus
from throughline.exceptions import NotFoundError, TransitionError, ValidationError
from throughline.services._audit import audit_row, now


async def get_discovery(session: AsyncSession, id: int) -> Discovery:
    d = await session.get(Discovery, id)
    if d is None:
        raise NotFoundError(f"discovery {id} not found")
    return d


async def record_discovery(
    session: AsyncSession,
    bus: MutationBus,
    *,
    kind: DiscoveryKind,
    title: str,
    body: str,
    package_id: str | None = None,
) -> Discovery:
    if kind not in {"blocker", "insight", "hypothesis", "risk"}:
        raise ValidationError(f"invalid kind: {kind}")
    if not title.strip() or not body.strip():
        raise ValidationError("title and body are required")
    if package_id is not None:
        pkg = await session.get(Package, package_id)
        if pkg is None:
            raise NotFoundError(f"package '{package_id}' not found")

    d = Discovery(
        kind=kind,
        title=title,
        body=body,
        status="open",
        package_id=package_id,
        created_at=now(),
    )
    session.add(d)
    if package_id is not None:
        session.add(audit_row(package_id, "agent", f"discovery recorded: {kind} — {title}"))
    await session.commit()
    await session.refresh(d)
    await bus.signal()
    return d


async def resolve_discovery(
    session: AsyncSession, bus: MutationBus, *, id: int, resolution: str
) -> Discovery:
    d = await get_discovery(session, id)
    if d.status != "open":
        raise TransitionError(
            f"resolve_discovery requires status='open' (got '{d.status}')"
        )
    if not resolution.strip():
        raise ValidationError("resolution is required")
    d.status = "resolved"
    d.resolution = resolution
    d.resolved_at = now()
    if d.package_id is not None:
        session.add(
            audit_row(d.package_id, "agent", f"discovery {id} resolved: {resolution[:60]}")
        )
    await session.commit()
    await session.refresh(d)
    await bus.signal()
    return d


async def absorb_discovery(
    session: AsyncSession,
    bus: MutationBus,
    *,
    discovery_id: int,
    into_kind: AbsorbedKind,
    into_id: int | str,
) -> Discovery:
    d = await get_discovery(session, discovery_id)
    if d.status == "absorbed":
        raise TransitionError(f"discovery {discovery_id} is already absorbed")

    if into_kind == "package":
        target = await session.get(Package, str(into_id))
        if target is None:
            raise NotFoundError(f"package '{into_id}' not found")
        target_id_str = str(into_id)
    elif into_kind == "decision":
        target = await session.get(Decision, int(into_id))
        if target is None:
            raise NotFoundError(f"decision {into_id} not found")
        target_id_str = str(int(into_id))
    else:
        raise ValidationError(f"invalid into_kind: {into_kind}")

    d.status = "absorbed"
    d.absorbed_into_kind = into_kind
    d.absorbed_into_id = target_id_str
    if d.resolved_at is None:
        d.resolved_at = now()
    if d.package_id is not None:
        session.add(
            audit_row(
                d.package_id,
                "human",
                f"discovery {discovery_id} absorbed into {into_kind} {into_id}",
            )
        )
    await session.commit()
    await session.refresh(d)
    await bus.signal()
    return d


async def list_discoveries(
    session: AsyncSession, *, status: str | None = None
) -> list[Discovery]:
    stmt = select(Discovery).order_by(Discovery.id.asc())
    if status is not None:
        stmt = stmt.where(Discovery.status == status)
    result = await session.execute(stmt)
    return list(result.scalars().all())
