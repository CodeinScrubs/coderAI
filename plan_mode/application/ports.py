"""Ports (interfaces) of the Plan Mode application layer.

The application layer depends only on these abstractions, never on a concrete
repository, workspace, or tool runtime. Concrete implementations live in
:mod:`plan_mode.adapters` and are injected into
:class:`~plan_mode.application.service.PlanModeService`. This is the dependency
rule in action: adapters implement ports; the application never imports adapters.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from plan_mode.domain.entities import Plan


@dataclass
class ToolOutcome:
    """The result of executing a single tool call.

    Attributes:
        tool_name: the tool that was invoked.
        ok: whether the tool ran without reporting an error.
        output: the tool's return value (string or serialized JSON).

    Notes:
        A tool may *execute successfully* and still report a domain error
        (e.g. a read that finds no file, or a write that is rejected). The
        adapter is responsible for setting ``ok`` correctly from the tool's
        return value; the service treats ``ok=False`` as a failed step.
    """

    tool_name: str
    ok: bool
    output: str

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict.

        Returns:
            ``{"tool_name", "ok", "output"}``.
        """
        return {"tool_name": self.tool_name, "ok": self.ok, "output": self.output}


class PlanRepository(ABC):
    """Persists and retrieves :class:`~plan_mode.domain.entities.Plan` objects."""

    @abstractmethod
    def save(self, plan: Plan) -> None:
        """Persist ``plan`` (create or update).

        Args:
            plan: the plan to store.
        """

    @abstractmethod
    def get(self, plan_id: str) -> Optional[Plan]:
        """Return the plan with ``plan_id``, or ``None`` if absent.

        Args:
            plan_id: the plan identifier.

        Returns:
            The stored plan, or ``None``.
        """

    @abstractmethod
    def list(self) -> list[Plan]:
        """Return all stored plans (order is implementation-defined)."""


class WorkspacePort(ABC):
    """Resolves the workspace the plan should operate in."""

    @abstractmethod
    def resolve(self) -> str:
        """Return the absolute path of the active workspace.

        Returns:
            An absolute directory path.
        """


class AgentLoopPort(ABC):
    """Executes a single tool call on behalf of the plan executor.

    The application layer never imports the concrete tool registry; it only asks
    this port to run a tool and report back a :class:`ToolOutcome`.
    """

    @abstractmethod
    def execute(self, tool_name: str, arguments: dict) -> ToolOutcome:
        """Run ``tool_name`` with ``arguments`` and report the result.

        Args:
            tool_name: the tool to invoke.
            arguments: the tool's arguments.

        Returns:
            A :class:`ToolOutcome` describing the result.
        """
