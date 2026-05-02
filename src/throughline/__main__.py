"""Entrypoint: python -m throughline → uvicorn server."""
from __future__ import annotations

import logging

import uvicorn

from throughline.config import get_settings
from throughline.http_app.app import build_app


def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = build_app(settings)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level=settings.log_level.lower())


if __name__ == "__main__":
    main()
