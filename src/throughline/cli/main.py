"""Typer CLI: `throughline init`, `throughline serve`."""
from __future__ import annotations

from pathlib import Path

import typer

from throughline.cli.bootstrap import init_project

app = typer.Typer(
    name="throughline",
    help="MCP state bus for Claude Desktop ↔ Claude Code.",
    no_args_is_help=True,
)


@app.command()
def init(
    target: Path = typer.Argument(
        Path("."),
        help="Target project directory (defaults to current directory).",
    ),
) -> None:
    """Bootstrap a project: create .docs/, .throughline/, docker-compose.yml, edit .claude/CLAUDE.md."""
    actions = init_project(target)
    if not actions:
        typer.echo("nothing to do — project already bootstrapped.")
        return
    for a in actions:
        typer.echo(f"  • {a}")
    typer.echo(f"\nbootstrapped {len(actions)} change(s) in {target.resolve()}")


@app.command()
def serve() -> None:
    """Start the throughline server (delegates to python -m throughline)."""
    from throughline.__main__ import main as run_server

    run_server()


if __name__ == "__main__":
    app()
