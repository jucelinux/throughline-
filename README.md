# throughline

> A state bus and harness orchestrator for the **Claude Desktop ↔ Claude Code** flow.
> An MCP server that keeps your project context alive across both surfaces, so you
> stop copy-pasting artifacts by hand and re-explaining context every session.

**Status: v1, dogfood.** Functional enough that the author uses it to manage the
project's own subsequent packages. Not production-grade yet — read
[Current state and what to expect](#current-state-and-what-to-expect) before adopting.

---

## The problem it solves

The natural Claude flow is: **ideate/discuss/prioritize in Desktop, execute in Code**.
In practice today that requires constant manual translation:

- Copy the work package from Desktop into the Code repo.
- Re-explain context every new session.
- Lose state updates between the two surfaces.
- Decisions and discoveries that vanish because they never became an artifact anywhere.

**throughline** removes that translation. It's an MCP server that both sides
(Desktop and Code) consume, with **typed, shared state** plus an always-fresh
markdown file the Code harness automatically pulls into context.

---

## How it works, in one breath

```
        ┌─────────────────┐                        ┌──────────────┐
        │ Claude Desktop  │ ── X-Throughline-      │ Claude Code  │
        │   (human)       │    Actor: human        │   (agent)    │
        └────────┬────────┘                        └──────┬───────┘
                 │            HTTP/JSON-RPC               │
                 │            X-Throughline-Actor: agent  │
                 ▼                                        ▼
            ┌──────────────────────────────────────────────────┐
            │           throughline (HTTP MCP on :8765)        │
            │  ┌──────────────┐  ┌─────────────────────────┐   │
            │  │ 9 tools      │  │ 6 tools                 │   │
            │  │ (human)      │  │ (agent)                 │   │
            │  └──────┬───────┘  └────────────┬────────────┘   │
            │         └───── services ────────┘                │
            │                    │                             │
            │              SQLite (WAL) + mutation bus         │
            │                    │                             │
            │           render worker (500ms debounce)         │
            └────────────────────┬─────────────────────────────┘
                                 ▼
                    ┌────────────────────────────┐
                    │ .docs/state.md             │  ← full snapshot
                    │ .docs/active-context.md    │  ← injected into CLAUDE.md
                    └────────────────────────────┘
```

- **One toolset per surface.** The client passes an `X-Throughline-Actor` header
  on the handshake. Desktop connects as `human` (9 tools — create package, propose
  decision, etc). Code connects as `agent` (6 tools — record discovery, advance
  status, append log). No header → 400.
- **Typed state.** Five SQLite tables — packages, decisions, discoveries,
  execution log, free-form sections. Markdown is generated *from* the DB, never
  the other way around.
- **Reactivity.** Every mutation pushes a signal to an `asyncio.Queue`. A worker
  using a *drain-quiet* pattern waits for 500ms of silence before regenerating
  `state.md` and `active-context.md` (coalesces bursts of mutations).
- **Bridge to the harness.** `throughline init` adds an
  `@./.docs/active-context.md` line to your project's `.claude/CLAUDE.md`. Each
  Code session reads that file automatically and inherits the active package +
  open discoveries + recent decisions — without you re-explaining anything.

---

## Current state and what to expect

| Item | Status |
| --- | --- |
| HTTP server, /health, header dispatch | ✅ verified |
| 9 human + 6 agent tools over JSON-RPC | ✅ 46 tests passing |
| Debounced rendering of `state.md` and `active-context.md` | ✅ verified |
| SQLite (WAL) persistence across in-process restarts | ✅ verified |
| Idempotent bootstrap on target projects | ✅ verified |
| Healthcheck via `docker compose up` | 🟡 manual |
| Restart preserving state via `docker compose down/up` | 🟡 manual |
| Connecting real Claude Desktop / Code to the MCP endpoint | 🟡 instructions below, not yet validated end-to-end |
| Multi-project, full-text search, decision revisitation | ❌ explicitly out of scope for v1 |

Bugs and spec deviations are listed under [Spec deviations](#spec-deviations-v1).

---

## Run it locally

Requirements: **Python 3.12+** and **Docker** (optional, recommended for restart resilience).

### Option A — Docker (recommended)

```bash
git clone git@github.com:jucelinux/throughline-.git throughline
cd throughline
docker compose up -d --build
docker compose logs -f throughline   # wait for "Application startup complete"
curl -fsS http://localhost:8765/health
# {"status":"ok"}
```

The bind-mount creates `.throughline/` (DB) and `.docs/` (markdown) under the repo
directory. Both are gitignored — the DB persists across restarts.

> **WSL users**: keep the repo on a real Linux filesystem (`~/dev/...`), not on
> `/mnt/c/...`. SQLite WAL breaks under bind-mounts on Windows drives.

### Option B — plain Python, no container

```bash
git clone git@github.com:jucelinux/throughline-.git throughline
cd throughline
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m throughline
# INFO  Started server process
# INFO  Uvicorn running on http://127.0.0.1:8765
```

In another terminal:

```bash
curl -fsS http://localhost:8765/health
```

Environment variables (all optional; defaults in parentheses):

| Variable | Default | Description |
| --- | --- | --- |
| `THROUGHLINE_HOST` | `127.0.0.1` | Bind address. Use `0.0.0.0` inside containers. |
| `THROUGHLINE_PORT` | `8765` | HTTP port. |
| `THROUGHLINE_DB_PATH` | `.throughline/state.db` | SQLite path (WAL siblings live next to it). |
| `THROUGHLINE_DOCS_DIR` | `.docs` | Where `state.md` and `active-context.md` get written. |
| `THROUGHLINE_DEBOUNCE_MS` | `500` | Render-worker coalescing window. |
| `THROUGHLINE_LOG_LEVEL` | `INFO` | Set to `DEBUG` to trace each mutation. |
| `THROUGHLINE_ALLOWED_HOSTS` | `127.0.0.1:*,localhost:*,[::1]:*` | DNS rebinding allowlist enforced by the MCP SDK. |

---

## Connecting Claude Desktop and Claude Code

> The flow below is the design. Real client wiring has **not been validated
> end-to-end** by the author yet — if you try it before I do, please open an
> issue with what you see.

### Claude Desktop (human, 9 tools)

Edit `~/.config/Claude/claude_desktop_config.json` (Linux/Mac) or
`%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "throughline": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "http://localhost:8765/mcp/",
        "--allow-http",
        "--header",
        "X-Throughline-Actor:human"
      ]
    }
  }
}
```

Restart Desktop. The 9 tools (`create_package`, `commit_package`,
`propose_decision`, etc.) should appear.

### Claude Code (agent, 6 tools)

In your **target project** directory (not in the throughline repo), run the
bootstrap first:

```bash
throughline init   # creates .docs/, .throughline/, edits .claude/CLAUDE.md
```

Then register the MCP server in one of two scopes:

- **Project-scoped** (recommended, checked in with the repo): drop a
  `.mcp.json` at the project root —
  ```json
  {
    "mcpServers": {
      "throughline": {
        "type": "http",
        "url": "http://localhost:8765/mcp/",
        "headers": {
          "X-Throughline-Actor": "agent",
          "Accept": "application/json, text/event-stream"
        }
      }
    }
  }
  ```
  This repo ships its own `.mcp.json` as a working example.

- **User-scoped** (one config across all projects): `claude mcp add` or
  edit `~/.claude.json` with the same shape.

The `@./.docs/active-context.md` line that bootstrap adds to your `.claude/CLAUDE.md`
makes Code inject the active context automatically each session.

---

## Smoke test without an MCP client

When you just want to confirm the server is wired right, without spinning up
Desktop or Code:

```bash
INIT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}'
LIST='{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
HEADERS='-H Accept:application/json,text/event-stream -H Content-Type:application/json'

for actor in human agent; do
  curl -fsS $HEADERS -H "X-Throughline-Actor: $actor" -d "$INIT" http://localhost:8765/mcp/ > /dev/null
  echo -n "$actor: "
  curl -fsS $HEADERS -H "X-Throughline-Actor: $actor" -d "$LIST" http://localhost:8765/mcp/ \
    | python -c 'import json,sys; r=json.load(sys.stdin); print(len(r["result"]["tools"]),"tools")'
done
# expected:
#   human: 9 tools
#   agent: 6 tools

curl -sS -o /dev/null -w "no header: HTTP %{http_code}\n" $HEADERS -d "$INIT" http://localhost:8765/mcp/
# no header: HTTP 400
```

---

## Tool surface

| Actor | Tool | What it does |
| --- | --- | --- |
| human | `create_package(id, title, goal?, paths_glob?)` | Create a `draft` package. |
| human | `update_package(id, **fields)` | Edit fields while in `draft`. |
| human | `commit_package(id)` | `draft → ready` (validates `acceptance_criteria > 30 chars`). |
| human | `abandon_package(id, reason)` | `* → abandoned` (except from `done`). |
| human | `propose_decision(...)` | Record a `proposed` decision. |
| human | `ratify_decision(id)` | `proposed → ratified`. |
| human | `supersede_decision(old_id, new_id)` | Mark old as `superseded`. |
| human | `absorb_discovery(discovery_id, into_kind, into_id)` | Move a discovery into a package or decision. |
| human | `patch_state(section, content)` | Write any free-form section. |
| agent | `set_package_status(id, new_status)` | `ready → in-progress → done\|abandoned`. |
| agent | `update_package_field(id, field, value)` | Edit only `decisions_made` or `verification`. |
| agent | `record_discovery(kind, title, body, package_id?)` | Create an `open` discovery. |
| agent | `resolve_discovery(id, resolution)` | `open → resolved`. |
| agent | `append_log(package_id, entry)` | Free-text narrative log line. |
| agent | `patch_state(section, content)` | Restricted to `active_packages_summary`, `recent_discoveries`, `latest_activity`. |

Read-only resources (both actors):
`throughline://state`, `throughline://active-context`, `throughline://packages`,
`throughline://package/{id}`, `throughline://decisions`, `throughline://decision/{id}`,
`throughline://discoveries/open`.

---

## Code layout

```
src/throughline/
├── config.py            pydantic-settings (THROUGHLINE_* env vars)
├── exceptions.py        ServiceError, ValidationError, TransitionError, NotFoundError
├── events.py            MutationBus (asyncio.Queue)
├── db/                  SQLAlchemy 2.0 models, async engine, WAL pragma listener
├── services/            per-entity business logic — only depends on db/ and events.py
├── render/              state_md / active_context_md + atomic write + drain-quiet worker
├── mcp_server/          build_human_mcp(), build_agent_mcp(), 7 shared resources
├── http_app/            Starlette dispatch + /health + lifespan
├── cli/                 Typer: `throughline init`, `throughline serve`
└── __main__.py          uvicorn entrypoint
```

**Layering rule** (enforced by imports): `services/` never imports from
`mcp_server/` or `http_app/`. Tool handlers are thin wrappers; the actor
identity (`"human"`/`"agent"`) is a closure constant per sub-app, not a
`contextvar`.

---

## Spec deviations (v1)

[`.docs/packages/001-build-throughline-v1.md`](.docs/packages/001-build-throughline-v1.md) is the originating spec. The points
below differ from what's written there and are recorded for explicit amendment:

- **`absorbed_into_id` is `TEXT`, not `INTEGER`.** Package IDs are strings; with
  INTEGER, absorbing a discovery into a package would silently lose the link.
- **Resource URI uses path filtering, not a query string.** The spec wrote
  `throughline://discoveries?status=open`; FastMCP only supports path templates,
  so the implemented URI is `throughline://discoveries/open`.
- **`tools/list` is JSON-RPC POST, not GET.** The `curl /mcp/tools/list` in the
  spec is shorthand; Streamable HTTP uses POST with a JSON-RPC payload.
- **Per-actor toolsets are implemented as two FastMCP instances** plus an ASGI
  dispatcher that reads `X-Throughline-Actor`. The `mcp` SDK has no first-class
  per-request `tools/list` filtering (open issues #1063, #1509).

---

## Development

```bash
pip install -e ".[dev]"
pytest                          # 46 tests (~3s)
pytest tests/integration -v     # AC #2-#7 end-to-end
pytest tests/unit -k debouncer  # one specific case
```

Acceptance-criteria coverage:

- AC #2 (handshake 9/6/400) → `tests/integration/test_handshake.py`
- AC #3 (full cycle) + AC #4 (≥3 regenerations) → `tests/integration/test_full_cycle.py`
- AC #5 (`throughline init` idempotent) → `tests/integration/test_bootstrap.py`
- AC #6 (decision + discovery) → `tests/integration/test_decision_discovery.py`
- AC #7 (cross-engine persistence) → `tests/integration/test_resilience.py`
- AC #1 and the cross-restart half of #7 → manual (need Docker running)

---

## Known roadmap

Items out of v1 but on the radar (in rough order of likelihood):

- v1.1: per-tool test coverage (not just AC), separate per-package and
  per-decision markdown files, basic observability.
- v2: temporal decision revisitation (TTL + reminder), full-text search,
  importing legacy packages (manual markdown → DB), multi-project support.
- explicitly **out**: UI, git/PR integration, custom hooks,
  auth/permissions beyond the actor header.

---

## Contributing

Issues and PRs welcome. Before opening a larger PR, file an issue describing
your design — the project has strong opinions about v1 scope, and a lot of what
looks "missing" was deferred deliberately (see "Out of scope" in
[the spec](.docs/packages/001-build-throughline-v1.md)).

When reporting a bug, include:

- Python version (`python --version`)
- How you started it (Docker or plain Python)
- Contents of `.throughline/` and `.docs/` if relevant
- Server log (`docker compose logs throughline` or stdout)

---

## License

MIT.
