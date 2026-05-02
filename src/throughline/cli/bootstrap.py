"""`throughline init` — idempotent project bootstrap."""
from __future__ import annotations

from pathlib import Path

CLAUDE_INCLUDE_LINE = "@./.docs/active-context.md"
GITIGNORE_LINE = ".throughline/"
DOCKER_COMPOSE_TEMPLATE = """\
services:
  throughline:
    image: throughline:local
    container_name: throughline
    ports:
      - "8765:8765"
    environment:
      THROUGHLINE_HOST: "0.0.0.0"
      THROUGHLINE_PORT: "8765"
      THROUGHLINE_DB_PATH: "/app/.throughline/state.db"
      THROUGHLINE_DOCS_DIR: "/app/.docs"
    volumes:
      - ./.throughline:/app/.throughline
      - ./.docs:/app/.docs
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8765/health"]
      interval: 10s
      timeout: 3s
      retries: 5
    restart: unless-stopped
"""


def _has_line(path: Path, line: str) -> bool:
    if not path.exists():
        return False
    target = line.strip()
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.strip() == target:
            return True
    return False


def _append_line(path: Path, line: str) -> None:
    """Append line to path, ensuring it ends with exactly one newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        sep = "" if existing.endswith("\n") or existing == "" else "\n"
        path.write_text(existing + sep + line + "\n", encoding="utf-8")
    else:
        path.write_text(line + "\n", encoding="utf-8")


def init_project(target: Path) -> list[str]:
    """Run the bootstrap. Returns a list of human-readable change descriptions."""
    target = Path(target).resolve()
    actions: list[str] = []

    docs = target / ".docs"
    state_dir = target / ".throughline"
    packages_dir = docs / "packages"
    decisions_dir = docs / "decisions"

    for d in (docs, packages_dir, decisions_dir, state_dir):
        if not d.exists():
            d.mkdir(parents=True)
            actions.append(f"created {d.relative_to(target)}/")

    state_md = docs / "state.md"
    if not state_md.exists():
        state_md.write_text(
            "# throughline\n\n_(state will be populated when the server runs)_\n",
            encoding="utf-8",
        )
        actions.append("seeded .docs/state.md")

    active_md = docs / "active-context.md"
    if not active_md.exists():
        active_md.write_text(
            "# Active package\n\n_no active package_\n",
            encoding="utf-8",
        )
        actions.append("seeded .docs/active-context.md")

    compose = target / "docker-compose.yml"
    if not compose.exists():
        compose.write_text(DOCKER_COMPOSE_TEMPLATE, encoding="utf-8")
        actions.append("wrote docker-compose.yml")

    gitignore = target / ".gitignore"
    if not _has_line(gitignore, GITIGNORE_LINE):
        _append_line(gitignore, GITIGNORE_LINE)
        actions.append(f"added '{GITIGNORE_LINE}' to .gitignore")

    claude_md = target / ".claude" / "CLAUDE.md"
    if not _has_line(claude_md, CLAUDE_INCLUDE_LINE):
        _append_line(claude_md, CLAUDE_INCLUDE_LINE)
        actions.append(f"added '{CLAUDE_INCLUDE_LINE}' to .claude/CLAUDE.md")

    return actions
