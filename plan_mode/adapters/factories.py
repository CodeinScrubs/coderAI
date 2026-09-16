"""Composition root for the default Plan Mode service.

Wires concrete adapters to the application service:

* repository — JSON-on-disk when a directory is supplied, in-memory otherwise
  (tests and the pure-library default use the in-memory store);
* workspace  — :class:`~plan_mode.adapters.workspace.PathWorkspace`;
* agent loop — :class:`~plan_mode.adapters.agents.ToolsAgentLoop` (the real
  ``tools`` registry, imported lazily);
* gate       — a default :class:`~plan_mode.domain.tool_gate.ToolGate`.

This is the only place in the module that names concrete adapter classes; the
rest of the code depends on ports.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Union

from plan_mode.adapters.agents import ToolsAgentLoop
from plan_mode.adapters.repositories import JsonPlanRepository, MemoryPlanRepository
from plan_mode.adapters.workspace import PathWorkspace
from plan_mode.application.service import PlanModeService
from plan_mode.domain.tool_gate import ToolGate


def _base_dir() -> Path:
    """Return the application base directory (mirrors ``web_app.ROOT``).

    Under a PyInstaller bundle this is the extraction dir (``sys._MEIPASS``);
    otherwise it is the project root (two levels above this file: this file is
    ``<root>/plan_mode/adapters/factories.py``).

    Returns:
        The base directory as a :class:`Path`.
    """
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


def default_plans_dir() -> Path:
    """Return the conventional on-disk location for persisted plans.

    Returns:
        ``<base>/coderai_data/plans``.

    Examples:
        >>> d = default_plans_dir()
        >>> d.name
        'plans'
    """
    return _base_dir() / "coderai_data" / "plans"


def build_default_service(
    directory: Optional[Union[str, Path]] = None,
) -> PlanModeService:
    """Build a fully wired :class:`PlanModeService`.

    Args:
        directory: if given (str or Path), plans are persisted as JSON under it
            (JSON repository). If ``None``, an in-memory repository is used, so
            importing and building the service has no side effects on disk.

    Returns:
        A ready-to-use service.

    Examples:
        >>> svc = build_default_service()          # in-memory, no disk writes
        >>> svc.start_plan("goal")["state"]
        'exploring'
        >>> svc = build_default_service("./plans") # persistent
        >>> isinstance(svc, PlanModeService)
        True
    """
    if directory is None:
        repository = MemoryPlanRepository()
    else:
        repository = JsonPlanRepository(Path(directory))

    return PlanModeService(
        repository=repository,
        workspace=PathWorkspace(),
        agent_loop=ToolsAgentLoop(),
        gate=ToolGate(),
    )
