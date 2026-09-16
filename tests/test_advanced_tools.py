"""
tests/test_advanced_tools.py - TDD spec for gating the advanced shell tools (P0 #1).

These tools used to run model-controlled strings via ``shell=True`` with no approval.
After the fix every one of them is gated behind the per-request approval token, the
fixed-binary ones (kubectl/terraform/npm/docker) no longer go through a shell, and
"always allow" for one tool must not leak into another.
"""

import json
from pathlib import Path

import pytest

import tools
from approval_policy import DEFAULT_GLOBAL_POLICY
from tools import (
    allow_tool_for_session,
    clear_approval_state,
    execute_tool,
    set_workspace,
)

SHELL_TOOLS = [
    "run_linter", "run_tests", "run_kubectl", "run_terraform",
    "run_npm_script", "run_docker_container", "get_container_logs",
]

SHELL_TOOL_ARGS = {
    "run_linter": {"command": "flake8 ."},
    "run_tests": {"command": "pytest"},
    "run_kubectl": {"command": "get pods"},
    "run_terraform": {"command": "plan"},
    "run_npm_script": {"script_name": "test"},
    "run_docker_container": {"image": "alpine", "command": "echo hi"},
    "get_container_logs": {"container_name_or_id": "web"},
}


def _fresh_ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    set_workspace(ws)
    clear_approval_state()
    tools.reset_cancel_flag()
    return ws


def _approval_payload(tool: str, args: dict) -> dict:
    out = execute_tool(tool, args)
    if isinstance(out, str):
        try:
            data = json.loads(out)
            if data.get("status") == "approval_required":
                return data
        except (json.JSONDecodeError, TypeError):
            pass
    return {"status": "not-approval-required", "raw": out}


@pytest.mark.parametrize("tool", SHELL_TOOLS)
def test_shell_tool_requires_approval(tmp_path, tool):
    _fresh_ws(tmp_path)
    payload = _approval_payload(tool, SHELL_TOOL_ARGS[tool])
    assert payload["status"] == "approval_required", f"{tool} was not gated: {payload}"
    assert payload["tool_name"] == tool
    assert payload.get("token")


def test_shell_tools_are_in_default_policy():
    for tool in SHELL_TOOLS:
        assert DEFAULT_GLOBAL_POLICY.get(tool) == "always", f"{tool} missing from policy"


def test_run_linter_runs_when_allowed(tmp_path):
    _fresh_ws(tmp_path)
    allow_tool_for_session("run_linter")
    out = execute_tool("run_linter", {"command": "echo lint-ok"})
    assert "exit code" in out
    assert "lint-ok" in out


def test_run_tests_runs_when_allowed(tmp_path):
    _fresh_ws(tmp_path)
    allow_tool_for_session("run_tests")
    out = execute_tool("run_tests", {"command": "echo tests-ok"})
    assert "exit code" in out
    assert "tests-ok" in out


def test_kubectl_injection_is_gated_before_execution(tmp_path):
    # A shell-injection payload must be stopped at the approval gate, not executed.
    _fresh_ws(tmp_path)
    payload = _approval_payload("run_kubectl", {"command": "get pods; echo pwned"})
    assert payload["status"] == "approval_required"


def test_always_allow_is_scoped_per_tool(tmp_path):
    _fresh_ws(tmp_path)
    allow_tool_for_session("run_tests")
    # run_kubectl is NOT covered by the run_tests allow-list -> still prompts.
    payload = _approval_payload("run_kubectl", {"command": "get pods"})
    assert payload["status"] == "approval_required"


def test_docker_tools_are_gated(tmp_path):
    _fresh_ws(tmp_path)
    assert _approval_payload("run_docker_container", SHELL_TOOL_ARGS["run_docker_container"])["status"] == "approval_required"
    assert _approval_payload("get_container_logs", SHELL_TOOL_ARGS["get_container_logs"])["status"] == "approval_required"
