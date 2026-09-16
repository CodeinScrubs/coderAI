"""In-memory fakes for Plan Mode ports, used to test the application layer
without touching disk, the workspace, or the real tool set."""

from __future__ import annotations

from typing import Optional

from plan_mode.application.ports import ToolOutcome
from plan_mode.domain.entities import Plan


class FakePlanRepository:
    """A dict-backed PlanRepository for tests."""

    def __init__(self) -> None:
        self._plans: dict[str, Plan] = {}

    def save(self, plan: Plan) -> None:
        self._plans[plan.plan_id] = plan

    def get(self, plan_id: str) -> Optional[Plan]:
        return self._plans.get(plan_id)

    def list(self) -> list[Plan]:
        return list(self._plans.values())


class FakeWorkspace:
    """A fixed WorkspacePort."""

    def __init__(self, path: str = "/tmp/fake-ws") -> None:
        self._path = path

    def resolve(self) -> str:
        return self._path


class FakeAgentLoop:
    """An AgentLoopPort that records calls and returns canned output.

    ``fail_tools`` is a set of tool names whose calls should return an error
    string (simulating a failing tool).
    """

    def __init__(self, fail_tools: set[str] | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._fail_tools = fail_tools or set()

    def execute(self, tool_name: str, arguments: dict) -> ToolOutcome:
        self.calls.append((tool_name, arguments))
        if tool_name in self._fail_tools:
            return ToolOutcome(
                tool_name=tool_name, ok=False, output=f"Error in '{tool_name}': simulated failure"
            )
        return ToolOutcome(tool_name=tool_name, ok=True, output=f"ok:{tool_name}")
