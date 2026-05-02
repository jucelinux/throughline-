---
id: "001"
title: "Bootstrap throughline v1"
status: draft
owner: jucelino
created: 2026-05-01
last-updated: 2026-05-01
related:
  - .docs/state.md
  - .docs/active-context.md
  - .claude/CLAUDE.md
paths:
  - "**"
---

# Bootstrap throughline v1

## Goal

Build the complete v1 of **throughline**, an MCP server that acts as a state bus
and harness orchestrator for the Desktop ↔ Code flow, running in Docker over HTTP,
with four layers: bus, structured knowledge, transition policy, and ergonomics
for the agent. After this package, every subsequent package in the project will
be created, executed, and closed through throughline itself — the system is its
own first user.

## Context and why it exists

The intended flow is: ideation/discussion/prioritization in Claude Desktop,
execution in Claude Code, with project state shared between the two surfaces.
Today that flow requires manual translation (copying artifacts between sides,
re-explaining context every session, losing state updates). throughline removes
the translation and enforces minimal discipline at phase transitions.

v1 doesn't cover the entire intended flow — it covers enough to be dogfooded
immediately. It is deliberately undersized in some respects (simple ADRs without
multi-stage ratification, no temporal revisitation, no advanced search) because
real-usage evidence should drive v2, not hypotheses.

## Architecture

### Stack

- **Language**: Python 3.12+
- **MCP SDK**: `mcp` (official, with HTTP transport support)
- **DB**: SQLite with WAL mode
- **ORM**: SQLAlchemy 2.x (style 2.0, with Mapped types)
- **Validation**: Pydantic v2 for tool schemas and frontmatter
- **Transport**: Streamable HTTP on `localhost:8765`
- **Container**: Docker, with `docker-compose.yml` for orchestration
- **Hot reload in dev**: `watchfiles` to restart on change

### Naming conventions

- PyPI package / repo: `throughline`
- CLI command: `throughline` (e.g., `throughline init`)
- Server name in the MCP handshake: `throughline`
- docker-compose container and service: `throughline`
- Resource URI scheme: `throughline://`
- Attribution HTTP header: `X-Throughline-Actor: human|agent`
- Env vars: `THROUGHLINE_` prefix (e.g., `THROUGHLINE_DB_PATH`,
  `THROUGHLINE_PORT`)

### Target-project directory layout

```
project/
├── .claude/
│   └── CLAUDE.md              ← contains one line: @./.docs/active-context.md
├── .docs/                     ← throughline's territory (reactive writes)
│   ├── state.md               ← current snapshot, regenerated on every mutation
│   ├── active-context.md      ← active context for the harness (regenerated)
│   ├── packages/
│   │   ├── 001-build-throughline-v1.md
│   │   └── 002-...md
│   ├── decisions/
│   │   └── 0001-decision-id.md
│   └── execution-log.md       ← append-only
├── .throughline/              ← opaque; in .gitignore
│   └── state.db               ← SQLite
├── docker-compose.yml
└── ... project code
```

`.docs/` is versionable (you decide if you commit). `.throughline/` never is.

### SQLite schema

Five tables. Markdown in `.docs/` is generated from the DB; the DB is the source
of truth.

