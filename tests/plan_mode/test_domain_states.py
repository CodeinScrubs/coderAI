"""Tests for the Plan Mode state machine (plan_mode.domain.states)."""

from __future__ import annotations

import pytest

from plan_mode.domain.states import (
    InvalidTransitionError,
    PlanState,
    TERMINAL_STATES,
    TRANSITIONS,
    can_transition,
)


class TestCanTransition:
    def test_idle_to_exploring(self):
        assert can_transition(PlanState.IDLE, PlanState.EXPLORING) is True

    def test_exploring_to_drafting(self):
        assert can_transition(PlanState.EXPLORING, PlanState.DRAFTING) is True

    def test_drafting_to_awaiting_approval(self):
        assert can_transition(PlanState.DRAFTING, PlanState.AWAITING_APPROVAL) is True

    def test_awaiting_to_executing(self):
        assert can_transition(PlanState.AWAITING_APPROVAL, PlanState.EXECUTING) is True

    def test_executing_to_done(self):
        assert can_transition(PlanState.EXECUTING, PlanState.DONE) is True

    def test_drafting_back_to_exploring(self):
        # Re-exploration before the plan is final.
        assert can_transition(PlanState.DRAFTING, PlanState.EXPLORING) is True

    def test_awaiting_back_to_drafting(self):
        # "Edit plan" path.
        assert can_transition(PlanState.AWAITING_APPROVAL, PlanState.DRAFTING) is True


class TestIllegalTransitions:
    @pytest.mark.parametrize(
        "source,target",
        [
            (PlanState.IDLE, PlanState.EXECUTING),
            (PlanState.IDLE, PlanState.DONE),
            (PlanState.IDLE, PlanState.AWAITING_APPROVAL),
            (PlanState.EXPLORING, PlanState.EXECUTING),
            (PlanState.EXPLORING, PlanState.AWAITING_APPROVAL),
            (PlanState.DRAFTING, PlanState.EXECUTING),
            (PlanState.EXECUTING, PlanState.DRAFTING),
            (PlanState.EXECUTING, PlanState.AWAITING_APPROVAL),
            (PlanState.AWAITING_APPROVAL, PlanState.EXPLORING),
        ],
    )
    def test_illegal(self, source, target):
        assert can_transition(source, target) is False

    @pytest.mark.parametrize(
        "terminal",
        [PlanState.DONE, PlanState.REJECTED, PlanState.CANCELLED],
    )
    def test_terminal_states_block_everything(self, terminal):
        for target in PlanState:
            assert can_transition(terminal, target) is False

    def test_terminal_states_membership(self):
        assert PlanState.DONE in TERMINAL_STATES
        assert PlanState.REJECTED in TERMINAL_STATES
        assert PlanState.CANCELLED in TERMINAL_STATES
        assert PlanState.EXECUTING not in TERMINAL_STATES

    def test_transitions_table_complete(self):
        # Every state must appear as a key in the transition table.
        assert set(TRANSITIONS.keys()) == set(PlanState)


class TestInvalidTransitionError:
    def test_message_and_fields(self):
        err = InvalidTransitionError(PlanState.IDLE, PlanState.EXECUTING)
        assert err.source is PlanState.IDLE
        assert err.target is PlanState.EXECUTING
        assert "idle" in str(err)
        assert "executing" in str(err)
