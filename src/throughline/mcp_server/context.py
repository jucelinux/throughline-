"""ServiceContext — bundles sessionmaker + bus passed to MCP tool wrappers."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from throughline.events import MutationBus


@dataclass(slots=True, frozen=True)
class ServiceContext:
    sessionmaker: async_sessionmaker[AsyncSession]
    bus: MutationBus

    def session(self):
        return self.sessionmaker()
