# Changelog

All notable changes to CoderAI are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **`run_command` is now approval-gated and sandboxed, like `run_bash`.** It is
  the "verify my changes" shell tool, but it is the same capability class as
  `run_bash` — a host shell execution tool. It previously ran
  `subprocess.run(command, shell=True)` directly on the host with **no**
  approval (its gate was a no-op because `run_command` was absent from the
  approval policy, so it fell through to the ungated return) and **no**
  sandbox, leaving an unprompted RCE surface that the P0/P1 hardening of
  `run_bash` had closed. `run_command` now carries the `always` default, is
  hard-stopped against destructive commands, and executes through
  `SandboxRunner` (Docker when available, otherwise a local `sh -c` with a
  sanitized environment).
- **The SSRF policy now covers every outbound tool, not just `fetch_url`.**
  `test_api_endpoint` called `urllib.request.urlopen(url)` directly on a
  model-supplied URL and `navigate_web`/`take_screenshot` called Playwright
  `page.goto(url)` — none applied the SSRF guard, so the model could reach the
  cloud metadata endpoint (`169.254.169.254`), loopback, or private hosts (and
  `file://` for the browser tools) even though `fetch_url` blocked the same
  target. All three now route through the shared SSRF policy.
- **`fetch_url` pins the socket to the validated IP (closes DNS rebinding) and
  re-validates every redirect hop.** The guard used to resolve the hostname and
  then let `urllib` re-resolve independently at connect time — a rebinding flip
  between check and connect could still steer the socket to a private address.
  The connection is now made directly to the validated public IP (original
  hostname kept for `Host`/TLS), and each 30x target is re-checked against the
  policy before it is followed.

### Added

- **A network access layer: an access token + loopback guard.** The server's only
  protection was the default `127.0.0.1` bind. Now there are two independent
  boundaries. A **loopback-only guard** (`WEB_APP_LOOPBACK_ONLY`, default `true`)
  refuses any non-local HTTP/WebSocket client. An **access token**
  (`CODERAI_AUTH_TOKEN`) gates non-loopback clients: they must present it
  (`Authorization: Bearer <token>` for HTTP, `?token=<token>` for WebSockets) or
  be refused; loopback clients never need it, so the local single-machine flow is
  unchanged. With no token configured, one is generated at boot and printed once,
  and the UI surfaces it under **Settings → Remote access** (and accepts a
  `?token=` in the page URL). The interactive terminal WebSocket keeps its own
  tighter loopback-only guard on top of this.

### Fixed

- **The default (FastAPI) server now exposes `/api/plans*`.** Plan Mode (the
  1.3.0 feature) was only wired into the stdlib `web_app`; `fastapi_app` — the
  server that actually starts — had no `/api/plans` routes, so the feature was
  unreachable on the default server. It is now served with the same
  list/get/start/action/404 behavior as the stdlib adapter.
- **`terminal_manager.py` now imports the `Any` it annotates with.** Three type
  hints referenced `Any` without importing it — it only failed to raise because
  of `from __future__ import annotations`, but the name was still undefined at
  runtime.

### Improved

- **Test collection and app boot are ~15× faster.** `web_app` imported `litellm`
  at module load, which pulls in the openai/azure/anthropic SDKs and a tiktoken
  model download (~100s). That ran on every `pytest` collection and every boot.
  The import is now deferred to a background daemon thread started at boot; until
  it finishes, token counting uses the fast char-based estimator (the exact
  counter is picked up automatically once warm). Collection dropped from ~115s to
  ~4s, and the server now comes up instantly instead of blocking on the SDK load.

## [1.4.1] - 2026-09-16

### Fixed

- **`fetch_url` is now SSRF-safe.** The guard only checked the scheme and whether
  the hostname *string* looked local, so a DNS name that resolves to a
  private/metadata address (`localtest.me` → `127.0.0.1`) passed and a `302` to
  the cloud metadata service (`169.254.169.254`) was never re-checked. Every
  resolved address is now validated (public-only), and a redirect handler
  re-validates each hop so a public page cannot bounce the client into the
  internal network.
- **Terminal sessions are contained to the workspace.** A session could be
  anchored at any path (`C:\Windows`, the user profile) and then run commands
  there — a user-RCE surface anywhere on disk. The requested cwd is now
  resolved; if it escapes the active workspace the session is re-anchored to the
  workspace root, and `set_cwd` refuses to move outside it.
- **`run_bash` requires approval on every command.** It defaulted to
  `dangerous_only`, which ran any non-matching command unprompted — and without
  Docker the sandbox falls back to a local shell, so the narrow destructive
  blocklist was the only guard. The default is now `always`; the destructive
  block is kept as defense-in-depth, and an explicit `auto` override is
  available for users who accept the risk.
