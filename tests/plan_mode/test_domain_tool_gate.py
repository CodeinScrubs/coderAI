"""Tests for the fail-closed Plan Mode tool gate."""

from __future__ import annotations

import pytest

from plan_mode.domain.states import PlanState
from plan_mode.domain.tool_gate import (
    READ_ONLY_TOOLS,
    ToolClass,
    ToolGate,
    classify_tool,
)

# A representative spread of read-only and mutating tools to test against.
READ_EXAMPLE = ["read_file", "search_codebase", "git_status", "fetch_url"]
MUTATING_EXAMPLE = [
    "write_file",
    "replace_in_file",
    "append_file",
    "delete_file",
    "run_bash",
    "create_directory",
    "git_commit",
]


class TestClassifyTool:
    @pytest.mark.parametrize("name", sorted(READ_ONLY_TOOLS))
    def test_known_read_only(self, name):
        assert classify_tool(name) is ToolClass.READ_ONLY

    @pytest.mark.parametrize("name", MUTATING_EXAMPLE)
    def test_known_mutating(self, name):
        assert classify_tool(name) is ToolClass.MUTATING

    @pytest.mark.parametrize("name", ["totally_new_tool", "delete_everything", ""])
    def test_unknown_fails_closed_to_mutating(self, name):
        # This is the core safety guarantee: anything we have not explicitly
        # blessed as read-only is treated as mutating.
        assert classify_tool(name) is ToolClass.MUTATING

    def test_misuse_of_read_only_toolname_is_still_classified_by_name(self):
        # Classification is purely by name; the gate does not (and cannot)
        # inspect arguments. A read-only tool named with a mutating name is not
        # our case here, but a mutating tool that merely reads an argument stays
        # mutating.
        assert classify_tool("run_bash") is ToolClass.MUTATING


class TestGateReadStates:
    """EXPLORING / DRAFTING / AWAITING_APPROVAL permit read-only, block mutating."""

    @pytest.mark.parametrize("state", [PlanState.EXPLORING, PlanState.DRAFTING, PlanState.AWAITING_APPROVAL])
    def test_allows_read_only(self, state):
        gate = ToolGate()
        for name in READ_EXAMPLE:
            assert gate.is_allowed(state, name) is True, name

    @pytest.mark.parametrize("state", [PlanState.EXPLORING, PlanState.DRAFTING, PlanState.AWAITING_APPROVAL])
    def test_blocks_mutating(self, state):
        gate = ToolGate()
        for name in MUTATING_EXAMPLE:
            assert gate.is_allowed(state, name) is False, name

    @pytest.mark.parametrize("state", [PlanState.EXPLORING, PlanState.DRAFTING, PlanState.AWAITING_APPROVAL])
    def test_blocks_unknown_tool(self, state):
        gate = ToolGate()
        assert gate.is_allowed(state, "unknown_future_tool") is False

    def test_decision_explains_block(self):
        gate = ToolGate()
        d = gate.check(PlanState.EXPLORING, "write_file")
        assert d.allowed is False
        assert d.tool_class is ToolClass.MUTATING
        assert "blocked" in d.reason
        assert d.tool == "write_file"


class TestGateExecuting:
    def test_allows_read_only(self):
        gate = ToolGate()
        for name in READ_EXAMPLE:
            assert gate.is_allowed(PlanState.EXECUTING, name) is True

    def test_allows_mutating(self):
        gate = ToolGate()
        for name in MUTATING_EXAMPLE:
            assert gate.is_allowed(PlanState.EXECUTING, name) is True, name

    def test_allows_unknown(self):
        # During execution the gate does not second-guess the approved step set;
        # step-boundary enforcement is the executor's job, not the gate's.
        gate = ToolGate()
        assert gate.is_allowed(PlanState.EXECUTING, "unknown_future_tool") is True


class TestGateBlockedStates:
    @pytest.mark.parametrize("state", [PlanState.IDLE, PlanState.DONE, PlanState.REJECTED, PlanState.CANCELLED])
    def test_blocks_everything(self, state):
        gate = ToolGate()
        for name in READ_EXAMPLE + MUTATING_EXAMPLE + ["unknown_future_tool"]:
            assert gate.is_allowed(state, name) is False, name

    def test_idle_reason_mentions_start(self):
        gate = ToolGate()
        d = gate.check(PlanState.IDLE, "read_file")
        assert d.allowed is False
        assert "idle" in d.reason.lower()


class TestGateDeterminismAndStatelessness:
    def test_same_input_same_decision(self):
        gate = ToolGate()
        first = gate.check(PlanState.DRAFTING, "delete_file")
        second = gate.check(PlanState.DRAFTING, "delete_file")
        assert (first.allowed, first.reason) == (second.allowed, second.reason)

    def test_instance_is_stateless_shareable(self):
        # A single shared instance must give consistent answers across states.
        gate = ToolGate()
        assert gate.is_allowed(PlanState.EXPLORING, "read_file") is True
        assert gate.is_allowed(PlanState.EXECUTING, "write_file") is True
        assert gate.is_allowed(PlanState.DRAFTING, "write_file") is False

    def test_classify_delegates(self):
        gate = ToolGate()
        assert gate.classify("read_file") is ToolClass.READ_ONLY
        assert gate.classify("write_file") is ToolClass.MUTATING
