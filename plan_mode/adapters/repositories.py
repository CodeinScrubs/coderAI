"""Plan repositories: in-memory and JSON-on-disk.

Both implement :class:`~plan_mode.application.ports.PlanRepository`.

* :class:`MemoryPlanRepository` — process-local, thread-safe. Used for tests and
  as the default when no persistence directory is configured.
* :class:`JsonPlanRepository` — one JSON file per plan under a directory, so
  plans survive a restart. File names are sanitized to the plan id, and plan ids
  are validated to prevent path traversal.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Optional

from plan_mode.application.ports import PlanRepository
from plan_mode.domain.entities import Plan

# A plan id is a 32-char lowercase hex string (uuid4().hex). We accept a slightly
# looser charset but reject anything that could escape the directory.
_PLAN_ID_RE = re.compile(r"^[0-9a-f]{8,64}$")


class MemoryPlanRepository(PlanRepository):
    """A thread-safe, in-memory plan store.

    Attributes:
        lock: guards the underlying dict so concurrent save/get/list are safe.

    Examples:
        >>> repo = MemoryPlanRepository()
        >>> repo.list()
        []
    """

    def __init__(self) -> None:
        self._plans: dict[str, Plan] = {}
        self._lock = threading.Lock()

    def save(self, plan: Plan) -> None:
        """Store ``plan`` keyed by its id (create or update).

        Args:
            plan: the plan to store.
        """
        with self._lock:
            self._plans[plan.plan_id] = plan

    def get(self, plan_id: str) -> Optional[Plan]:
        """Return the plan with ``plan_id`` or ``None``.

        Args:
            plan_id: the plan identifier.

        Returns:
            The plan, or ``None``.
        """
        with self._lock:
            return self._plans.get(plan_id)

    def list(self) -> list[Plan]:
        """Return a snapshot of all stored plans.

        Returns:
            A list of plans (order is arbitrary).
        """
        with self._lock:
            return list(self._plans.values())


class JsonPlanRepository(PlanRepository):
    """Persist one plan per JSON file under ``directory``.

    Attributes:
        directory: the folder that holds the plan JSON files. Created on demand.

    Notes:
        Plan ids are validated against :data:`_PLAN_ID_RE` before being used as
        a file name, so a malformed or malicious id cannot escape the directory.
    """

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # -- helpers --------------------------------------------------------------

    def _path_for(self, plan_id: str) -> Optional[Path]:
        """Resolve a plan id to a safe file path, or ``None`` if the id is unsafe.

        Args:
            plan_id: the candidate id.

        Returns:
            A :class:`Path` inside :attr:`directory`, or ``None`` if the id is
            not a valid plan id (path-traversal defense).
        """
        if not _PLAN_ID_RE.match(plan_id or ""):
            return None
        candidate = (self.directory / f"{plan_id}.json").resolve()
        try:
            candidate.relative_to(self.directory.resolve())
        except ValueError:
            return None
        return candidate

    # -- PlanRepository -------------------------------------------------------

    def save(self, plan: Plan) -> None:
        """Serialize and write ``plan`` to its JSON file.

        Args:
            plan: the plan to persist.

        Raises:
            ValueError: if the plan id is not safe to use as a file name.
        """
        path = self._path_for(plan.plan_id)
        if path is None:
            raise ValueError(f"Unsafe plan id for storage: {plan.plan_id!r}")
        with self._lock:
            path.write_text(
                json.dumps(plan.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def get(self, plan_id: str) -> Optional[Plan]:
        """Load the plan with ``plan_id`` from disk, or ``None`` if absent/unsafe.

        Args:
            plan_id: the plan identifier.

        Returns:
            The plan, or ``None``.
        """
        path = self._path_for(plan_id)
        if path is None or not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return Plan.from_dict(data)

    def list(self) -> list[Plan]:
        """Load every plan file in the directory.

        Returns:
            A list of plans (order is arbitrary).
        """
        plans: list[Plan] = []
        for file in self.directory.glob("*.json"):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            plans.append(Plan.from_dict(data))
        return plans