- **Skills load again after the `coderai` package move.** The refactor moved
  `skills_manager.py` from the repo root into `coderai/skills/`, but its
  `SKILLS_DIR` still resolved `Path(__file__).parent / "skills"` to the
  nonexistent `coderai/skills/skills` — so the app silently loaded **zero**
  skills and slash commands never resolved. `ROOT` now climbs back to the repo
  root (`parent.parent.parent`), matching `web_app.py`; the frozen `_MEIPASS`
  path is unchanged.
- **Fully restored the test suite after the `coderai` package move.** The
  import repair fixed *collection* (34 errors) but ten tests still failed at
  *runtime* on references the repair missed: `patch`/`monkeypatch.setattr`
  targets that used the old top-level module names (`hindsight_manager`,
  `codebase_index`, `vector_store`) now use the `coderai.*` paths, and the
  embedding-model tests were still asserting the removed `embeddinggemma`
  model instead of `nomic-embed-text`.

## [1.4.0] - 2026-09-16

### Changed

- **Per-request approval tokens.** Approval state is now a token-keyed,
  thread-safe store instead of a single global slot keyed by tool name. Each
  pending action carries a stable token (a hash of the tool + arguments) that
  round-trips through the API and browser; approving one action no longer
  silently authorizes a different one, and "always allow" is scoped to a single
  tool for the session instead of being one global flag. Git push keeps its
  separate explicit-confirmation flow.

### Fixed

- **Advanced shell tools are now gated and no longer shell-injectable.**
  `run_linter`, `run_tests`, `run_kubectl`, `run_terraform`, `run_npm_script`,
  `run_docker_container`, and `get_container_logs` previously ran
  model-controlled strings via `shell=True` with no approval. They now require
  approval, the fixed binaries run as argv lists (no shell), and linter/tests
  run through the sandboxed runner.
- **SQL tools are local-only.** `execute_sql_query` and `get_database_schema`
  only reach a workspace-local SQLite file; remote connection strings and
  paths outside the workspace are rejected. Read-only statements run
  unprompted; write statements require approval.
- **`delete_file` and `append_file` now require approval**, matching
  `write_file` and `replace_in_file`.
- **`query_code_graph` is no longer dead.** Its advertised patterns
  (`calls`, `callers`, `imports`, `dependencies`, `extended_by`) are translated
  to the code-review-graph engine's real pattern names, and engine errors are
  surfaced instead of being reported as success.
- **Offline hindsight fallback actually works.** It previously imported a
  nonexistent `get_memory_manager` and called nonexistent methods (the error was
  swallowed), so `remember_fact` reported success for facts that were never
  stored. Added a real `get_memory_manager(workspace)` factory and
  `MemoryManager.get_summary()`; the fallback now uses
  `index_fact` / `retrieve_relevant` / `get_summary`, and `remember_fact`
  reports genuine failures honestly.

## [1.3.0] - 2026-09-16

### Added

- **Plan Mode** — a modular, cleanly-architected service for
  *explore → draft → approve → execute*. The agent explores the codebase
  read-only, proposes concrete steps, holds them for human approval, and only
  then executes them.
  - Clean-architecture layering: `plan_mode/domain` (pure state machine,
    entities, fail-closed tool gate), `plan_mode/application` (use-case service +
    ports), `plan_mode/adapters` (JSON/in-memory repository, tools agent loop,
    path workspace, factory), and `plan_mode/http_api` (HTTP-agnostic handlers).
  - Lifecycle: `IDLE → EXPLORING → DRAFTING → AWAITING_APPROVAL → EXECUTING →
    DONE`, with `REJECTED` / `CANCELLED` terminal states and an "edit plan"
    path back to `DRAFTING`.
  - **Fail-closed tool gate**: a tool is only allowed in read-only states if it
    is explicitly classified read-only; unknown tools are treated as mutating and
    blocked. Mutating tools run only during `EXECUTING`.
  - HTTP surface (JSON only, UI deferred):
    - `GET  /api/plans` — list plans
    - `POST /api/plans` — start a plan
    - `GET  /api/plans/{id}` — fetch a plan
    - `POST /api/plans/{id}/explore` — run a read-only tool
    - `POST /api/plans/{id}/draft` — submit steps
    - `POST /api/plans/{id}/approve` — move to `EXECUTING`
    - `POST /api/plans/{id}/reject` — reject with a reason
    - `POST /api/plans/{id}/edit` — reopen for editing
    - `POST /api/plans/{id}/execute` — run the approved steps
    - `POST /api/plans/{id}/cancel` — cancel
  - Plans persist to `coderai_data/plans` (one JSON file per plan), surviving a
    restart.
- **Test suite** for Plan Mode: 199 tests, ~99% line coverage on `plan_mode/`
  (enforced with `--cov-fail-under=95`).

### Notes

- Plan Mode is wired only into the stdlib server (`web_app.py`) for now. FastAPI
  route parity and the UI are intentionally out of scope for this release.
