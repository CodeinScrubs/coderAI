"""Tests for the Plan Mode HTTP-agnostic request handlers.

These exercise ``plan_mode.http_api.handlers.dispatch`` — a pure function that
maps (method, path, body) onto the PlanModeService and returns an HTTP status
plus a JSON-safe payload. No live server or web_app import is required.
"""

from __future__ import annotations

import pytest

from plan_mode.http_api.handlers import dispatch
from plan_mode.application.errors import PlanStateError

from tests.plan_mode.fakes import FakeAgentLoop, FakePlanRepository, FakeWorkspace
from plan_mode.application.service import PlanModeService
from plan_mode.domain.tool_gate import ToolGate


def service() -> PlanModeService:
    return PlanModeService(
        repository=FakePlanRepository(),
        workspace=FakeWorkspace("/ws"),
        agent_loop=FakeAgentLoop(),
        gate=ToolGate(),
    )


class TestDispatchRouting:
    def test_start_plan(self):
        svc = service()
        status, payload = dispatch("POST", "/api/plans", {"goal": "fix login"}, svc)
        assert status == 200
        assert payload["state"] == "exploring"
        assert payload["goal"] == "fix login"

    def test_start_requires_goal(self):
        status, payload = dispatch("POST", "/api/plans", {}, service())
        assert status == 400
        assert "goal" in payload["error"]

    def test_list_plans(self):
        svc = service()
        dispatch("POST", "/api/plans", {"goal": "a"}, svc)
        status, payload = dispatch("GET", "/api/plans", {}, svc)
        assert status == 200
        assert isinstance(payload["plans"], list)
        assert len(payload["plans"]) == 1

    def test_get_plan(self):
        svc = service()
        start = dispatch("POST", "/api/plans", {"goal": "a"}, svc)[1]
        status, payload = dispatch("GET", f"/api/plans/{start['plan_id']}", {}, svc)
        assert status == 200
        assert payload["plan"]["plan_id"] == start["plan_id"]

    def test_get_missing_plan_is_404(self):
        status, payload = dispatch("GET", "/api/plans/doesnotexist", {}, service())
        assert status == 404

    def test_unknown_path_is_404(self):
        status, payload = dispatch("GET", "/api/plans/totally/bogus/sub", {}, service())
        assert status == 404

    def test_unknown_method_is_405(self):
        svc = service()
        pid = dispatch("POST", "/api/plans", {"goal": "a"}, svc)[1]["plan_id"]
        status, payload = dispatch("PATCH", f"/api/plans/{pid}", {}, svc)
        assert status == 405


class TestActionRoutes:
    def _start(self, svc):
        return dispatch("POST", "/api/plans", {"goal": "g"}, svc)[1]["plan_id"]

    def _explored(self, svc, pid):
        status, payload = dispatch(
            "POST", f"/api/plans/{pid}/explore",
            {"tool": "read_file", "arguments": {"path": "a.py"}}, svc)
        assert status == 200
        return payload

    def _drafted(self, svc, pid):
        self._explored(svc, pid)
        status, payload = dispatch(
            "POST", f"/api/plans/{pid}/draft",
            {"steps": [{"title": "s", "tool": "write_file", "arguments": {"path": "a.py", "content": "x"}}]},
            svc)
        assert status == 200
        return payload

    def test_explore(self):
        svc = service()
        pid = self._start(svc)
        payload = self._explored(svc, pid)
        assert payload["state"] == "drafting"
        assert any("ok:read_file" in o for o in payload["observations"])

    def test_explore_blocks_mutating(self):
        svc = service()
        pid = self._start(svc)
        status, payload = dispatch(
            "POST", f"/api/plans/{pid}/explore",
            {"tool": "write_file", "arguments": {"path": "a", "content": "x"}}, svc)
        assert status == 409

    def test_draft_moves_to_awaiting(self):
        svc = service()
        pid = self._start(svc)
        payload = self._drafted(svc, pid)
        assert payload["state"] == "awaiting_approval"
        assert payload["steps"][0]["tool"] == "write_file"

    def test_draft_builds_steps_without_id(self):
        # The client does not supply step_id; the handler must generate one.
        svc = service()
        pid = self._start(svc)
        payload = self._drafted(svc, pid)
        assert payload["steps"][0]["step_id"] != ""

    def test_approve_and_execute(self):
        svc = service()
        pid = self._start(svc)
        self._drafted(svc, pid)
        status, approved = dispatch("POST", f"/api/plans/{pid}/approve", {}, svc)
        assert status == 200 and approved["state"] == "executing"
        status, done = dispatch("POST", f"/api/plans/{pid}/execute", {}, svc)
        assert status == 200 and done["state"] == "done"

    def test_reject(self):
        svc = service()
        pid = self._start(svc)
        self._drafted(svc, pid)
        status, payload = dispatch(
            "POST", f"/api/plans/{pid}/reject", {"reason": "too risky"}, svc)
        assert status == 200
        assert payload["state"] == "rejected"
        assert payload["rejection_reason"] == "too risky"

    def test_edit(self):
        svc = service()
        pid = self._start(svc)
        self._drafted(svc, pid)
        status, payload = dispatch("POST", f"/api/plans/{pid}/edit", {}, svc)
        assert status == 200 and payload["state"] == "drafting"

    def test_cancel(self):
        svc = service()
        pid = self._start(svc)
        status, payload = dispatch("POST", f"/api/plans/{pid}/cancel", {}, svc)
        assert status == 200 and payload["state"] == "cancelled"

    def test_wrong_state_is_409(self):
        # approve without having drafted -> illegal state -> 409
        svc = service()
        pid = self._start(svc)
        status, payload = dispatch("POST", f"/api/plans/{pid}/approve", {}, svc)
        assert status == 409
        assert payload["error"]

    def test_action_on_missing_plan_is_404(self):
        status, payload = dispatch("POST", "/api/plans/nope/approve", {}, service())
        assert status == 404


