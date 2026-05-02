"""SQLAlchemy 2.0 models — five tables per the v1 spec."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

PackageStatus = Literal["draft", "ready", "in-progress", "done", "abandoned"]
DecisionStatus = Literal["proposed", "ratified", "superseded"]
DiscoveryKind = Literal["blocker", "insight", "hypothesis", "risk"]
DiscoveryStatus = Literal["open", "resolved", "absorbed"]
Actor = Literal["human", "agent"]
AbsorbedKind = Literal["package", "decision"]


class Base(DeclarativeBase):
    pass


class Package(Base):
    __tablename__ = "packages"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','ready','in-progress','done','abandoned')",
            name="ck_packages_status",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft")
    goal: Mapped[str | None] = mapped_column(Text)
    acceptance_criteria: Mapped[str | None] = mapped_column(Text)
    out_of_scope: Mapped[str | None] = mapped_column(Text)
    decisions_made: Mapped[str | None] = mapped_column(Text)
    verification: Mapped[str | None] = mapped_column(Text)
    paths_glob: Mapped[list[str] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column()


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('proposed','ratified','superseded')",
            name="ck_decisions_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="proposed")
    context: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    alternatives: Mapped[str | None] = mapped_column(Text)
    consequences: Mapped[str | None] = mapped_column(Text)
    superseded_by: Mapped[int | None] = mapped_column(ForeignKey("decisions.id"))
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    ratified_at: Mapped[datetime | None] = mapped_column()


class Discovery(Base):
    __tablename__ = "discoveries"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('blocker','insight','hypothesis','risk')",
            name="ck_discoveries_kind",
        ),
        CheckConstraint(
            "status IN ('open','resolved','absorbed')",
            name="ck_discoveries_status",
        ),
        CheckConstraint(
            "absorbed_into_kind IS NULL OR absorbed_into_kind IN ('package','decision')",
            name="ck_discoveries_absorbed_kind",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    resolution: Mapped[str | None] = mapped_column(Text)
    package_id: Mapped[str | None] = mapped_column(ForeignKey("packages.id"))
    # Stored as TEXT — package IDs are strings, decision IDs are integers stringified.
    # Spec called this INTEGER but `into_kind='package'` requires text.
    absorbed_into_id: Mapped[str | None] = mapped_column(String)
    absorbed_into_kind: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column()


class ExecutionLog(Base):
    __tablename__ = "execution_log"
    __table_args__ = (
        CheckConstraint("actor IN ('human','agent')", name="ck_log_actor"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    package_id: Mapped[str] = mapped_column(ForeignKey("packages.id"), nullable=False)
    actor: Mapped[str] = mapped_column(String, nullable=False)
    entry: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(nullable=False)


class StateSection(Base):
    __tablename__ = "state_sections"

    name: Mapped[str] = mapped_column(String, primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)
