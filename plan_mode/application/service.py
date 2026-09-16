"""Plan Mode application service — the use cases.

:class:`PlanModeService` orchestrates the domain (state machine, entities, tool
gate) against the injected ports (repository, workspace, agent loop) to implement
the Plan Mode lifecycle:

    start -> explore* -> draft -> (approve -> execute) | reject | edit -> ...

Every public method:
  1. loads the plan (raising :class:`~plan_mode.application.errors.PlanNotFoundError`),
  2. validates the current state against the requested action,
  3. performs the state transition (delegated to the domain),
  4. persists the plan,
  5. returns a JSON-safe dict via :meth:`Plan.to_dict`.

The service itself is stateless with respect to *current* state: the plan is the
source of truth, and each call re-reads it from the repository. That keeps the
service safe to share across requests/threads as long as the repository is.
"""

from __future__ import annotations

from typing import Optional

from plan_mode.application.errors import (
    PlanInputError,
    PlanNotFoundError,
    PlanStateError,
)
from plan_mode.application.ports import AgentLoopPort, PlanRepository, WorkspacePort
from plan_mode.domain.entities import Plan, PlanStep
from plan_mode.domain.states import ACTIVE_STATES, PlanState
from plan_mode.domain.tool_gate import ToolGate, classify_tool, ToolClass


