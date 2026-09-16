"""Tests for Plan / PlanStep domain entities."""

from __future__ import annotations

import pytest

from plan_mode.domain.entities import Plan, PlanStep
from plan_mode.domain.states import InvalidTransitionError, PlanState


class TestPlanStep:
    def test_defaults(self):
        s = PlanStep(step_id="s1", title="t", tool="write_file")
        assert s.arguments == {}
        assert s.status == "pending"
        assert s.detail == ""
        assert s.is_done is False
        assert s.is_failed is False

    def test_status_flags(self):
        assert PlanStep("a", "t", "x", status="done").is_done is True
        assert PlanStep("a", "t", "x", status="failed").is_failed is True
        assert PlanStep("a", "t", "x", status="done").is_failed is False


class TestPlanConstruction:
    def test_new_starts_idle(self):
        p = Plan.new("goal", workspace="/tmp/ws")
        assert p.state is PlanState.IDLE
        assert p.goal == "goal"
        assert p.workspace == "/tmp/ws"
        assert p.steps == []
        assert p.is_terminal is False

    def test_plan_id_is_unique(self):
        assert Plan.new("a").plan_id != Plan.new("b").plan_id


class TestTransitions:
    def test_happy_path(self):
        p = Plan.new("g")
        p.transition_to(PlanState.EXPLORING)
        p.transition_to(PlanState.DRAFTING)
        p.transition_to(PlanState.AWAITING_APPROVAL)
        p.transition_to(PlanState.EXECUTING)
        p.transition_to(PlanState.DONE)
        assert p.state is PlanState.DONE

    def test_illegal_raises(self):
        p = Plan.new("g")
        with pytest.raises(InvalidTransitionError):
            p.transition_to(PlanState.EXECUTING)

    def test_transition_returns_self_for_chaining(self):
        p = Plan.new("g")
        assert p.transition_to(PlanState.EXPLORING) is p


class TestSteps:
    def test_with_step_appends(self):
        p = Plan.new("g")
        # with_step is permitted in any non-terminal state; the service controls
        # *when* steps are recorded. IDLE is a valid, non-terminal starting point.
        p.with_step("Add validator", "write_file", {"path": "a.py", "content": "x"})
        assert len(p.steps) == 1
        assert p.steps[0].title == "Add validator"
        assert p.steps[0].tool == "write_file"
        assert p.steps[0].arguments == {"path": "a.py", "content": "x"}

    def test_with_step_defaults_args(self):
        p = Plan.new("g")
        p.with_step("read", "read_file", None, "detail text")
        assert p.steps[0].arguments == {}
        assert p.steps[0].detail == "detail text"

    def test_next_pending_index(self):
        p = Plan.new("g")
        assert p.next_pending_index() is None
        p.with_step("a", "read_file")
        p.with_step("b", "read_file")
        assert p.next_pending_index() == 0
        p.mark_step(0, "done")
        assert p.next_pending_index() == 1
        p.mark_step(1, "done")
        assert p.next_pending_index() is None

    def test_mark_step_invalid_status(self):
        p = Plan.new("g")
        p.with_step("a", "read_file")
        with pytest.raises(ValueError):
            p.mark_step(0, "not-a-status")

    def test_mark_step_out_of_range(self):
        p = Plan.new("g")
        with pytest.raises(IndexError):
            p.mark_step(5, "done")

    def test_cannot_add_step_when_terminal(self):
        p = Plan.new("g")
        p.transition_to(PlanState.EXPLORING)
        p.transition_to(PlanState.DRAFTING)
        p.transition_to(PlanState.AWAITING_APPROVAL)
        p.transition_to(PlanState.REJECTED)
        with pytest.raises(ValueError):
            p.with_step("late", "write_file")


class TestObservations:
    def test_add_observation(self):
        p = Plan.new("g")
        p.add_observation("found login()")
        assert p.observations == ["found login()"]

    def test_empty_ignored(self):
        p = Plan.new("g")
        p.add_observation("")
        assert p.observations == []

    def test_truncation(self):
        p = Plan.new("g")
        p.add_observation("x" * (Plan.MAX_OBSERVATION_CHARS + 10))
        assert len(p.observations[0]) == Plan.MAX_OBSERVATION_CHARS + 3  # + "..."
        assert p.observations[0].endswith("...")

    def test_bounded_to_max(self):
        p = Plan.new("g")
        for i in range(Plan.MAX_OBSERVATIONS + 5):
            p.add_observation(f"obs {i}")
        assert len(p.observations) == Plan.MAX_OBSERVATIONS
        # oldest dropped, newest retained
        assert p.observations[-1] == f"obs {Plan.MAX_OBSERVATIONS + 4}"


class TestSerialization:
    def test_roundtrip(self):
        p = Plan.new("refactor auth", workspace="/ws")
        p.transition_to(PlanState.EXPLORING)
        p.transition_to(PlanState.DRAFTING)
        p.with_step("s1", "write_file", {"path": "a.py", "content": "x"}, "detail")
        p.add_observation("note")
        p.mark_step(0, "running")
        d = p.to_dict()
        q = Plan.from_dict(d)
        assert q.plan_id == p.plan_id
        assert q.goal == p.goal
        assert q.state is PlanState.DRAFTING
        assert q.workspace == "/ws"
        assert len(q.steps) == 1
        assert q.steps[0].status == "running"
        assert q.observations == ["note"]

    def test_to_dict_is_json_safe(self):
        import json

        p = Plan.new("g")
        p.with_step("s", "read_file", {"path": "a"})
        serialized = json.dumps(p.to_dict())
        assert isinstance(serialized, str)

    def test_from_dict_tolerates_missing_new_keys(self):
        # Simulate a plan serialized before observations/failure_reason existed.
        data = {
            "plan_id": "id",
            "goal": "g",
            "state": "drafting",
            "workspace": "",
            "rejection_reason": "",
            "created_at": 123.0,
            "steps": [{"step_id": "1", "title": "t", "tool": "read_file", "arguments": {}, "status": "pending"}],
        }
        p = Plan.from_dict(data)
        assert p.observations == []
        assert p.failure_reason == ""
        assert p.state is PlanState.DRAFTING
