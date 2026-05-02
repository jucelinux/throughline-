"""Free-form state sections — patch_state with per-actor allowlist."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from throughline.db.models import Actor, StateSection
from throughline.events import MutationBus
from throughline.exceptions import ValidationError
from throughline.services._audit import now

AGENT_ALLOWED_SECTIONS = frozenset(
    {"active_packages_summary", "recent_discoveries", "latest_activity"}
)


async def patch_state(
    session: AsyncSession,
    bus: MutationBus,
    *,
    name: str,
    content: str,
    actor: Actor,
    allowed_sections: frozenset[str] | None = None,
) -> StateSection:
    if not name or not name.strip():
        raise ValidationError("section name is required")
    if allowed_sections is not None and name not in allowed_sections:
        raise ValidationError(
            f"section '{name}' is not patchable by {actor} "
            f"(allowed: {sorted(allowed_sections)})"
        )

    existing = await session.get(StateSection, name)
    if existing is None:
        section = StateSection(name=name, content=content, updated_at=now())
        session.add(section)
    else:
        existing.content = content
        existing.updated_at = now()
        section = existing
    await session.commit()
    await session.refresh(section)
    await bus.signal()
    return section


async def list_sections(session: AsyncSession) -> list[StateSection]:
    result = await session.execute(select(StateSection).order_by(StateSection.name))
    return list(result.scalars().all())
