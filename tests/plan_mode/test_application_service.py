"""Tests for the Plan Mode application service (use cases) and ports.

These define the service contract *before* the implementation exists (TDD). The
service is exercised against in-memory fakes so no disk, workspace, or real tool
set is required.
"""

from __future__ import annotations

import pytest

from plan_mode.application.errors import PlanNotFoundError, PlanStateError
from plan_mode.application.service import PlanModeService
from plan_mode.domain.entities import PlanStep
from plan_mode.domain.states import PlanState
from plan_mode.domain.tool_gate import ToolGate

from tests.plan_mode.fakes import FakeAgentLoop, FakePlanRepository, FakeWorkspace


def make_service(agent=None, workspace=None, gate=None) -> PlanModeService:
    return PlanModeService(
        repository=FakePlanRepository(),
        workspace=workspace or FakeWorkspace(),
        agent_loop=agent or FakeAgentLoop(),
        gate=gate or ToolGate(),
    )


# ---------------------------------------------------------------------------
# start_plan
# ---------------------------------------------------------------------------


class TestStartPlan:
    def test_starts_in_exploring(self):
        svc = make_service()
        plan = svc.start_plan("refactor auth", workspace="/custom")
        assert plan["state"] == PlanState.EXPLORING.value
        assert plan["goal"] == "refactor auth"
        assert plan["workspace"] == "/custom"
        assert plan["steps"] == []

    def test_uses_resolved_workspace_when_not_given(self):
        svc = make_service(workspace=FakeWorkspace("/resolved/ws"))
        plan = svc.start_plan("goal")
        assert plan["workspace"] == "/resolved/ws"

    def test_plan_is_persisted(self):
        svc = make_service()
        plan = svc.start_plan("goal")
        assert svc.get_plan(plan["plan_id"]) is not None


# ---------------------------------------------------------------------------
# explore
# ---------------------------------------------------------------------------


class TestExplore:
    def test_read_only_tool_records_observation(self):
        agent = FakeAgentLoop()
        svc = make_service(agent=agent)
        plan = svc.start_plan("goal")
        result = svc.explore(plan["plan_id"], "read_file", {"path": "a.py"})
        assert result["state"] == PlanState.DRAFTING.value
        assert any("ok:read_file" in o for o in result["observations"])
        assert agent.calls == [("read_file", {"path": "a.py"})]

    def test_mutating_tool_blocked_in_exploring(self):
        svc = make_service()
        plan = svc.start_plan("goal")
        with pytest.raises(PlanStateError):
            svc.explore(plan["plan_id"], "write_file", {"path": "a.py", "content": "x"})

    def test_unknown_tool_blocked_fail_closed(self):
        svc = make_service()
        plan = svc.start_plan("goal")
        with pytest.raises(PlanStateError):
            svc.explore(plan["plan_id"], "brand_new_tool", {})

    def test_explore_requires_exploring_or_drafting(self):
        svc = make_service()
        plan = svc.start_plan("goal")
        svc.explore(plan["plan_id"], "read_file", {})  # -> DRAFTING
        svc.draft_plan(plan["plan_id"], [PlanStep("s", "t", "read_file")])  # -> AWAITING_APPROVAL
        with pytest.raises(PlanStateError):
            svc.explore(plan["plan_id"], "read_file", {})

    def test_explore_reexplore_from_drafting_stays_drafting(self):
        svc = make_service()
        plan = svc.start_plan("goal")
        svc.explore(plan["plan_id"], "read_file", {})  # -> DRAFTING
        result = svc.explore(plan["plan_id"], "search_files", {"query": "x"})  # re-explore
        assert result["state"] == PlanState.DRAFTING.value
        assert len(result["observations"]) == 2

    def test_explore_missing_plan(self):
        svc = make_service()
        with pytest.raises(PlanNotFoundError):
            svc.explore("nope", "read_file", {})


# ---------------------------------------------------------------------------
# draft_plan
# ---------------------------------------------------------------------------


