"""Plan and PlanStep domain entities.

These are value objects: :class:`PlanStep` is a frozen dataclass (immutable),
and :class:`Plan` carries an immutable core (goal, steps, metadata) plus a single
mutable field — its :class:`~plan_mode.domain.states.PlanState` — which the state
machine mutates in place. Steps are appended via a *copy* method
(:meth:`Plan.with_step`) so the step list itself stays append-only and callers can
never mutate a plan they were handed.

The domain layer has no I/O: nothing here touches disk, the workspace, or tools.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, replace
from typing import Optional

from plan_mode.domain.states import (
    InvalidTransitionError,
    PlanState,
    TERMINAL_STATES,
    can_transition,
)


def _utcnow() -> float:
    """Return the current Unix time in seconds (float).

    Wrapped in a helper so tests can monkeypatch a single, stable seam instead of
    reaching into :mod:`time`.
    """
    return time.time()


@dataclass(frozen=True)
class PlanStep:
    """A single, atomic action a Plan intends to perform.

    Attributes:
        step_id: stable unique identifier.
        title: short human-readable summary of the step.
        detail: longer description, optional.
        tool: name of the tool the step will invoke (e.g. ``"write_file"``).
        arguments: the tool arguments the step will pass, verbatim.
        status: one of ``"pending"``, ``"running"``, ``"done"``, ``"failed"``.

    Examples:
        >>> PlanStep(
        ...     step_id="s1",
        ...     title="Add validator",
        ...     tool="write_file",
        ...     arguments={"path": "auth/validator.py", "content": "..."},
        ... ).status
        'pending'
    """

    step_id: str
    title: str
    tool: str
    arguments: dict = field(default_factory=dict)
    detail: str = ""
    status: str = "pending"

    @property
    def is_done(self) -> bool:
        """Return ``True`` if the step finished successfully."""
        return self.status == "done"

    @property
    def is_failed(self) -> bool:
        """Return ``True`` if the step failed."""
        return self.status == "failed"


@dataclass
class Plan:
    """A plan to be approved and executed by the agent.

    Attributes:
        plan_id: stable unique identifier for the plan.
        goal: the natural-language objective the plan is meant to achieve.
        state: the current lifecycle state.
        steps: the ordered list of :class:`PlanStep` to execute, in order.
        workspace: absolute path of the workspace the plan targets (optional; the
            adapter resolves a sensible default when empty).
        rejection_reason: set when the plan is rejected, explaining why.
        created_at: creation timestamp (seconds since epoch).
    """

    plan_id: str
    goal: str
    state: PlanState = PlanState.IDLE
    steps: list[PlanStep] = field(default_factory=list)
    workspace: str = ""
    rejection_reason: str = ""
    failure_reason: str = ""
    observations: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=_utcnow)

    #: Bounding limits for the rolling observation buffer.
    MAX_OBSERVATION_CHARS = 2_000
    MAX_OBSERVATIONS = 25

    # -- construction helpers -------------------------------------------------

    @classmethod
    def new(cls, goal: str, workspace: str = "") -> "Plan":
        """Create a fresh plan in :data:`~plan_mode.domain.states.PlanState.IDLE`.

        Args:
            goal: the objective text.
            workspace: optional absolute workspace path.

        Returns:
            A brand-new :class:`Plan`.

        Examples:
            >>> p = Plan.new("Refactor auth", workspace="/tmp/ws")
            >>> p.state
            <PlanState.IDLE: 'idle'>
            >>> bool(p.plan_id)
            True
        """
        return cls(plan_id=uuid.uuid4().hex, goal=goal, workspace=workspace)

    # -- state machine --------------------------------------------------------

    def transition_to(self, target: PlanState) -> "Plan":
        """Move the plan to ``target`` if the transition is legal.

        Args:
            target: the requested next state.

        Returns:
            ``self`` for chaining.

        Raises:
            InvalidTransitionError: if the transition is not permitted.

        Examples:
            >>> p = Plan.new("g")
            >>> p.transition_to(PlanState.EXPLORING)
            <Plan object ...>
        """
        if not can_transition(self.state, target):
            raise InvalidTransitionError(self.state, target)
        self.state = target
        return self

    @property
    def is_terminal(self) -> bool:
        """Return ``True`` if the plan is in a terminal state."""
        return self.state in TERMINAL_STATES

    # -- step management ------------------------------------------------------

    def with_step(self, title: str, tool: str, arguments: Optional[dict] = None,
                  detail: str = "") -> "Plan":
        """Append a new :class:`PlanStep` and return ``self``.

        The step list is append-only from the caller's perspective: this returns
        ``self`` after appending, so the caller can chain, but never hand a plan
        its mutable step list to mutate in place.

        Args:
            title: short summary of the step.
            tool: the tool name the step will invoke.
            arguments: the tool arguments.
            detail: optional longer description.

        Returns:
            ``self``.

        Raises:
            ValueError: if the plan is already in a terminal state.
        """
        if self.is_terminal:
            raise ValueError(f"Cannot add steps to a terminal plan ({self.state.value})")
        self.steps.append(
            PlanStep(
                step_id=uuid.uuid4().hex,
                title=title,
                tool=tool,
                arguments=arguments or {},
                detail=detail,
            )
        )
        return self

    def set_steps(self, steps: list[PlanStep]) -> "Plan":
        """Replace the plan's step list wholesale (a fresh draft).

        Use this when submitting a complete draft in one shot, as opposed to
        :meth:`with_step` for incremental building. Resets any per-step status to
        the value carried by the provided steps (typically ``"pending"``).

        Args:
            steps: the new, ordered list of steps.

        Returns:
            ``self``.

        Raises:
            ValueError: if the plan is already in a terminal state.

        Examples:
            >>> p = Plan.new("g")
            >>> p.set_steps([PlanStep("s", "t", "read_file")])
            >>> len(p.steps)
            1
        """
        if self.is_terminal:
            raise ValueError(f"Cannot set steps on a terminal plan ({self.state.value})")
        self.steps = list(steps)
        return self

    def next_pending_index(self) -> Optional[int]:
        """Return the index of the first not-yet-run step, or ``None`` if none.

        A step is "not yet run" when its status is ``"pending"``. This is how the
        executor walks the plan in order.

        Examples:
            >>> p = Plan.new("g")
            >>> p.next_pending_index()
        """
        for i, step in enumerate(self.steps):
            if step.status == "pending":
                return i
        return None

    def add_observation(self, text: str) -> None:
        """Record a read-only exploration result against the plan.

        Observations cap memory: each is truncated to
        :attr:`MAX_OBSERVATION_CHARS` and only the most recent
        :attr:`MAX_OBSERVATIONS` are kept, so a long exploration cannot blow up
        the context budget.

        Args:
            text: the observation text (e.g. a tool's read-only result).

        Examples:
            >>> p = Plan.new("g")
            >>> p.add_observation("auth.py defines login()")
            >>> len(p.observations)
            1
        """
        if not text:
            return
        clipped = text if len(text) <= self.MAX_OBSERVATION_CHARS else (
            text[: self.MAX_OBSERVATION_CHARS] + "..."
        )
        self.observations.append(clipped)
        if len(self.observations) > self.MAX_OBSERVATIONS:
            del self.observations[: len(self.observations) - self.MAX_OBSERVATIONS]

    def mark_step(self, index: int, status: str) -> None:
        """Set the status of the step at ``index``.

        Args:
            index: position of the step in :attr:`steps`.
            status: one of ``"running"``, ``"done"``, ``"failed"``.

        Raises:
            IndexError: if ``index`` is out of range.
            ValueError: if ``status`` is not a recognized step status.
        """
        valid = {"running", "done", "failed"}
        if status not in valid:
            raise ValueError(f"Invalid step status: {status}")
        step = self.steps[index]  # bounds-checked here so IndexError propagates
        self.steps[index] = replace(step, status=status)

    # -- serialization --------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialize the plan to a JSON-safe dict.

        Returns:
            A dict suitable for ``json.dumps`` and HTTP transport.

        Examples:
            >>> d = Plan.new("g").to_dict()
            >>> d["goal"]
            'g'
            >>> "steps" in d
            True
        """
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "state": self.state.value,
            "workspace": self.workspace,
            "rejection_reason": self.rejection_reason,
            "failure_reason": self.failure_reason,
            "observations": list(self.observations),
            "created_at": self.created_at,
            "steps": [
                {
                    "step_id": s.step_id,
                    "title": s.title,
                    "tool": s.tool,
                    "arguments": s.arguments,
                    "detail": s.detail,
                    "status": s.status,
                }
                for s in self.steps
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Plan":
        """Reconstruct a plan from a dict produced by :meth:`to_dict`.

        Args:
            data: the serialized plan dict.

        Returns:
            A :class:`Plan` instance.

        Raises:
            KeyError: if required keys are missing.
        """
        plan = cls(
            plan_id=data["plan_id"],
            goal=data["goal"],
            state=PlanState(data.get("state", PlanState.IDLE.value)),
            workspace=data.get("workspace", ""),
            rejection_reason=data.get("rejection_reason", ""),
            failure_reason=data.get("failure_reason", ""),
            created_at=data.get("created_at", _utcnow()),
        )
        plan.observations = list(data.get("observations", []))
        plan.steps = [
            PlanStep(
                step_id=s["step_id"],
                title=s["title"],
                tool=s["tool"],
                arguments=s.get("arguments", {}),
                detail=s.get("detail", ""),
                status=s.get("status", "pending"),
            )
            for s in data.get("steps", [])
        ]
        return plan
