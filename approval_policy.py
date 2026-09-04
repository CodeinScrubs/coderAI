"""
approval_policy.py - Granular Per-Tool and Per-Workspace Security Approval Policies.

Provides:
- Default global policy for tools requiring user confirmation.
- Workspace-level policy inheritance and customization.
- Dangerous shell command heuristics detection.
- Persistence in global settings and local project configuration (.agent_memory/workspace_policy.json).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

DEFAULT_GLOBAL_POLICY: dict[str, str] = {
    "write_file": "always",        # "always" (diff preview) | "auto"
    "replace_in_file": "always",    # "always" (diff preview) | "auto"
    "run_bash": "dangerous_only",  # "always" | "dangerous_only" | "auto"
    "run_python": "always",        # "always" | "auto"
    "git_push": "always",          # "always" | "auto"
    "git_revert": "always",        # "always" | "auto"
}

DANGEROUS_BASH_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\brm\s+(-[a-zA-Z]*[rf][a-zA-Z]*|--recursive|--force)\b", re.IGNORECASE), "Recursive or forced file deletion (rm -rf)"),
    (re.compile(r"\b(del|erase)\s+/[fFqQsS]", re.IGNORECASE), "Forced or quiet recursive file deletion (del /f /s /q)"),
    (re.compile(r"\brmdir\s+/[sS]", re.IGNORECASE), "Recursive directory deletion (rmdir /s)"),
    (re.compile(r"\b(mkfs|format\s+[a-zA-Z]:)", re.IGNORECASE), "Disk formatting filesystem command"),
    (re.compile(r"\bdd\s+if=", re.IGNORECASE), "Raw disk or block device write (dd)"),
    (re.compile(r"\b(fdisk|parted|diskpart)\b", re.IGNORECASE), "Disk partitioning utility"),
    (re.compile(r"\b(shutdown|reboot|poweroff|init\s+0)\b", re.IGNORECASE), "System reboot or shutdown command"),
    (re.compile(r"\b(sudo|su\s+-)\b", re.IGNORECASE), "Elevated privilege execution (sudo/su)"),
    (re.compile(r"(curl|wget)\s+[^|]+\|\s*(bash|sh|zsh|powershell|pwsh|cmd)", re.IGNORECASE), "Direct execution of remote script piped to shell"),
    (re.compile(r":\(\)\s*\{\s*:\|:&\s*\};:", re.IGNORECASE), "Fork bomb denial of service pattern"),
    (re.compile(r">\s*(/etc/|/boot/|C:\\\\Windows|/dev/sd)", re.IGNORECASE), "Overwriting critical system directories or block devices"),
]


def is_dangerous_bash(command: str) -> tuple[bool, str]:
    """Check if a bash/shell command matches known destructive or high-risk patterns."""
    if not command:
        return False, ""
    cleaned = command.strip()
    for pattern, description in DANGEROUS_BASH_PATTERNS:
        if pattern.search(cleaned):
            return True, description
    return False, ""


class ApprovalPolicyManager:
    """Manages global and per-workspace approval policies."""

    def __init__(self, global_settings_path: Path | str | None = None) -> None:
        if global_settings_path:
            self.global_settings_path = Path(global_settings_path)
        else:
            self.global_settings_path = Path("coderai_data/settings.json")

    def get_global_policy(self) -> dict[str, str]:
        """Load global approval policy from settings, falling back to defaults."""
        if not self.global_settings_path.exists():
            return dict(DEFAULT_GLOBAL_POLICY)
        try:
            data = json.loads(self.global_settings_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "approval_policy" in data:
                saved = data["approval_policy"]
                if isinstance(saved, dict):
                    policy = dict(DEFAULT_GLOBAL_POLICY)
                    policy.update(saved)
                    return policy
        except Exception:
            pass
        return dict(DEFAULT_GLOBAL_POLICY)

    def save_global_policy(self, policy: dict[str, str]) -> dict[str, str]:
        """Save global approval policy into settings file."""
        current = {}
        if self.global_settings_path.exists():
            try:
                data = json.loads(self.global_settings_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    current = data
            except Exception:
                current = {}

        merged = dict(DEFAULT_GLOBAL_POLICY)
        merged.update(policy)
        current["approval_policy"] = merged
        self.global_settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.global_settings_path.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
        return merged

    def _get_workspace_policy_file(self, workspace_path: str | Path) -> Path | None:
        if not workspace_path:
            return None
        p = Path(workspace_path)
        if not p.exists() or not p.is_dir():
            return None
        return p / ".agent_memory" / "workspace_policy.json"

    def get_workspace_policy(self, workspace_path: str | Path) -> dict[str, Any]:
        """Get workspace policy file content or default inherit mode."""
        policy_file = self._get_workspace_policy_file(workspace_path)
        if policy_file and policy_file.exists():
            try:
                data = json.loads(policy_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return {
                        "mode": data.get("mode", "inherit"),  # "inherit" or "custom"
                        "policy": data.get("policy", {}),
                    }
            except Exception:
                pass
        return {"mode": "inherit", "policy": {}}

    def save_workspace_policy(
        self,
        workspace_path: str | Path,
        mode: str,
        policy: dict[str, str],
    ) -> dict[str, Any]:
        """Save customized approval policy for a specific workspace."""
        policy_file = self._get_workspace_policy_file(workspace_path)
        if not policy_file:
            raise ValueError(f"Invalid workspace path: {workspace_path}")

        policy_file.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "mode": mode if mode in {"custom", "inherit"} else "custom",
            "policy": policy if isinstance(policy, dict) else {},
        }
        policy_file.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        return record

    def reset_workspace_policy(self, workspace_path: str | Path) -> dict[str, Any]:
        """Reset workspace policy to inherit global defaults."""
        return self.save_workspace_policy(workspace_path, mode="inherit", policy={})


    def get_effective_policy(self, workspace_path: str | Path = "") -> dict[str, str]:
        """Resolve effective policy: workspace custom settings or fallback to global."""
        global_policy = self.get_global_policy()
        if not workspace_path:
            return global_policy

        ws = self.get_workspace_policy(workspace_path)
        if ws.get("mode") == "custom" and isinstance(ws.get("policy"), dict):
            effective = dict(global_policy)
            effective.update(ws["policy"])
            return effective

        return global_policy


    def should_require_approval(
        self,
        tool_name: str,
        arguments: dict | None = None,
        workspace_path: str | Path = "",
    ) -> tuple[bool, str, str]:
        """
        Determine whether tool execution requires user approval based on active policy.

        Returns:
            (requires_approval: bool, reason: str, preview_type: str)
            preview_type can be "diff", "command", "code", or "generic".
        """
        arguments = arguments or {}
        policy = self.get_effective_policy(workspace_path)
        rule = policy.get(tool_name, "always")

        # 1. File modification tools
        if tool_name in {"write_file", "replace_in_file"}:
            if rule == "auto":
                return False, "", "diff"
            return True, f"Policy requires review for {tool_name}", "diff"

        # 2. Bash / Terminal commands
        if tool_name in {"run_bash", "run_terminal_command"}:
            cmd = arguments.get("command") or arguments.get("cmd") or ""
            if rule == "auto":
                return False, "", "command"
            if rule == "dangerous_only":
                is_danger, danger_desc = is_dangerous_bash(cmd)
                if is_danger:
                    return True, f"High-risk command detected: {danger_desc}", "command"
                return False, "", "command"
            return True, f"Policy requires review for {tool_name}", "command"

        # 3. Python code execution
        if tool_name == "run_python":
            if rule == "auto":
                return False, "", "code"
            return True, "Policy requires review for Python script execution", "code"

        # 4. Git mutation tools
        if tool_name in {"git_push", "git_revert"}:
            if rule == "auto":
                return False, "", "generic"
            return True, f"Policy requires review for Git operation '{tool_name}'", "generic"

        # Safe read-only or informational tools do not require approval
        return False, "", "generic"


policy_manager = ApprovalPolicyManager()