class TestDraftPlan:
    def _exploring_plan(self, svc):
        plan = svc.start_plan("goal")
        svc.explore(plan["plan_id"], "read_file", {})
        return plan

    def test_draft_moves_to_awaiting_approval(self):
        svc = make_service()
        plan = self._exploring_plan(svc)
        steps = [PlanStep("s1", "Add validator", "write_file", {"path": "a.py", "content": "x"})]
        result = svc.draft_plan(plan["plan_id"], steps)
        assert result["state"] == PlanState.AWAITING_APPROVAL.value
        assert len(result["steps"]) == 1
        assert result["steps"][0]["tool"] == "write_file"

    def test_draft_requires_drafting_or_awaiting(self):
        svc = make_service()
        plan = svc.start_plan("goal")  # EXPLORING, not yet explored/drafted
        with pytest.raises(PlanStateError):
            svc.draft_plan(plan["plan_id"], [])

    def test_redraft_from_awaiting_replaces_steps_and_stays_awaiting(self):
        # Re-submitting a draft while already awaiting approval replaces the
        # steps but keeps the plan gated at AWAITING_APPROVAL (the approval gate
        # only opens in this state). To drop back to DRAFTING one uses edit_plan.
        svc = make_service()
        plan = self._exploring_plan(svc)
        svc.draft_plan(plan["plan_id"], [PlanStep(step_id="a", title="first", tool="read_file")])
        result = svc.draft_plan(
            plan["plan_id"], [PlanStep(step_id="b", title="second", tool="write_file")]
        )
        assert result["state"] == PlanState.AWAITING_APPROVAL.value
        assert len(result["steps"]) == 1
        # the draft was replaced, not appended
        assert result["steps"][0]["title"] == "second"

    def test_draft_missing_plan(self):
        svc = make_service()
        with pytest.raises(PlanNotFoundError):
            svc.draft_plan("nope", [])


# ---------------------------------------------------------------------------
# get_plan / list
# ---------------------------------------------------------------------------


class TestGetPlan:
    def test_returns_none_when_absent(self):
        svc = make_service()
        assert svc.get_plan("missing") is None

    def test_returns_current_state(self):
        svc = make_service()
        plan = svc.start_plan("goal")
        assert svc.get_plan(plan["plan_id"])["state"] == PlanState.EXPLORING.value


# ---------------------------------------------------------------------------
# approve / reject
# ---------------------------------------------------------------------------


class TestApprove:
    def _awaiting(self, svc, n_steps=1):
        plan = svc.start_plan("goal")
        svc.explore(plan["plan_id"], "read_file", {})
        svc.draft_plan(
            plan["plan_id"],
            [PlanStep(f"s{i}", f"t{i}", "write_file", {"path": f"f{i}.py", "content": "x"}) for i in range(n_steps)],
        )
        return plan

    def test_approve_moves_to_executing(self):
        svc = make_service()
        plan = self._awaiting(svc)
        result = svc.approve(plan["plan_id"])
        assert result["state"] == PlanState.EXECUTING.value

    def test_approve_requires_awaiting(self):
        svc = make_service()
        plan = svc.start_plan("goal")
        with pytest.raises(PlanStateError):
            svc.approve(plan["plan_id"])

    def test_approve_missing(self):
        svc = make_service()
        with pytest.raises(PlanNotFoundError):
            svc.approve("nope")


class TestReject:
    def _awaiting(self, svc):
        plan = svc.start_plan("goal")
        svc.explore(plan["plan_id"], "read_file", {})
        svc.draft_plan(plan["plan_id"], [PlanStep("s", "t", "read_file")])
        return plan

    def test_reject_records_reason(self):
        svc = make_service()
        plan = self._awaiting(svc)
        result = svc.reject(plan["plan_id"], "too risky")
        assert result["state"] == PlanState.REJECTED.value
        assert result["rejection_reason"] == "too risky"

    def test_reject_requires_awaiting(self):
        svc = make_service()
        plan = svc.start_plan("goal")
        with pytest.raises(PlanStateError):
            svc.reject(plan["plan_id"], "why")

    def test_rejected_plan_cannot_be_executed(self):
        svc = make_service()
        plan = self._awaiting(svc)
        svc.reject(plan["plan_id"], "no")
        with pytest.raises(PlanStateError):
            svc.execute(plan["plan_id"])


# ---------------------------------------------------------------------------
# edit_plan (AWAITING_APPROVAL -> DRAFTING)
# ---------------------------------------------------------------------------


class TestEditPlan:
    def test_edit_returns_to_drafting(self):
        svc = make_service()
        plan = svc.start_plan("goal")
        svc.explore(plan["plan_id"], "read_file", {})
        svc.draft_plan(plan["plan_id"], [PlanStep("s", "t", "read_file")])
        result = svc.edit_plan(plan["plan_id"])
        assert result["state"] == PlanState.DRAFTING.value
        # steps are preserved for further editing
        assert len(result["steps"]) == 1

    def test_edit_requires_awaiting(self):
        svc = make_service()
        plan = svc.start_plan("goal")
        with pytest.raises(PlanStateError):
            svc.edit_plan(plan["plan_id"])


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------


