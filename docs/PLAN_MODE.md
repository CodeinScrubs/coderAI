# Plan Mode

A read-only-then-approve planning loop for CoderAI. The agent **explores** the
codebase without making changes, **drafts** a concrete set of steps, holds them
for a human to **approve** (or reject/edit), and only then **executes** them.

This is the "task-level" gate that complements the existing "tool-level"
approval policies: multi-file work is reviewed *as a plan* before a single
mutating tool runs.

## Architecture

Clean architecture / ports-and-adapters. The dependency rule points inward:
adapters implement the application's ports; the domain knows nothing about the
others.

```
plan_mode/
  domain/       pure — no I/O
    states.py       PlanState, TRANSITIONS, can_transition, InvalidTransitionError
    entities.py     Plan, PlanStep (value objects + the mutable state machine)
    tool_gate.py    ToolGate — fail-closed read-only/mutating classification
  application/  use cases
    service.py      PlanModeService — start/explore/draft/approve/reject/edit/execute/cancel
    ports.py        PlanRepository, WorkspacePort, AgentLoopPort, ToolOutcome
    errors.py       PlanNotFoundError, PlanStateError, PlanInputError
  adapters/     concrete ports (the composition root)
    repositories.py MemoryPlanRepository, JsonPlanRepository (path-traversal safe)
    agents.py       ToolsAgentLoop — runs steps through the real `tools` registry
    workspace.py    PathWorkspace — resolves the active workspace
    factories.py    build_default_service(), default_plans_dir()
  http_api/
    handlers.py     dispatch(method, path, body, service) -> (status, payload)
```

The web app is a **thin adapter**: `web_app.dispatch_plan_request` forwards
`/api/plans*` requests to `plan_mode.http_api.dispatch` and sends the returned
JSON. No Plan Mode logic lives in `web_app`.

## State machine

```
IDLE → EXPLORING → DRAFTING → AWAITING_APPROVAL → EXECUTING → DONE
         │              │               │                 │
         └──────────────┴───────────────┴──── CANCELLED ──┘
                                              AWAITING_APPROVAL → REJECTED
                                              AWAITING_APPROVAL → DRAFTING  (edit)
```

| state               | read-only tools | mutating tools |
|---------------------|:---------------:|:--------------:|
| IDLE                | blocked         | blocked        |
| EXPLORING / DRAFTING / AWAITING_APPROVAL | allowed | **blocked** |
| EXECUTING           | allowed         | allowed (only the plan's own steps) |
| DONE / REJECTED / CANCELLED | blocked | blocked |

**Fail-closed:** a tool name not explicitly listed as read-only is treated as
mutating, so anything newly added is blocked outside `EXECUTING` by default.
During `EXECUTING` the gate permits tools; the *executor* enforces that only the
approved steps actually run, in order, stopping on the first failure.

## HTTP surface

| Method | Path                       | Body                                   | Notes |
|--------|----------------------------|----------------------------------------|-------|
| GET    | `/api/plans`               | —                                      | `{"plans": [...]}` |
| POST   | `/api/plans`               | `{"goal", "workspace"?}`               | → EXPLORING |
| GET    | `/api/plans/{id}`          | —                                      | `{"plan": {...}}`, 404 if absent |
| POST   | `/api/plans/{id}/explore`  | `{"tool", "arguments"}`                | read-only only; records an observation; → DRAFTING |
| POST   | `/api/plans/{id}/draft`    | `{"steps": [{title, tool, arguments}]}`| → AWAITING_APPROVAL |
| POST   | `/api/plans/{id}/approve`  | —                                      | → EXECUTING |
| POST   | `/api/plans/{id}/reject`   | `{"reason"?}`                          | → REJECTED |
| POST   | `/api/plans/{id}/edit`     | —                                      | → DRAFTING |
| POST   | `/api/plans/{id}/execute`  | —                                      | runs steps → DONE (or CANCELLED on failure) |
| POST   | `/api/plans/{id}/cancel`   | —                                      | → CANCELLED |

Status codes: `200` success, `400` invalid input, `404` unknown plan/path,
`405` wrong method, `409` illegal state transition.

## Persistence

Plans are stored as one JSON file each under `coderai_data/plans`. Plan ids are
validated (hex, no path separators) before use as file names.

## Testing

`tests/plan_mode/` — domain, application (against in-memory fakes), adapters,
HTTP handlers, and the `web_app` seam. Coverage target is enforced:

```bash
python -m pytest tests/plan_mode/ --cov=plan_mode --cov-fail-under=95
```
