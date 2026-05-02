@./.docs/active-context.md

# Working on throughline

This repository *is* throughline — a Python MCP server that brokers state
between Claude Desktop and Claude Code. The line above pulls the current
package context (active package, open discoveries, recent decisions) from the
throughline server running on this machine.

If the active-context block above is empty or visibly stale, see
**[Activating throughline](#activating-throughline)** below and bring the
server up before doing further work.

## Activating throughline

1. **Start the server.** From the repo root:
   ```bash
   docker compose up -d --build
   curl -fsS http://localhost:8765/health   # → {"status":"ok"}
   ```
   Or for plain Python (no container):
   ```bash
   source .venv/bin/activate
   python -m throughline
   ```

2. **The agent connection is project-scoped.** `.mcp.json` at the repo root
   already points Claude Code at `http://localhost:8765/mcp/` with header
   `X-Throughline-Actor: agent`. Nothing to wire by hand — opening this repo
   in Code picks it up automatically. (For the Desktop side, see README.md.)

3. **Verify**: in a Claude Code session, `tools/list` should show 6
   throughline tools — `set_package_status`, `update_package_field`,
   `record_discovery`, `resolve_discovery`, `append_log`, `patch_state`. If
   not, the server isn't running or the connection didn't load; fix that
   before further work.

## Layering rule (strict)

`services/` MUST NOT import from `mcp_server/` or `http_app/`. Tool handlers
are thin wrappers; actor identity (`"human"`/`"agent"`) is a closure constant
per sub-app, never a `contextvar`.

## Mutation pattern (strict)

Every service mutator runs in this exact order:

```
validate → DB work → audit row → await session.commit() → await bus.signal()
```

Signaling before commit makes the render worker read stale state. Auto-audit
(an `ExecutionLog` row tagged with the actor) is required on every mutation,
not optional — it's how human work shows up alongside agent work in the log.

## Tests

`pytest -q` runs the suite in ~3 seconds (46 tests). Integration tests drive
the Starlette app via `httpx.AsyncClient(transport=ASGITransport)` with
`asgi-lifespan` — no subprocess, no real network. SQLite fixtures use real
files in `tmp_path` (not `:memory:`) because WAL requires a real file.

When debugging the debouncer, set `THROUGHLINE_DEBOUNCE_MS=20` (or inject via
the `Settings` fixture in the test). Don't mock `asyncio.sleep`.

## Render layer

- All writes to `.docs/` go through `render.atomic.write_atomic` (tmp +
  `os.replace`) so the harness never sees a partial read.
- The render worker uses the **drain-quiet** debouncer pattern in
  `render/worker.py`. Inverting it (putting `wait_for` at the top of the
  outer loop) breaks under sustained mutation. Don't refactor that shape.

## Spec deviations

Recorded in `README.md` under "Spec deviations". Adding a new deviation? Note
it there in the same PR — don't ship a divergence the spec wouldn't catch up
on.

## Working *with* throughline on throughline (self-hosting loop)

Throughline is its own first user. While advancing work in this repo, drive
state forward through the agent tools rather than relying on commit messages
and memory:

- Starting work on a package: `set_package_status(id, "in-progress")`.
- Blocker, insight, hypothesis, or risk found mid-flight:
  `record_discovery(kind, title, body, package_id)` — don't bury it in code
  comments.
- Inline design choice you locked in: `update_package_field(id,
  "decisions_made", "<text>")`.
- Verification recipe: `update_package_field(id, "verification", "<text>")`.
- Narrative log line: `append_log(package_id, "<entry>")`.
- A discovery is now resolved: `resolve_discovery(id, "<resolution>")`.
- Package finished: `set_package_status(id, "done")`.

If `acceptance_criteria` needs revision after commit, the agent has no tool
for it — by design. Record a discovery describing what the AC should become
and surface it; the human absorbs it via `update_package` (which only works
on `draft`) or by reopening with a new package.

## Environment quirks

- Python 3.12+ is required; the project venv lives in `.venv/`.
- SQLite WAL needs a real Linux filesystem. On WSL, keep the repo under
  `~/dev/...`, not `/mnt/c/...`.
- Container bind-mounts `./.throughline/` (DB + WAL siblings, must mount the
  whole directory) and `./.docs/` (rendered markdown). The container's
  entrypoint chowns both to uid 1000 before dropping privileges via gosu —
  see `scripts/entrypoint.sh`.
- `.docs/state.md`, `.docs/active-context.md`, and `.docs/execution-log.md`
  are gitignored (auto-rendered from the DB). `.docs/packages/` and
  `.docs/decisions/` are tracked.