```sql
-- Work packages
CREATE TABLE packages (
    id TEXT PRIMARY KEY,                       -- '001', '002', etc
    title TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN
        ('draft', 'ready', 'in-progress', 'done', 'abandoned')),
    goal TEXT,
    acceptance_criteria TEXT,
    out_of_scope TEXT,
    decisions_made TEXT,                       -- free text, not relational
    verification TEXT,
    paths_glob TEXT,                           -- json array of globs
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    closed_at TIMESTAMP
);

-- Decisions (lite ADRs)
CREATE TABLE decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN
        ('proposed', 'ratified', 'superseded')),
    context TEXT NOT NULL,                     -- why this decision exists
    decision TEXT NOT NULL,                    -- what was decided
    alternatives TEXT,                         -- alternatives considered
    consequences TEXT,                         -- anticipated impact
    superseded_by INTEGER,                     -- FK to another decision
    created_at TIMESTAMP NOT NULL,
    ratified_at TIMESTAMP,
    FOREIGN KEY (superseded_by) REFERENCES decisions(id)
);

-- Discoveries (blockers, insights, hypotheses)
CREATE TABLE discoveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK(kind IN
        ('blocker', 'insight', 'hypothesis', 'risk')),
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN
        ('open', 'resolved', 'absorbed')),     -- absorbed = became package/decision
    resolution TEXT,
    package_id TEXT,                           -- where it was discovered
    absorbed_into_id INTEGER,                  -- package or decision that absorbed it
    absorbed_into_kind TEXT,                   -- 'package' | 'decision'
    created_at TIMESTAMP NOT NULL,
    resolved_at TIMESTAMP,
    FOREIGN KEY (package_id) REFERENCES packages(id)
);

-- Execution log (append-only)
CREATE TABLE execution_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    package_id TEXT NOT NULL,
    actor TEXT NOT NULL CHECK(actor IN ('human', 'agent')),
    entry TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    FOREIGN KEY (package_id) REFERENCES packages(id)
);

-- Free-form state (focus, notes, anything not yet typed)
CREATE TABLE state_sections (
    name TEXT PRIMARY KEY,                     -- 'current_focus', 'notes', etc
    content TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

### Actor attribution via HTTP header

The client passes the `X-Throughline-Actor: human|agent` header on the handshake.
The server inspects it and exposes the corresponding tool set. A missing or
invalid header rejects the connection with HTTP 400 and an explicit message
naming the expected header and valid values.

### Tool surface, by actor

**Resources (read-only, both actors):**
- `throughline://state` — rendered markdown of `state.md`
- `throughline://active-context` — markdown of `active-context.md`
- `throughline://packages` — list of packages (id, title, status)
- `throughline://package/{id}` — full package
- `throughline://decisions` — list of decisions (id, title, status)
- `throughline://decision/{id}` — full decision
- `throughline://discoveries?status=open` — filtered discoveries

**actor=human tools (9 tools):**

```python
create_package(id, title, goal, paths_glob=None) -> draft
update_package(id, **fields)                     -> draft only
commit_package(id)                               -> draft → ready
                                                    validates acceptance_criteria
                                                    non-empty and > 30 chars
abandon_package(id, reason)                      -> any → abandoned

propose_decision(title, context, decision,
                 alternatives, consequences)     -> proposed
ratify_decision(id)                              -> proposed → ratified
supersede_decision(old_id, new_id)               -> old → superseded

absorb_discovery(discovery_id, into_kind,
                 into_id)                        -> discovery → absorbed

patch_state(section, content)                   -- any section
```

**actor=agent tools (6 tools):**

```python
set_package_status(id, new_status)               -- only valid transitions in
                                                    ready→in-progress→
                                                    done|abandoned
update_package_field(id, field, value)           -- decisions_made and
                                                    verification only

record_discovery(kind, title, body, package_id)  -> open
resolve_discovery(id, resolution)                -> resolved

append_log(package_id, entry)                   -- automatically actor=agent

patch_state(section, content)                   -- only restricted sections
                                                    (server-side allowlist)
```

**Sections agent is allowed to patch:**
`active_packages_summary`, `recent_discoveries`, `latest_activity`. Everything
else is human-only.

### Reactivity

Every mutation triggers asynchronous regeneration of two files in `.docs/`:

- `state.md`: full render of sections + summary tables
- `active-context.md`: subset focused on what the Code harness needs to see —
  single active package (if any), related open discoveries, recent ratified
  decisions (last 5)

Regeneration is debounced (500ms) so back-to-back mutations don't trigger N
writes. Implementation: thread workers + `asyncio.Queue`.

### Bridge to the Claude Code harness

When the user installs throughline in a new project, they run a bootstrap
command (`throughline init`) that:

