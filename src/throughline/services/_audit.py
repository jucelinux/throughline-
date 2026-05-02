"""Auto-audit helper — every mutation adds an ExecutionLog row."""
from __future__ import annotations

from datetime import datetime, timezone

from throughline.db.models import Actor, ExecutionLog


def now() -> datetime:
    return datetime.now(timezone.utc)


def audit_row(package_id: str, actor: Actor, entry: str) -> ExecutionLog:
    return ExecutionLog(
        package_id=package_id,
        actor=actor,
        entry=entry,
        timestamp=now(),
    )
