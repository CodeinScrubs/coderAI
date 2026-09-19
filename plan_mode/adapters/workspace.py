"""Workspace adapter: resolve the active workspace from the tools layer."""

from __future__ import annotations

from plan_mode.application.ports import WorkspacePort


class PathWorkspace(WorkspacePort):
    """Resolves the active workspace path via :func:`tools.get_workspace`.

    The workspace is resolved lazily at call time (not at construction), matching
    how the rest of the app treats the active workspace: it can change at runtime
    when the user activates a different folder.

    Examples:
        >>> ws = PathWorkspace()
        >>> isinstance(ws.resolve(), str)
        True
    """

    def resolve(self) -> str:
        """Return the absolute path of the currently active workspace.

        Returns:
            An absolute directory path string.
        """
        import coderai.tools.tools as tools

        return str(tools.get_workspace())
