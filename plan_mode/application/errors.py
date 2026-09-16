"""Exception types raised by the Plan Mode application service.

These are *expected* control-flow errors, not crashes: the HTTP adapter catches
them and maps each to an appropriate status code (404 for a missing plan, 409 for
an illegal state transition, 400 for invalid input).
"""

from __future__ import annotations


class PlanModeError(Exception):
    """Base class for all Plan Mode application errors."""


class PlanNotFoundError(PlanModeError):
    """Raised when a plan_id does not resolve to a stored plan."""

    def __init__(self, plan_id: str) -> None:
        self.plan_id = plan_id
        super().__init__(f"Plan not found: {plan_id}")


class PlanStateError(PlanModeError):
    """Raised when an action is not valid for the plan's current state.

    Attributes:
        plan_id: the plan the action was attempted on.
        action: a short verb describing the attempted action (e.g. "approve").
        state: the plan's current state (string form).
    """

    def __init__(self, plan_id: str, action: str, state: str) -> None:
        self.plan_id = plan_id
        self.action = action
        self.state = state
        super().__init__(f"Cannot {action} a plan in state '{state}'")


class PlanInputError(PlanModeError):
    """Raised when a request carries invalid input (e.g. missing goal)."""
