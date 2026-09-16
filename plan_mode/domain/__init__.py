"""Pure domain layer for Plan Mode (state machine, entities, tool gate).

No I/O here. Re-exports the public domain API for convenient imports.
"""

from __future__ import annotations

from plan_mode.domain.states import (
    ACTIVE_STATES,
    TERMINAL_STATES,
    TRANSITIONS,
    InvalidTransitionError,
    PlanState,
    can_transition,
)
from plan_mode.domain.entities import Plan, PlanStep
from plan_mode.domain.tool_gate import READ_ONLY_TOOLS, GateDecision, ToolClass, ToolGate, classify_tool

__all__ = [
    "PlanState",
    "PlanStep",
    "Plan",
    "ToolGate",
    "ToolClass",
    "GateDecision",
    "READ_ONLY_TOOLS",
    "classify_tool",
    "InvalidTransitionError",
    "can_transition",
    "TRANSITIONS",
    "TERMINAL_STATES",
    "ACTIVE_STATES",
]
