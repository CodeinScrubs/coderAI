"""HTTP-agnostic request handlers for Plan Mode.

The single entry point is :func:`dispatch`, a pure function with the signature::

    dispatch(method, path, body, service) -> (status_code, payload)

It depends only on the :class:`~plan_mode.application.service.PlanModeService`
(never on :mod:`web_app`), which keeps it unit-testable without a live server.
The web app's HTTP layer (``do_GET``/``do_POST``) is a thin adapter that calls
this and sends the returned payload as JSON.

Routing model
-------------
The surface is a flat set of method-specific routes (no REST verb overloading) so
it maps cleanly onto the app's existing ``if path == "/api/..."`` style:

    GET    /api/plans                     list plans
    POST   /api/plans                     start a plan {"goal", "workspace"?}
    GET    /api/plans/{id}                fetch one plan
    POST   /api/plans/{id}/explore        {"tool", "arguments"}
    POST   /api/plans/{id}/draft          {"steps": [ {title, tool, arguments} ]}
    POST   /api/plans/{id}/approve        {}
    POST   /api/plans/{id}/reject         {"reason"?}
    POST   /api/plans/{id}/edit           {}
    POST   /api/plans/{id}/execute        {}
    POST   /api/plans/{id}/cancel         {}
"""

from __future__ import annotations

import uuid
from typing import Optional, Tuple

from plan_mode.application.errors import (
    PlanInputError,
    PlanNotFoundError,
    PlanStateError,
)
from plan_mode.application.service import PlanModeService
from plan_mode.domain.entities import PlanStep

# An "action" route is ``/api/plans/{id}/{action}`` with one of these verbs.
_Actions = ("explore", "draft", "approve", "reject", "edit", "execute", "cancel")


def _bad_request(message: str) -> Tuple[int, dict]:
    return 400, {"error": message}


def _not_found() -> Tuple[int, dict]:
    return 404, {"error": "not found"}


def _method_not_allowed() -> Tuple[int, dict]:
    return 405, {"error": "method not allowed"}


def _parse_steps(raw: object) -> list[PlanStep]:
    """Turn a client-supplied ``steps`` array into :class:`PlanStep` objects.

    Clients supply ``title`` and ``tool`` (and optional ``arguments``/``detail``);
    the handler generates the ``step_id``. A step without a ``tool`` is invalid.

    Args:
        raw: the decoded JSON value of the ``steps`` body field.

    Returns:
        A list of :class:`PlanStep`.

    Raises:
        PlanInputError: if ``steps`` is not a list, or a step is malformed.
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise PlanInputError("'steps' must be a list")
    steps: list[PlanStep] = []
    for item in raw:
        if not isinstance(item, dict):
            raise PlanInputError("each step must be an object")
        tool = item.get("tool")
        if not tool:
            raise PlanInputError("each step requires a 'tool'")
        # step_id is a server-side concern; a placeholder is used here and a
        # fresh id is assigned when the draft is recorded.
        steps.append(
            PlanStep(
                step_id="",
                title=str(item.get("title") or tool),
                tool=str(tool),
                arguments=item.get("arguments") or {},
                detail=str(item.get("detail") or ""),
            )
        )
    return steps


def dispatch(
    method: str,
    path: str,
    body: Optional[dict],
    service: PlanModeService,
) -> Tuple[int, dict]:
    """Route a Plan Mode HTTP request to the service.

    Args:
        method: the HTTP method, e.g. ``"GET"`` or ``"POST"`` (case-insensitive).
        path: the request path, e.g. ``"/api/plans/abc/explore"``.
        body: the decoded JSON body (a dict), or ``None``.
        service: the wired :class:`PlanModeService`.

    Returns:
        A ``(status_code, payload)`` tuple. ``payload`` is always JSON-serializable.

    Examples:
        >>> from plan_mode.http_api.handlers import dispatch  # doctest: +SKIP
    """
    verb = (method or "").upper()
    body = body or {}
    parts = [p for p in (path or "").split("/") if p]

    # /api/plans
    if parts[-2:] == ["api", "plans"]:
        if verb == "GET":
            return 200, {"plans": service.list_plans()}
        if verb == "POST":
            try:
                return 200, service.start_plan(
                    goal=str(body.get("goal") or ""),
                    workspace=str(body.get("workspace") or ""),
                )
            except PlanInputError as exc:
                return _bad_request(str(exc))
        return _method_not_allowed()

    # /api/plans/{id}[/action]
    if len(parts) >= 3 and parts[0] == "api" and parts[1] == "plans":
        plan_id = parts[2]
        action = parts[3] if len(parts) > 3 else None

        if action is None:
            if verb != "GET":
                return _method_not_allowed()
            plan = service.get_plan(plan_id)
            if plan is None:
                return _not_found()
            return 200, {"plan": plan}

        if action not in _Actions or verb != "POST":
            return _not_found() if action not in _Actions else _method_not_allowed()

        return _run_action(action, plan_id, body, service)

    return _not_found()


def _run_action(
    action: str,
    plan_id: str,
    body: dict,
    service: PlanModeService,
) -> Tuple[int, dict]:
    """Run a single ``/api/plans/{id}/{action}`` request against the service.

    Args:
        action: the action verb.
        plan_id: the target plan id.
        body: the decoded request body.
        service: the service.

    Returns:
        A ``(status, payload)`` tuple.
    """
    try:
        if action == "explore":
            tool = body.get("tool")
            if not tool:
                return _bad_request("explore requires a 'tool'")
            payload = service.explore(
                plan_id, str(tool), body.get("arguments") or {}
            )
            return 200, payload

        if action == "draft":
            raw_steps = _parse_steps(body.get("steps"))
            # Assign server-side step ids (the client does not supply them).
            steps = [
                PlanStep(
                    step_id=uuid.uuid4().hex,
                    title=s.title,
                    tool=s.tool,
                    arguments=s.arguments,
                    detail=s.detail,
                )
                for s in raw_steps
            ]
            return 200, service.draft_plan(plan_id, steps)

        if action == "approve":
            return 200, service.approve(plan_id)

        if action == "reject":
            return 200, service.reject(plan_id, str(body.get("reason") or ""))

        if action == "edit":
            return 200, service.edit_plan(plan_id)

        if action == "execute":
            return 200, service.execute(plan_id)

        if action == "cancel":
            return 200, service.cancel(plan_id)

        # Unreachable: _run_action is only invoked for a validated action verb
        # (see the guard in dispatch). Kept as an explicit, typed return so the
        # function has no implicit fall-through.
        return _not_found()

    except PlanNotFoundError:
        return _not_found()
    except PlanStateError as exc:
        return 409, {"error": str(exc)}
    except PlanInputError as exc:
        return _bad_request(str(exc))
