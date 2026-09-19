"""Test the thin web_app seam (dispatch_plan_request) that forwards /api/plans*
requests to the plan_mode package. Uses a fake-backed service so it is fast and
disk-free; importing web_app is intentional (it must stay importable with the
new wiring).
"""

from __future__ import annotations

import pytest

from plan_mode.application.service import PlanModeService
from plan_mode.domain.tool_gate import ToolGate

from tests.plan_mode.fakes import FakeAgentLoop, FakePlanRepository, FakeWorkspace


@pytest.fixture
def web(monkeypatch):
    import coderai.server.web_app as web_app

    svc = PlanModeService(
        repository=FakePlanRepository(),
        workspace=FakeWorkspace("/ws"),
        agent_loop=FakeAgentLoop(),
        gate=ToolGate(),
    )
    monkeypatch.setattr(web_app, "_get_plan_service", lambda: svc)
    return web_app


def test_seam_lists_plans(web):
    status, payload = web.dispatch_plan_request("GET", "/api/plans", {})
    assert status == 200
    assert payload == {"plans": []}


def test_seam_starts_plan(web):
    status, payload = web.dispatch_plan_request("POST", "/api/plans", {"goal": "fix"})
    assert status == 200
    assert payload["state"] == "exploring"
    assert payload["goal"] == "fix"


def test_seam_action_routes(web):
    start = web.dispatch_plan_request("POST", "/api/plans", {"goal": "fix"})[1]
    pid = start["plan_id"]
    status, payload = web.dispatch_plan_request(
        "POST", f"/api/plans/{pid}/explore", {"tool": "read_file", "arguments": {}}
    )
    assert status == 200 and payload["state"] == "drafting"
    status, payload = web.dispatch_plan_request(
        "POST", f"/api/plans/{pid}/cancel", {}
    )
    assert status == 200 and payload["state"] == "cancelled"


def test_seam_missing_plan_is_404(web):
    status, payload = web.dispatch_plan_request("GET", "/api/plans/nope", {})
    assert status == 404
    assert "error" in payload