class PlanModeService:
    """Implements the Plan Mode use cases.

    Attributes:
        repository: where plans are stored.
        workspace: resolves the default workspace path.
        agent_loop: executes tool calls during EXECUTING.
        gate: the fail-closed tool gate consulted during explore.

    Examples:
        >>> from tests.plan_mode.fakes import FakeAgentLoop, FakePlanRepository, FakeWorkspace
        >>> svc = PlanModeService(
        ...     repository=FakePlanRepository(),
        ...     workspace=FakeWorkspace(),
        ...     agent_loop=FakeAgentLoop(),
        ...     gate=ToolGate(),
        ... )
        >>> plan = svc.start_plan("fix login")
        >>> plan["state"]
        'exploring'
    """

    def __init__(
        self,
        repository: PlanRepository,
        workspace: WorkspacePort,
        agent_loop: AgentLoopPort,
        gate: Optional[ToolGate] = None,
    ) -> None:
        self.repository = repository
        self.workspace = workspace
        self.agent_loop = agent_loop
        self.gate = gate or ToolGate()

    # -- internal helpers -----------------------------------------------------

    def _load(self, plan_id: str) -> Plan:
        """Load a plan or raise :class:`PlanNotFoundError`.

        Args:
            plan_id: the plan to load.

        Returns:
            The stored plan.

        Raises:
            PlanNotFoundError: if no plan has this id.
        """
        plan = self.repository.get(plan_id)
        if plan is None:
            raise PlanNotFoundError(plan_id)
        return plan

    def _require_state(self, plan: Plan, allowed: set[PlanState], action: str) -> None:
        """Ensure ``plan.state`` is in ``allowed`` or raise :class:`PlanStateError`.

        Args:
            plan: the plan being validated.
            allowed: the set of states in which ``action`` is legal.
            action: a verb describing the action (for the error message).
        """
        if plan.state not in allowed:
            raise PlanStateError(plan.plan_id, action, plan.state.value)

    # -- use cases ------------------------------------------------------------

    def start_plan(self, goal: str, workspace: str = "") -> dict:
        """Start a new plan and move it straight into EXPLORING.

        Args:
            goal: the objective the plan should achieve (required, non-empty).
            workspace: optional workspace path; when empty the resolved
                workspace is used.

        Returns:
            The serialized plan dict in EXPLORING.

        Raises:
            PlanInputError: if ``goal`` is empty.

        Examples:
            >>> svc.start_plan("refactor auth")["state"]
            'exploring'
        """
        if not goal or not goal.strip():
            raise PlanInputError("goal is required and cannot be empty")
        plan = Plan.new(goal, workspace=workspace or self.workspace.resolve())
        plan.transition_to(PlanState.EXPLORING)
        self.repository.save(plan)
        return plan.to_dict()

    def explore(self, plan_id: str, tool_name: str, arguments: Optional[dict] = None) -> dict:
        """Run a read-only tool and record its output as an observation.

        Mutating or unknown tools are rejected by the gate (fail-closed), which
        surfaces as :class:`PlanStateError`. A successful read moves the plan from
        EXPLORING to DRAFTING; re-exploring from DRAFTING stays in DRAFTING.

        Args:
            plan_id: the plan to explore within.
            tool_name: a read-only tool to invoke.
            arguments: the tool's arguments.

        Returns:
            The serialized plan dict.

        Raises:
            PlanNotFoundError: if the plan does not exist.
            PlanStateError: if the plan is not in a read-only state, or the tool
                is not permitted in that state.

        Examples:
            >>> svc.explore(plan_id, "read_file", {"path": "a.py"})["state"]
            'drafting'
        """
        plan = self._load(plan_id)
        self._require_state(plan, {PlanState.EXPLORING, PlanState.DRAFTING}, "explore")

        decision = self.gate.check(plan.state, tool_name)
        if not decision.allowed:
            raise PlanStateError(plan.plan_id, f"explore with '{tool_name}'", plan.state.value)

        outcome = self.agent_loop.execute(tool_name, arguments or {})
        plan.add_observation(f"{tool_name}: {outcome.output}")

        if plan.state is PlanState.EXPLORING:
            plan.transition_to(PlanState.DRAFTING)
        self.repository.save(plan)
        return plan.to_dict()

    def draft_plan(self, plan_id: str, steps: list[PlanStep]) -> dict:
        """Record the plan's steps and move it to AWAITING_APPROVAL.

        A complete draft is submitted at once (the step list is replaced). This is
        valid from DRAFTING (first draft) or AWAITING_APPROVAL (a revised draft
        after "Edit plan").

        Args:
            plan_id: the plan to draft.
            steps: the ordered steps the approved plan should execute.

        Returns:
            The serialized plan dict in AWAITING_APPROVAL.

        Raises:
            PlanNotFoundError: if the plan does not exist.
            PlanStateError: if the plan is not in DRAFTING or AWAITING_APPROVAL.

        Examples:
            >>> svc.draft_plan(plan_id, [PlanStep("s", "t", "write_file")])["state"]
            'awaiting_approval'
        """
        plan = self._load(plan_id)
        self._require_state(
            plan, {PlanState.DRAFTING, PlanState.AWAITING_APPROVAL}, "draft"
        )
        plan.set_steps(steps)
        if plan.state is not PlanState.AWAITING_APPROVAL:
            plan.transition_to(PlanState.AWAITING_APPROVAL)
        self.repository.save(plan)
        return plan.to_dict()

    def get_plan(self, plan_id: str) -> Optional[dict]:
        """Return the serialized plan, or ``None`` if it does not exist.

        Args:
            plan_id: the plan to fetch.

        Returns:
            The serialized plan dict, or ``None``.
        """
        plan = self.repository.get(plan_id)
        return plan.to_dict() if plan is not None else None

    def list_plans(self) -> list[dict]:
        """Return all stored plans as serialized dicts.

        Returns:
            A list of plan dicts.
        """
        return [p.to_dict() for p in self.repository.list()]

    def approve(self, plan_id: str) -> dict:
        """Approve an awaiting plan, moving it to EXECUTING.

        Args:
            plan_id: the plan to approve.

        Returns:
            The serialized plan dict in EXECUTING.

        Raises:
            PlanNotFoundError / PlanStateError: as appropriate.

        Examples:
            >>> svc.approve(plan_id)["state"]
            'executing'
        """
        plan = self._load(plan_id)
        self._require_state(plan, {PlanState.AWAITING_APPROVAL}, "approve")
        plan.transition_to(PlanState.EXECUTING)
        self.repository.save(plan)
        return plan.to_dict()

    def reject(self, plan_id: str, reason: str = "") -> dict:
        """Reject an awaiting plan, moving it to REJECTED.

        Args:
            plan_id: the plan to reject.
            reason: a human-readable reason, recorded on the plan.

        Returns:
            The serialized plan dict in REJECTED.

        Raises:
            PlanNotFoundError / PlanStateError: as appropriate.
        """
        plan = self._load(plan_id)
        self._require_state(plan, {PlanState.AWAITING_APPROVAL}, "reject")
        plan.rejection_reason = reason or "rejected"
        plan.transition_to(PlanState.REJECTED)
        self.repository.save(plan)
        return plan.to_dict()

    def edit_plan(self, plan_id: str) -> dict:
        """Send an awaiting plan back to DRAFTING so it can be revised.

        Args:
            plan_id: the plan to re-open for editing.

        Returns:
            The serialized plan dict in DRAFTING (steps preserved).

        Raises:
            PlanNotFoundError / PlanStateError: as appropriate.
        """
        plan = self._load(plan_id)
        self._require_state(plan, {PlanState.AWAITING_APPROVAL}, "edit")
        plan.transition_to(PlanState.DRAFTING)
        self.repository.save(plan)
        return plan.to_dict()

    def execute(self, plan_id: str) -> dict:
        """Execute all pending steps of an executing plan, in order.

        Each step is dispatched through the agent loop. Execution proceeds step
        by step until every step is ``done`` (plan -> DONE) or a step fails
        (that step -> ``failed``, remaining steps stay ``pending``, plan ->
        CANCELLED with a ``failure_reason``).

        Args:
            plan_id: the plan to execute.

        Returns:
            The serialized plan dict (DONE or CANCELLED).

        Raises:
            PlanNotFoundError / PlanStateError: as appropriate.

        Examples:
            >>> svc.execute(plan_id)["state"] in {"done", "cancelled"}
            True
        """
        plan = self._load(plan_id)
        self._require_state(plan, {PlanState.EXECUTING}, "execute")

        while True:
            index = plan.next_pending_index()
            if index is None:
                break
            step = plan.steps[index]
            plan.mark_step(index, "running")
            outcome = self.agent_loop.execute(step.tool, step.arguments)
            if outcome.ok:
                plan.mark_step(index, "done")
            else:
                plan.mark_step(index, "failed")
                plan.failure_reason = (
                    f"Step '{step.title}' ({step.tool}) failed: {outcome.output}"
                )
                break

        target = PlanState.DONE if not plan.failure_reason else PlanState.CANCELLED
        plan.transition_to(target)
        self.repository.save(plan)
        return plan.to_dict()

    def cancel(self, plan_id: str) -> dict:
        """Cancel an active plan, moving it to CANCELLED.

        Legal from any active (non-terminal) state.

        Args:
            plan_id: the plan to cancel.

        Returns:
            The serialized plan dict in CANCELLED.

        Raises:
            PlanNotFoundError / PlanStateError: as appropriate.
        """
        plan = self._load(plan_id)
        self._require_state(plan, set(ACTIVE_STATES), "cancel")
        plan.transition_to(PlanState.CANCELLED)
        self.repository.save(plan)
        return plan.to_dict()
