"""AC #7 (in-process) — state persists across engine restarts on the same DB file."""
from __future__ import annotations

from pathlib import Path

from throughline.db.session import build_engine, build_sessionmaker, init_db
from throughline.events import MutationBus
from throughline.services import packages as packages_svc


async def test_state_persists_across_engine_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"

    # session 1 — write a package
    eng1 = build_engine(db_path)
    await init_db(eng1)
    Session1 = build_sessionmaker(eng1)
    bus = MutationBus()
    async with Session1() as s:
        await packages_svc.create_package(
            s, bus, id="R", title="restart test", goal="g", actor="human"
        )
    await eng1.dispose()

    # session 2 — open same file, read it back
    eng2 = build_engine(db_path)
    Session2 = build_sessionmaker(eng2)
    async with Session2() as s:
        pkg = await packages_svc.get_package(s, "R")
    assert pkg.title == "restart test"
    assert pkg.status == "draft"
    await eng2.dispose()
