"""Agent-loop adapter: run plan steps through the real tool registry.

:class:`ToolsAgentLoop` implements :class:`~plan_mode.application.ports.AgentLoopPort`
by delegating each step to the existing :func:`tools.execute_tool` and translating
the tool's return value into a :class:`~plan_mode.application.ports.ToolOutcome`.

The result mapping is the security-relevant part, so it is conservative:

* ``"approval_required"`` (a dict) -> not ok (the plan executor does not perform
  the interactive approval flow; a step that needs approval is a failure here).
* ``"Unknown tool: ..."`` / ``"Missing required argument: ..."`` / ``"Error ..."``
  -> not ok.
* Anything else (a string that is not an error, or a plain dict) -> ok.
"""

from __future__ import annotations

import json

from plan_mode.application.ports import AgentLoopPort, ToolOutcome

# Prefixes that indicate the tool call itself failed (as opposed to a successful
# read that merely found nothing).
_ERROR_PREFIXES: tuple[str, ...] = (
    "Error",
    "Unknown tool",
    "Missing required argument",
    "Could not parse tool arguments",
)


class ToolsAgentLoop(AgentLoopPort):
    """Bridges the Plan Mode executor to the concrete ``tools`` module.

    Attributes:
        tools_module: the module providing ``execute_tool``. Defaults to the real
            ``tools`` module; tests inject a fake to avoid a hard dependency.

    Examples:
        >>> from plan_mode.adapters.agents import ToolsAgentLoop
        >>> ToolsAgentLoop  # importable without importing `tools` at import time
        <class '...ToolsAgentLoop'>
    """

    def __init__(self, tools_module=None) -> None:
        if tools_module is None:
            import tools as tools_module  # imported lazily to keep the domain pure
        self._tools = tools_module

    def execute(self, tool_name: str, arguments: dict) -> ToolOutcome:
        """Run ``tool_name`` and classify the outcome.

        Args:
            tool_name: the tool to invoke.
            arguments: the tool's arguments.

        Returns:
            A :class:`ToolOutcome` whose ``ok`` reflects whether the call
            succeeded and whose ``output`` is the tool's return (string or
            serialized JSON).
        """
        try:
            result = self._tools.execute_tool(tool_name, arguments)
        except Exception as exc:  # noqa: BLE001 - a tool crash must not kill the plan
            return ToolOutcome(tool_name=tool_name, ok=False, output=f"Error: {exc}")

        return ToolOutcome(
            tool_name=tool_name,
            ok=self._is_ok(result),
            output=self._serialize(result),
        )

    # -- classification helpers ----------------------------------------------

    @staticmethod
    def _is_ok(result) -> bool:
        """Decide whether a tool return value represents success.

        Args:
            result: the raw value returned by ``execute_tool``.

        Returns:
            ``True`` if the call succeeded.

        Examples:
            >>> ToolsAgentLoop._is_ok("file contents")
            True
            >>> ToolsAgentLoop._is_ok("Error: boom")
            False
            >>> ToolsAgentLoop._is_ok({"status": "approval_required"})
            False
        """
        if isinstance(result, dict):
            return result.get("status") != "approval_required"
        text = str(result)
        return not any(text.startswith(prefix) for prefix in _ERROR_PREFIXES)

    @staticmethod
    def _serialize(result) -> str:
        """Render a tool result as a string (JSON for structured values).

        Args:
            result: the raw value returned by ``execute_tool``.

        Returns:
            A string representation.
        """
        if isinstance(result, str):
            return result
        try:
            return json.dumps(result, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(result)
