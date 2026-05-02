"""Atomic file writes — tmp + os.replace, so readers never see partial state."""
from __future__ import annotations

import os
import secrets
from pathlib import Path


def write_atomic(target: Path, content: str) -> None:
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + f".tmp.{os.getpid()}.{secrets.token_hex(4)}")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, target)
