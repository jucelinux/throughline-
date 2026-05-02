"""Convert ORM rows into JSON-friendly dicts for MCP responses."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from throughline.db.models import (
    Decision,
    Discovery,
    ExecutionLog,
    Package,
    StateSection,
)


def _iso(ts: datetime | None) -> str | None:
    return ts.isoformat() if ts is not None else None


def package_dict(p: Package) -> dict[str, Any]:
    return {
        "id": p.id,
        "title": p.title,
        "status": p.status,
        "goal": p.goal,
        "acceptance_criteria": p.acceptance_criteria,
        "out_of_scope": p.out_of_scope,
        "decisions_made": p.decisions_made,
        "verification": p.verification,
        "paths_glob": p.paths_glob,
        "created_at": _iso(p.created_at),
        "updated_at": _iso(p.updated_at),
        "closed_at": _iso(p.closed_at),
    }


def decision_dict(d: Decision) -> dict[str, Any]:
    return {
        "id": d.id,
        "title": d.title,
        "status": d.status,
        "context": d.context,
        "decision": d.decision,
        "alternatives": d.alternatives,
        "consequences": d.consequences,
        "superseded_by": d.superseded_by,
        "created_at": _iso(d.created_at),
        "ratified_at": _iso(d.ratified_at),
    }


def discovery_dict(d: Discovery) -> dict[str, Any]:
    return {
        "id": d.id,
        "kind": d.kind,
        "title": d.title,
        "body": d.body,
        "status": d.status,
        "resolution": d.resolution,
        "package_id": d.package_id,
        "absorbed_into_id": d.absorbed_into_id,
        "absorbed_into_kind": d.absorbed_into_kind,
        "created_at": _iso(d.created_at),
        "resolved_at": _iso(d.resolved_at),
    }


def log_dict(row: ExecutionLog) -> dict[str, Any]:
    return {
        "id": row.id,
        "package_id": row.package_id,
        "actor": row.actor,
        "entry": row.entry,
        "timestamp": _iso(row.timestamp),
    }


def state_section_dict(s: StateSection) -> dict[str, Any]:
    return {
        "name": s.name,
        "content": s.content,
        "updated_at": _iso(s.updated_at),
    }
