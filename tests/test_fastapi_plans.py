"""tests/test_fastapi_plans.py - the default FastAPI server exposes /api/plans*.

Plan Mode routes were only wired into the stdlib web_app; fastapi_app (the
default live server) had no /api/plans route at all, so the 1.3.0 feature was
unreachable on the server users actually run. These tests assert parity with
the web_app seam: list / get / start / action / 404, using a fake-backed
service so they are fast and disk-free.
"""

from __future__ import annotations

import pytest

from plan_mode.application.service import PlanModeService
from plan_mode.domain.tool_gate import ToolGate

from tests.plan_mode.fakes import FakeAgentLoop, FakePlanRepository, FakeWorkspace


@pytest.fixture
def client(monkeypatch):
    import coderai.server.web_app as web_app

    svc = PlanModeService(
        repository=FakePlanRepository(),
        workspace=FakeWorkspace("/ws"),
        agent_loop=FakeAgentLoop(),
        gate=ToolGate(),
    )
    monkeypatch.setattr(web_app, "_get_plan_service", lambda: svc)

    from fastapi.testclient import TestClient
    from coderai.server.fastapi_app import create_app

    return TestClient(create_app())


def test_plans_list_empty(client):
    r = client.get("/api/plans")
    assert r.status_code == 200
    assert r.json() == {"plans": []}


def test_plans_start_and_get(client):
    r = client.post("/api/plans", json={"goal": "fix the build"})
    assert r.status_code == 200
    data = r.json()
    assert data["state"] == "exploring"
    assert data["goal"] == "fix the build"
    pid = data["plan_id"]

    g = client.get(f"/api/plans/{pid}")
    assert g.status_code == 200
    assert g.json()["plan"]["goal"] == "fix the build"


def test_plans_action_routes(client):
    start = client.post("/api/plans", json={"goal": "fix"}).json()
    pid = start["plan_id"]

    r = client.post(f"/api/plans/{pid}/explore",
                    json={"tool": "read_file", "arguments": {}})
    assert r.status_code == 200
    assert r.json()["state"] == "drafting"

    r = client.post(f"/api/plans/{pid}/cancel", json={})
    assert r.status_code == 200
    assert r.json()["state"] == "cancelled"


def test_plans_missing_is_404(client):
    r = client.get("/api/plans/nope")
    assert r.status_code == 404
    assert "error" in r.json()


def test_plans_unknown_action_is_404(client):
    start = client.post("/api/plans", json={"goal": "fix"}).json()
    pid = start["plan_id"]
    r = client.post(f"/api/plans/{pid}/nope", json={})
    assert r.status_code == 404
