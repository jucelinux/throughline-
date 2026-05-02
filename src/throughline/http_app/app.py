"""build_app() — Starlette ASGI app with header dispatch + /health + lifespan."""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from throughline.config import Settings, get_settings
from throughline.db.session import build_engine, build_sessionmaker, init_db
from throughline.events import MutationBus
from throughline.mcp_server.agent import build_agent_mcp
from throughline.mcp_server.context import ServiceContext
from throughline.mcp_server.human import build_human_mcp
from throughline.render.worker import render_worker

logger = logging.getLogger(__name__)


def _make_dispatcher(human_app, agent_app):
    async def dispatcher(scope, receive, send):
        if scope["type"] != "http":
            return
        actor: str | None = None
        for k, v in scope.get("headers", []):
            if k == b"x-throughline-actor":
                actor = v.decode()
                break
        if actor == "human":
            await human_app(scope, receive, send)
            return
        if actor == "agent":
            await agent_app(scope, receive, send)
            return
        body = json.dumps(
            {
                "error": (
                    "X-Throughline-Actor header required, "
                    "must be 'human' or 'agent'"
                )
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 400,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": body})

    return dispatcher


def _make_health(sessionmaker: async_sessionmaker[AsyncSession]):
    from sqlalchemy import text

    async def health(_: Request) -> JSONResponse:
        try:
            async with sessionmaker() as s:
                await s.execute(text("SELECT 1"))
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"status": "error", "detail": str(e)}, status_code=503)
        return JSONResponse({"status": "ok"})

    return health


def build_app(settings: Settings | None = None) -> Starlette:
    settings = settings or get_settings()
    engine = build_engine(settings.db_path)
    sessionmaker = build_sessionmaker(engine)
    bus = MutationBus()
    ctx = ServiceContext(sessionmaker=sessionmaker, bus=bus)

    human_mcp = build_human_mcp(ctx, settings)
    agent_mcp = build_agent_mcp(ctx, settings)
    human_app = human_mcp.streamable_http_app()
    agent_app = agent_mcp.streamable_http_app()
    debounce_s = settings.debounce_ms / 1000.0

    @asynccontextmanager
    async def lifespan(app: Starlette):
        await init_db(engine)
        async with human_app.router.lifespan_context(human_app):
            async with agent_app.router.lifespan_context(agent_app):
                # cold-start regeneration so .docs/ matches DB even if stale
                await bus.signal()
                worker = asyncio.create_task(
                    render_worker(bus, sessionmaker, settings.docs_dir, debounce_s)
                )
                try:
                    yield
                finally:
                    worker.cancel()
                    try:
                        await worker
                    except asyncio.CancelledError:
                        pass
                    await engine.dispose()

    return Starlette(
        lifespan=lifespan,
        routes=[
            Route("/health", _make_health(sessionmaker)),
            Mount("/mcp", app=_make_dispatcher(human_app, agent_app)),
        ],
    )
