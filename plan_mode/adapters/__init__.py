"""Adapter layer for Plan Mode: concrete ports and the composition root.

Re-exports the public adapter API.
"""

from __future__ import annotations

from plan_mode.adapters.agents import ToolsAgentLoop
from plan_mode.adapters.repositories import JsonPlanRepository, MemoryPlanRepository
from plan_mode.adapters.workspace import PathWorkspace
from plan_mode.adapters.factories import build_default_service, default_plans_dir

__all__ = [
    "MemoryPlanRepository",
    "JsonPlanRepository",
    "PathWorkspace",
    "ToolsAgentLoop",
    "build_default_service",
    "default_plans_dir",
]