class TestDispatchPassesThrough:
    def test_service_state_error_maps_to_409(self):
        svc = service()
        pid = dispatch("POST", "/api/plans", {"goal": "g"}, svc)[1]["plan_id"]
        # executing a plan that is still exploring
        status, _ = dispatch("POST", f"/api/plans/{pid}/execute", {}, svc)
        assert status == 409


class TestValidationEdges:
    def test_draft_with_missing_steps_is_empty_draft(self):
        # draft without a "steps" key -> empty step list, still awaiting approval
        svc = service()
        pid = dispatch("POST", "/api/plans", {"goal": "g"}, svc)[1]["plan_id"]
        dispatch("POST", f"/api/plans/{pid}/explore", {"tool": "read_file"}, svc)
        status, payload = dispatch("POST", f"/api/plans/{pid}/draft", {}, svc)
        assert status == 200
        assert payload["state"] == "awaiting_approval"
        assert payload["steps"] == []

    def test_draft_steps_must_be_a_list(self):
        svc = service()
        pid = dispatch("POST", "/api/plans", {"goal": "g"}, svc)[1]["plan_id"]
        dispatch("POST", f"/api/plans/{pid}/explore", {"tool": "read_file"}, svc)
        status, payload = dispatch(
            "POST", f"/api/plans/{pid}/draft", {"steps": "not-a-list"}, svc)
        assert status == 400

    def test_draft_step_must_be_object(self):
        svc = service()
        pid = dispatch("POST", "/api/plans", {"goal": "g"}, svc)[1]["plan_id"]
        dispatch("POST", f"/api/plans/{pid}/explore", {"tool": "read_file"}, svc)
        status, _ = dispatch(
            "POST", f"/api/plans/{pid}/draft", {"steps": ["not-a-dict"]}, svc)
        assert status == 400

    def test_draft_step_requires_tool(self):
        svc = service()
        pid = dispatch("POST", "/api/plans", {"goal": "g"}, svc)[1]["plan_id"]
        dispatch("POST", f"/api/plans/{pid}/explore", {"tool": "read_file"}, svc)
        status, _ = dispatch(
            "POST", f"/api/plans/{pid}/draft",
            {"steps": [{"title": "no tool"}]}, svc)
        assert status == 400

    def test_explore_requires_tool(self):
        svc = service()
        pid = dispatch("POST", "/api/plans", {"goal": "g"}, svc)[1]["plan_id"]
        status, _ = dispatch("POST", f"/api/plans/{pid}/explore", {}, svc)
        assert status == 400

    def test_unknown_action_is_404(self):
        svc = service()
        pid = dispatch("POST", "/api/plans", {"goal": "g"}, svc)[1]["plan_id"]
        status, _ = dispatch("POST", f"/api/plans/{pid}/teleport", {}, svc)
        assert status == 404

    def test_unknown_verb_on_collection_is_405(self):
        status, _ = dispatch("DELETE", "/api/plans", {}, service())
        assert status == 405

    def test_non_plan_path_is_404(self):
        status, _ = dispatch("GET", "/api/other", {}, service())
        assert status == 404
