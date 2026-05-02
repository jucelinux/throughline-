"""AC #5 — `throughline init` is correct and idempotent."""
from __future__ import annotations

from pathlib import Path

from throughline.cli.bootstrap import (
    CLAUDE_INCLUDE_LINE,
    GITIGNORE_LINE,
    init_project,
)


def test_bootstrap_creates_layout(tmp_path: Path) -> None:
    actions = init_project(tmp_path)
    assert actions, "expected at least one action"
    assert (tmp_path / ".docs").is_dir()
    assert (tmp_path / ".docs" / "packages").is_dir()
    assert (tmp_path / ".docs" / "decisions").is_dir()
    assert (tmp_path / ".throughline").is_dir()
    assert (tmp_path / ".docs" / "state.md").exists()
    assert (tmp_path / ".docs" / "active-context.md").exists()
    assert (tmp_path / "docker-compose.yml").exists()

    gitignore = (tmp_path / ".gitignore").read_text()
    assert GITIGNORE_LINE in gitignore.splitlines()

    claude = (tmp_path / ".claude" / "CLAUDE.md").read_text()
    assert CLAUDE_INCLUDE_LINE in claude.splitlines()


def test_bootstrap_idempotent(tmp_path: Path) -> None:
    init_project(tmp_path)
    second = init_project(tmp_path)
    assert second == [], f"second run reported actions: {second}"

    gitignore = (tmp_path / ".gitignore").read_text()
    assert gitignore.count(GITIGNORE_LINE) == 1, gitignore

    claude = (tmp_path / ".claude" / "CLAUDE.md").read_text()
    assert claude.count(CLAUDE_INCLUDE_LINE) == 1, claude


def test_bootstrap_appends_to_existing_files(tmp_path: Path) -> None:
    """If .gitignore or CLAUDE.md already exist with content, init must not clobber them."""
    (tmp_path / ".gitignore").write_text("node_modules/\nvenv/\n")
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "CLAUDE.md").write_text("# my project\n\nsome notes\n")

    init_project(tmp_path)

    gitignore = (tmp_path / ".gitignore").read_text()
    assert "node_modules/" in gitignore
    assert GITIGNORE_LINE in gitignore.splitlines()

    claude = (tmp_path / ".claude" / "CLAUDE.md").read_text()
    assert "# my project" in claude
    assert CLAUDE_INCLUDE_LINE in claude.splitlines()


def test_bootstrap_handles_missing_trailing_newline(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("foo")  # no trailing newline
    init_project(tmp_path)
    out = (tmp_path / ".gitignore").read_text()
    lines = out.splitlines()
    assert "foo" in lines
    assert GITIGNORE_LINE in lines