1. Creates `.docs/`, `.throughline/`, `docker-compose.yml`
2. Adds the following line to `.claude/CLAUDE.md` (creating the file if
   it doesn't exist):
   ```markdown
   @./.docs/active-context.md
   ```
3. Adds `.throughline/` to `.gitignore`

Bootstrap is idempotent — running it again duplicates nothing.

## Acceptance criteria

For the package to be `done`, all of the below must be true and demonstrable:

1. **Container starts and stays up**: `docker compose up -d` in the throughline
   sample directory finishes with the healthcheck returning 200 at
   `localhost:8765/health`.

2. **Per-actor handshake works**: a client connecting with
   `X-Throughline-Actor: human` sees 9 tools listed; with
   `X-Throughline-Actor: agent`, 6 tools; without the header, HTTP 400.

3. **End-to-end package cycle**: using `curl` + a simple test MCP client, run:
   - `create_package(id="999", title="test", goal="...")` as human
   - try `commit_package("999")` without acceptance_criteria → fails
   - `update_package("999", acceptance_criteria="...")` → succeeds
   - `commit_package("999")` → succeeds, status now `ready`
   - as agent, `set_package_status("999", "in-progress")` → succeeds
   - `append_log("999", "...")` → succeeds, log persisted
   - `set_package_status("999", "done")` → succeeds

4. **Observable reactivity**: during the cycle above, `.docs/state.md` and
   `.docs/active-context.md` were regenerated at least 3 times, timestamps
   confirm, and the content reflects package 999.

5. **Bootstrap works on a new project**: running `throughline init` in an
   empty directory produces the correct structure, is idempotent, and the
   `@./.docs/active-context.md` line appears in `.claude/CLAUDE.md`.

6. **Decision and discovery**: a parallel scenario — `propose_decision` →
   `ratify_decision`; `record_discovery` (as agent) → `absorb_discovery`
   (as human) pointing to the created decision. Both reflect in `state.md`.

7. **Basic resilience**: stop the container with `docker compose down`, bring
   it back up, state persists. SQLite WAL doesn't corrupt.

8. **Automated tests**: pytest covering at least scenarios 3, 6, and 7. Full
   coverage of every tool is not required — that's v1.1 work.

## Out of scope (explicitly)

The items below are NOT part of this package; they were considered, and the
decision was to defer:

- **Temporal decision revisitation**: tagging decisions with a TTL and
  injecting reminders. Defer to v2; without usage data, there's no basis to
  pick the right window.
- **Multi-project**: one server hosting many repos. v1 is single-project,
  configured by Docker volume.
- **Auth/permissions beyond actor**: no users, no tokens. localhost-only,
  implicit trust.
- **UI / dashboard**: no frontend. Inspect via `.docs/` or `sqlite3 cli`.
- **Full-text search of decisions/log**: read-only by id and lists filtered by
  status. Text search: v2.
- **Git integration**: no references to commits, branches, PRs. Deliberate —
  keep the surfaces independent.
- **Importing legacy packages (manual markdown)**: v1 starts from zero.
  Migrations: v2.
- **Cowork or mobile support**: a platform limitation, not a design one.
- **Custom pre/post-mutation hooks**: extensibility belongs to v2.
- **Observability**: simple logs to container stdout. No metrics, no traces,
  no alerting.

## Decisions made (revocable if you disagree)

- **HTTP instead of stdio**: required by the Desktop-on-Windows + Code-on-WSL
  combination.
- **SQLite + rendered markdown rather than pure markdown**: the typed schema
  and queries are worth the cost.
- **Decisions and discoveries as first-class entities**: justifies the
  "hippocampus" framing of the design.
- **Free-form state via `state_sections`**: an escape valve for things that
  haven't become typed entities yet. If a free section becomes recurring, it
  earns a table in v2.
- **`absorb_discovery` instead of "convert"**: absorption phrasing preserves
  the discovery's history while pointing to where it was resolved.
- **Markdown generated from the DB, not the other way around**: simplifies
  invariants; humans can edit `.docs/`, but changes are overwritten on the
  next trigger. If that hurts in practice, v2 inverts (DB syncs from
  markdown).
- **Opaque directory `.throughline/` instead of `.mcp-state/`**: matches the
  naming convention and makes it clear who owns that state.

## Verification

Run the acceptance suite manually, in order:

```bash
# 1. Build and startup
cd <throughline-repo>
docker compose up -d --build
curl -fsS http://localhost:8765/health    # expect 200

# 2. Handshake smoke
curl -fsS -H "X-Throughline-Actor: human" \
  http://localhost:8765/mcp/tools/list | jq '.tools | length'    # 9
curl -fsS -H "X-Throughline-Actor: agent" \
  http://localhost:8765/mcp/tools/list | jq '.tools | length'    # 6

# 3. End-to-end cycle via the test script
pytest tests/integration/test_full_cycle.py -v

# 4. Bootstrap on a new project
mkdir /tmp/test-project && cd /tmp/test-project
throughline init
test -f .docs/state.md && \
test -f .claude/CLAUDE.md && \
grep -q '@./.docs/active-context.md' .claude/CLAUDE.md && \
echo "OK"
```

All green, the package can be closed.

## Implementation notes

- The throughline repository lives separately from the target project.
  Suggestion: `throughline` repo at `~/dev/throughline/`.
- After v1 is done, the throughline repo gets its own `.docs/` instance and
  subsequent packages (002+) are created via throughline running on itself.
  That's the most honest canary test possible.
- Effort estimate: 4–5 focused Code sessions at `--effort high`, or
  ~1500–2000 lines of Python total counting tests. May vary widely; not a
  commitment.
- If the tool counts (9 human, 6 agent) diverge from what was actually
  exposed during implementation, update acceptance criterion #2 before
  closing the package — don't close with stale criteria.
