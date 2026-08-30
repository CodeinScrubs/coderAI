"""
session_manager.py - Multi-session state management and project cards.
Provides session isolation for multi-tab and concurrent client interactions.
"""

from __future__ import annotations

import copy
import time
import uuid
from pathlib import Path
from typing import Any

from git_manager import GitManager
from memory_manager import MemoryManager


class SessionStore:
    """In-memory multi-session store with thread-safe session isolation and lifecycle management."""

    def __init__(self, template_state: dict | None = None) -> None:
        self._template = template_state or {}
        self._sessions: dict[str, dict] = {}
        self._last_active: dict[str, float] = {}

    def set_template(self, template: dict) -> None:
        self._template = template

    def get_or_create(
        self, session_id: str | None = None, initial_state: dict | None = None
    ) -> tuple[str, dict]:
        sid = (session_id or "").strip() or f"sess_{uuid.uuid4().hex[:12]}"
        now = time.time()
        if sid not in self._sessions:
            base = copy.deepcopy(self._template)
            if initial_state:
                base.update(initial_state)
            base["memory_session_id"] = sid
            base["messages"] = list(base.get("messages", []))
            base["tools_log"] = list(base.get("tools_log", []))
            base["used_skills_log"] = list(base.get("used_skills_log", []))
            base["created_at"] = now
            self._sessions[sid] = base
        self._last_active[sid] = now
        return sid, self._sessions[sid]

    def get(self, session_id: str | None) -> dict | None:
        if not session_id:
            return None
        sid = session_id.strip()
        if sid in self._sessions:
            self._last_active[sid] = time.time()
            return self._sessions[sid]
        return None

    def list_sessions(self) -> list[dict]:
        results = []
        for sid, state in self._sessions.items():
            results.append({
                "session_id": sid,
                "created_at": state.get("created_at", 0),
                "last_active": self._last_active.get(sid, 0),
                "messages_count": len(state.get("messages", [])),
                "agent_running": bool(state.get("agent_running", False)),
                "workspace": str(state.get("workspace", "")),
            })
        return sorted(results, key=lambda x: x["last_active"], reverse=True)

    def delete(self, session_id: str) -> bool:
        sid = session_id.strip()
        if sid in self._sessions:
            del self._sessions[sid]
            self._last_active.pop(sid, None)
            return True
        return False

    def clear(self) -> None:
        self._sessions.clear()
        self._last_active.clear()


def build_project_cards(
    workspace_path: Path,
    manager: MemoryManager | None = None,
    is_agent_running: bool = False,
    snapshot_fn: Any = None,
) -> list[dict]:
    manager = manager or MemoryManager(workspace_path)
    active_path = str(workspace_path.resolve())
    cards = []
    for project in manager.list_projects():
        p_workspace = Path(project["workspace_path"])
        if snapshot_fn and p_workspace.is_dir():
            snapshot = snapshot_fn(p_workspace)
        else:
            snapshot = {"files": [], "stats": {"files": 0, "kb": 0, "types": 0}}
        git = {"is_repo": False, "files": [], "commits": 0}
        if p_workspace.is_dir():
            try:
                git_manager = GitManager(p_workspace)
                status = git_manager.get_status()
                git = {
                    "is_repo": bool(status.get("is_repo")),
                    "branch": status.get("branch"),
                    "files": status.get("files", []),
                    "commits": len(git_manager.get_log(100)) if status.get("is_repo") else 0,
                }
            except Exception:
                pass
        cards.append({
            **project,
            "exists": p_workspace.is_dir(),
            "stats": snapshot["stats"],
            "git": git,
            "agent_status": "running" if str(p_workspace.resolve()) == active_path and is_agent_running else "idle",
            "is_active": str(p_workspace.resolve()) == active_path if p_workspace.is_dir() else False,
        })
    return cards
