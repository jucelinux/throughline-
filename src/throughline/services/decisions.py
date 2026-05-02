"""Decision (ADR-lite) services."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from throughline.db.models import Decision
from throughline.events import MutationBus
from throughline.exceptions import NotFoundError, TransitionError, ValidationError
from throughline.services._audit import now


async def get_decision(session: AsyncSession, id: int) -> Decision:
    dec = await session.get(Decision, id)
    if dec is None:
        raise NotFoundError(f"decision {id} not found")
    return dec


async def propose_decision(
    session: AsyncSession,
    bus: MutationBus,
    *,
    title: str,
    context: str,
    decision: str,
    alternatives: str | None = None,
    consequences: str | None = None,
) -> Decision:
    if not title.strip() or not context.strip() or not decision.strip():
        raise ValidationError("title, context, and decision are required")
    dec = Decision(
        title=title,
        status="proposed",
        context=context,
        decision=decision,
        alternatives=alternatives,
        consequences=consequences,
        created_at=now(),
    )
    session.add(dec)
    await session.commit()
    await session.refresh(dec)
    await bus.signal()
    return dec


async def ratify_decision(
    session: AsyncSession, bus: MutationBus, *, id: int
) -> Decision:
    dec = await get_decision(session, id)
    if dec.status != "proposed":
        raise TransitionError(
            f"ratify_decision requires status='proposed' (got '{dec.status}')"
        )
    dec.status = "ratified"
    dec.ratified_at = now()
    await session.commit()
    await session.refresh(dec)
    await bus.signal()
    return dec


async def supersede_decision(
    session: AsyncSession, bus: MutationBus, *, old_id: int, new_id: int
) -> Decision:
    if old_id == new_id:
        raise ValidationError("cannot supersede a decision with itself")
    old = await get_decision(session, old_id)
    new = await get_decision(session, new_id)
    if old.status == "superseded":
        raise TransitionError(f"decision {old_id} is already superseded")
    if new.status != "ratified":
        raise TransitionError(
            f"superseding decision must be ratified (id={new_id} is '{new.status}')"
        )
    old.status = "superseded"
    old.superseded_by = new.id
    await session.commit()
    await session.refresh(old)
    await bus.signal()
    return old


async def list_decisions(session: AsyncSession) -> list[Decision]:
    result = await session.execute(select(Decision).order_by(Decision.id.asc()))
    return list(result.scalars().all())
