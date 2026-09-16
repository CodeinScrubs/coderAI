"""Plan-mode lifecycle states and transition rules.

This module is the single source of truth for the Plan Mode state machine. It is
pure: no I/O, no dependencies on the application or adapter layers. The state
machine it defines lets the agent *explore* the codebase read-only, *draft* a
set of steps, hold them for human *approval*, and only then *execute* them.

Lifecycle (forward direction)::

    IDLE -> EXPLORING -> DRAFTING -> AWAITING_APPROVAL -> EXECUTING -> DONE
              |              |               |                 |
              +--------------+--- REJECTED / CANCELLED <-------+

``AWAITING_APPROVAL`` may return to ``DRAFTING`` so the reviewer can refine the
plan before approving (the "Edit plan" action in the UI mock). ``REJECTED`` and
``CANCELLED`` are terminal: to proceed after one of them, start a fresh plan.
"""

from __future__ import annotations

from enum import Enum


class PlanState(str, Enum):
    """The finite set of states a Plan can occupy."""

    IDLE = "idle"
    EXPLORING = "exploring"
    DRAFTING = "drafting"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    DONE = "done"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


#: States from which no further transitions are possible.
TERMINAL_STATES: frozenset[PlanState] = frozenset(
    {PlanState.DONE, PlanState.REJECTED, PlanState.CANCELLED}
)

#: States in which the plan is actively progressing (not yet terminal).
ACTIVE_STATES: frozenset[PlanState] = frozenset(
    {
        PlanState.IDLE,
        PlanState.EXPLORING,
        PlanState.DRAFTING,
        PlanState.AWAITING_APPROVAL,
        PlanState.EXECUTING,
    }
)

#: Allowed transitions. ``TRANSITIONS[s]`` is the set of states ``s`` may move to.
#: Anything not listed here is illegal and raises :class:`InvalidTransitionError`.
TRANSITIONS: dict[PlanState, frozenset[PlanState]] = {
    PlanState.IDLE: frozenset({PlanState.EXPLORING, PlanState.CANCELLED}),
    PlanState.EXPLORING: frozenset({PlanState.DRAFTING, PlanState.CANCELLED}),
    # Re-exploration is allowed from DRAFTING when the reviewer realizes more
    # context is needed before the plan is final.
    PlanState.DRAFTING: frozenset(
        {PlanState.AWAITING_APPROVAL, PlanState.EXPLORING, PlanState.CANCELLED}
    ),
    # "Edit plan" sends an awaiting-approval plan back to DRAFTING.
    PlanState.AWAITING_APPROVAL: frozenset(
        {PlanState.EXECUTING, PlanState.DRAFTING, PlanState.REJECTED, PlanState.CANCELLED}
    ),
    PlanState.EXECUTING: frozenset({PlanState.DONE, PlanState.CANCELLED}),
    PlanState.DONE: frozenset(),
    PlanState.REJECTED: frozenset(),
    PlanState.CANCELLED: frozenset(),
}


class InvalidTransitionError(Exception):
    """Raised when a transition between two Plan states is not allowed.

    Attributes:
        source: the state the plan is currently in.
        target: the state the caller tried to move to.
    """

    def __init__(self, source: PlanState, target: PlanState) -> None:
        self.source = source
        self.target = target
        super().__init__(
            f"Illegal plan transition: {source.value} -> {target.value}"
        )


def can_transition(source: PlanState, target: PlanState) -> bool:
    """Return ``True`` if moving from ``source`` to ``target`` is legal.

    Args:
        source: the current state.
        target: the requested next state.

    Returns:
        Whether the transition is permitted by :data:`TRANSITIONS`.

    Examples:
        >>> can_transition(PlanState.IDLE, PlanState.EXPLORING)
        True
        >>> can_transition(PlanState.IDLE, PlanState.EXECUTING)
        False
    """
    return target in TRANSITIONS[source]
