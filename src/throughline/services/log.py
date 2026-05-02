"""Explicit append_log tool — narrative entries by either actor."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from throughline.db.models import Actor, ExecutionLog, Package
from throughline.events import MutationBus
from throughline.exceptions import NotFoundError, ValidationError
from throughline.services._audit import audit_row


async def append_log(
    session: AsyncSession,
    bus: MutationBus,
    *,
    package_id: str,
    entry: str,
    actor: Actor,
) -> ExecutionLog:
    if not entry.strip():
        raise ValidationError("entry is required")
    pkg = await session.get(Package, package_id)
    if pkg is None:
        raise NotFoundError(f"package '{package_id}' not found")
    row = audit_row(package_id, actor, entry)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    await bus.signal()
    return row


async def recent_log(
    session: AsyncSession, *, limit: int = 20
) -> list[ExecutionLog]:
    result = await session.execute(
        select(ExecutionLog).order_by(ExecutionLog.id.desc()).limit(limit)
    )
    return list(result.scalars().all())