class TestExecute:
    def _executing(self, svc, n_steps=2):
        plan = svc.start_plan("goal")
        svc.explore(plan["plan_id"], "read_file", {})
        svc.draft_plan(
            plan["plan_id"],
            [PlanStep(f"s{i}", f"t{i}", "write_file", {"path": f"f{i}.py", "content": "x"}) for i in range(n_steps)],
        )
        svc.approve(plan["plan_id"])
        return plan

    def test_executes_all_steps_and_finishes(self):
        svc = make_service()
        plan = self._executing(svc, n_steps=2)
        result = svc.execute(plan["plan_id"])
        assert result["state"] == PlanState.DONE.value
        assert all(s["status"] == "done" for s in result["steps"])
        # both steps were dispatched in order (after explore's own read_file call)
        assert [c[0] for c in svc.agent_loop.calls] == [
            "read_file",
            "write_file",
            "write_file",
        ]

    def test_execution_stops_on_failure(self):
        svc = make_service(agent=FakeAgentLoop(fail_tools={"write_file"}))
        plan = self._executing(svc, n_steps=2)
        result = svc.execute(plan["plan_id"])
        assert result["state"] == PlanState.CANCELLED.value
        # first step failed, second never ran
        assert result["steps"][0]["status"] == "failed"
        assert result["steps"][1]["status"] == "pending"
        assert result["failure_reason"] != ""
        # explore's read_file + the single (failing) write_file; the 2nd step
        # was never dispatched
        assert [c[0] for c in svc.agent_loop.calls] == ["read_file", "write_file"]

    def test_execute_requires_executing_state(self):
        svc = make_service()
        plan = svc.start_plan("goal")
        with pytest.raises(PlanStateError):
            svc.execute(plan["plan_id"])

    def test_execute_missing(self):
        svc = make_service()
        with pytest.raises(PlanNotFoundError):
            svc.execute("nope")

    def test_execute_empty_steps_finishes_immediately(self):
        svc = make_service()
        plan = svc.start_plan("goal")
        svc.explore(plan["plan_id"], "read_file", {})
        svc.draft_plan(plan["plan_id"], [])
        svc.approve(plan["plan_id"])
        result = svc.execute(plan["plan_id"])
        assert result["state"] == PlanState.DONE.value


# ---------------------------------------------------------------------------
# cancel
# ---------------------------------------------------------------------------


class TestCancel:
    def _plan_in(self, svc, n_explores=0, draft=False):
        plan = svc.start_plan("goal")
        for _ in range(n_explores):
            svc.explore(plan["plan_id"], "read_file", {})
        if draft:
            svc.draft_plan(plan["plan_id"], [PlanStep("s", "t", "read_file")])
        return plan

    @pytest.mark.parametrize(
        "setup",
        ["exploring", "drafting", "awaiting", "executing"],
    )
    def test_cancel_from_active_states(self, setup):
        agent = FakeAgentLoop()
        svc = make_service(agent=agent)
        if setup == "exploring":
            plan = svc.start_plan("goal")
        elif setup == "drafting":
            plan = self._plan_in(svc, n_explores=1)
        elif setup == "awaiting":
            plan = self._plan_in(svc, n_explores=1, draft=True)
        else:  # executing
            plan = self._plan_in(svc, n_explores=1, draft=True)
            svc.approve(plan["plan_id"])
        result = svc.cancel(plan["plan_id"])
        assert result["state"] == PlanState.CANCELLED.value

    def test_cancel_from_terminal_raises(self):
        svc = make_service()
        plan = svc.start_plan("goal")
        svc.explore(plan["plan_id"], "read_file", {})
        svc.draft_plan(plan["plan_id"], [PlanStep("s", "t", "read_file")])
        svc.reject(plan["plan_id"], "no")
        with pytest.raises(PlanStateError):
            svc.cancel(plan["plan_id"])

    def test_cancel_missing(self):
        svc = make_service()
        with pytest.raises(PlanNotFoundError):
            svc.cancel("nope")


# ---------------------------------------------------------------------------
# ToolOutcome port contract
# ---------------------------------------------------------------------------


class TestToolOutcome:
    def test_carries_ok_and_output(self):
        from plan_mode.application.ports import ToolOutcome

        out = ToolOutcome(tool_name="write_file", ok=False, output="Error: boom")
        assert out.ok is False
        assert out.output == "Error: boom"

    def test_to_dict(self):
        from plan_mode.application.ports import ToolOutcome

        out = ToolOutcome(tool_name="read_file", ok=True, output="hi")
        assert out.to_dict() == {"tool_name": "read_file", "ok": True, "output": "hi"}


class TestStartPlanInput:
    @pytest.mark.parametrize("goal", ["", "   ", "\t\n"])
    def test_empty_goal_rejected(self, goal):
        from plan_mode.application.errors import PlanInputError

        svc = make_service()
        with pytest.raises(PlanInputError):
            svc.start_plan(goal)

    def test_list_plans_returns_all(self):
        svc = make_service()
        a = svc.start_plan("goal A")
        b = svc.start_plan("goal B")
        listed = svc.list_plans()
        assert {p["plan_id"] for p in listed} == {a["plan_id"], b["plan_id"]}

    def test_list_plans_empty(self):
        svc = make_service()
        assert svc.list_plans() == []
