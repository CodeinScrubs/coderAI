# Changelog

All notable changes to CoderAI are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
