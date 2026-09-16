"""Fail-closed tool gate for Plan Mode.

The gate answers one question: *may a tool be invoked while the plan is in state
``S``?* It classifies every tool as read-only or mutating, then applies the state
rules from the design mock:

    | state                  | read-only tools | mutating tools |
    |------------------------|:---------------:|:--------------:|
    | IDLE                   | blocked         | blocked        |
    | EXPLORING / DRAFTING   | allowed         | **blocked**    |
    | AWAITING_APPROVAL      | allowed         | **blocked**    |
    | EXECUTING              | allowed         | allowed*       |
    | DONE / REJECTED /      | blocked         | blocked        |
    | CANCELLED              |                 |                |

``*`` "allowed" in EXECUTING means the gate does not stop the call; *which* calls
may be issued is the executor's concern (it only ever invokes the plan's own
steps, which are the approved set). The gate enforces the state boundary; the
executor enforces the step boundary.

**Fail-closed:** a tool name that is not present in :data:`READ_ONLY_TOOLS` is
treated as mutating. New/unknown tools are therefore blocked outside EXECUTING by
default, which is the safe direction when the classification is in doubt.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from plan_mode.domain.states import PlanState, TERMINAL_STATES


class ToolClass(str, Enum):
    """How the gate treats a tool with respect to the workspace."""

    READ_ONLY = "read_only"
    MUTATING = "mutating"


# Tools that only observe the workspace (read files, search, graph, read-only
# git, memory reads, network reads). Anything else — including every tool added
# in the future — is assumed mutating and thus fail-closed in read-only states.
READ_ONLY_TOOLS: frozenset[str] = frozenset(
    {
        # file reading / listing
        "read_file",
        "read_many_files",
        "list_files",
        "project_tree",
        # search / RAG
        "search_files",
        "search_codebase",
        # project intelligence / graph
        "get_project_overview",
        "get_related_files",
        "scan_project",
        "get_project_architecture",
        "get_impact_radius",
        "query_code_graph",
        "get_code_review_context",
        # read-only git
        "git_status",
        "git_log",
        "git_diff",
        # memory reads
        "recall_memory",
        "reflect_memory",
        # network reads (no local mutation)
        "fetch_url",
        "web_search",
        "extract_url",
        # misc
        "current_time",
        "get_database_schema",
        "get_container_logs",
    }
)


@dataclass(frozen=True)
class GateDecision:
    """The outcome of a gate check.

    Attributes:
        allowed: whether the tool may run in the given state.
        state: the plan state that was checked.
        tool: the tool name that was checked.
        tool_class: how the tool was classified.
        reason: a short human-readable explanation (used in error messages).
    """

    allowed: bool
    state: PlanState
    tool: str
    tool_class: ToolClass
    reason: str


def classify_tool(name: str) -> ToolClass:
    """Classify ``name`` as :data:`ToolClass.READ_ONLY` or :data:`ToolClass.MUTATING`.

    Fails closed: an unknown name is classified as mutating.

    Args:
        name: the tool name.

    Returns:
        The tool class.

    Examples:
        >>> classify_tool("read_file")
        <ToolClass.READ_ONLY: 'read_only'>
        >>> classify_tool("write_file")
        <ToolClass.MUTATING: 'mutating'>
        >>> classify_tool("brand_new_tool")  # unknown -> mutating
        <ToolClass.MUTATING: 'mutating'>
    """
    return ToolClass.READ_ONLY if name in READ_ONLY_TOOLS else ToolClass.MUTATING


class ToolGate:
    """State-aware, fail-closed gate over tool invocation.

    The gate is stateless (the plan state is passed per call), so a single
    instance can be shared safely across threads.

    Examples:
        >>> gate = ToolGate()
        >>> gate.check(PlanState.EXPLORING, "read_file").allowed
        True
        >>> gate.check(PlanState.EXPLORING, "write_file").allowed
        False
    """

    def classify(self, name: str) -> ToolClass:
        """Delegate to :func:`classify_tool` (kept for interface symmetry)."""
        return classify_tool(name)

    def is_allowed(self, state: PlanState, tool_name: str) -> bool:
        """Return ``True`` if ``tool_name`` may run while the plan is in ``state``.

        Args:
            state: the current plan state.
            tool_name: the tool about to be invoked.

        Returns:
            Whether the call passes the gate.
        """
        return self.check(state, tool_name).allowed

    def check(self, state: PlanState, tool_name: str) -> GateDecision:
        """Evaluate the gate and return a detailed :class:`GateDecision`.

        Args:
            state: the current plan state.
            tool_name: the tool about to be invoked.

        Returns:
            A :class:`GateDecision` with a human-readable ``reason``.
        """
        cls = classify_tool(tool_name)

        # Terminal states block everything — no reads, no writes.
        if state in TERMINAL_STATES:
            return GateDecision(
                allowed=False,
                state=state,
                tool=tool_name,
                tool_class=cls,
                reason=f"Plan is terminal ({state.value}); no tools may run.",
            )

        if state is PlanState.IDLE:
            return GateDecision(
                allowed=False,
                state=state,
                tool=tool_name,
                tool_class=cls,
                reason="Plan is idle; start exploration before running tools.",
            )

        if state is PlanState.EXECUTING:
            # Both read and mutating tools are permitted during execution.
            return GateDecision(
                allowed=True,
                state=state,
                tool=tool_name,
                tool_class=cls,
                reason="Executing approved plan; tool permitted.",
            )

        # EXPLORING / DRAFTING / AWAITING_APPROVAL: read-only only.
        if cls is ToolClass.READ_ONLY:
            return GateDecision(
                allowed=True,
                state=state,
                tool=tool_name,
                tool_class=cls,
                reason="Read-only tool permitted during planning.",
            )
        return GateDecision(
            allowed=False,
            state=state,
            tool=tool_name,
            tool_class=cls,
            reason=(
                f"Mutating tool '{tool_name}' is blocked in read-only state "
                f"{state.value}; approve the plan to execute it."
            ),
        )
