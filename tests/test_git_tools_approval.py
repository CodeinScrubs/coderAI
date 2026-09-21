"""
tests/test_git_tools_approval.py - git_commit and git_checkout are gated.

git_checkout can discard uncommitted work and git_commit mutates history;
neither asked for approval before. Both now sit behind the same policy branch
as git_push / git_revert (default rule "always").
"""

import json
import os
import subprocess

import coderai.tools.tools as tools
from coderai.tools.tools import (
    clear_approval_state,
    execute_tool,
    resolve_approval,
    set_workspace,
)
from coderai.utils.approval_policy import DEFAULT_GLOBAL_POLICY


def _approval_payload(out) -> dict:
    try:
        data = json.loads(out)
    except (json.JSONDecodeError, TypeError):
        return {"status": "not-approval-required", "raw": out}
    if isinstance(data, dict) and data.get("status") == "approval_required":
        return data
    return {"status": "not-approval-required", "raw": out}


def _fresh_git_ws(tmp_path):
    """A disposable git repo with one committed file, set as the workspace."""
    ws = tmp_path / "gitws"
    ws.mkdir()
    set_workspace(ws)
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
    }
    def g(*args):
        subprocess.run(["git", *args], cwd=ws, check=True, capture_output=True,
                       env={**os.environ, **env})
    g("init", "-q")
    (ws / "a.txt").write_text("hello\n", encoding="utf-8")
    g("add", "a.txt")
    g("commit", "-q", "-m", "initial")
    clear_approval_state()
    tools.reset_cancel_flag()
    return ws


def test_git_commit_in_default_policy():
    assert DEFAULT_GLOBAL_POLICY.get("git_commit") == "always"
    assert DEFAULT_GLOBAL_POLICY.get("git_checkout") == "always"


def test_git_commit_requires_approval(tmp_path):
    ws = _fresh_git_ws(tmp_path)
    (ws / "b.txt").write_text("b\n", encoding="utf-8")  # something to commit
    payload = _approval_payload(execute_tool("git_commit", {"message": "m"}))
    assert payload["status"] == "approval_required", f"git_commit not gated: {payload}"
    assert payload["tool_name"] == "git_commit"
    assert payload.get("token")


def test_git_checkout_requires_approval(tmp_path):
    _fresh_git_ws(tmp_path)
    payload = _approval_payload(execute_tool("git_checkout", {"branch": "feature-x", "create": True}))
    assert payload["status"] == "approval_required", f"git_checkout not gated: {payload}"
    assert payload["tool_name"] == "git_checkout"
    assert payload.get("token")


def test_git_commit_does_not_commit_without_approval(tmp_path):
    ws = _fresh_git_ws(tmp_path)
    (ws / "b.txt").write_text("b\n", encoding="utf-8")
    payload = _approval_payload(execute_tool("git_commit", {"message": "add b", "files": ["b.txt"]}))
    assert payload["status"] == "approval_required"
    # Nothing committed: b.txt is still untracked.
    status = subprocess.run(["git", "status", "--porcelain"], cwd=ws, capture_output=True, text=True).stdout
    assert "b.txt" in status
    assert "?? " in status


def test_git_commit_executes_after_approval(tmp_path):
    ws = _fresh_git_ws(tmp_path)
    (ws / "b.txt").write_text("b\n", encoding="utf-8")
    args = {"message": "add b", "files": ["b.txt"]}
    payload = _approval_payload(execute_tool("git_commit", args))
    assert payload["status"] == "approval_required"
    resolve_approval(payload["token"], True)
    out = execute_tool("git_commit", args)  # same args -> same token -> approved
    assert "approval_required" not in out
    assert "Committed successfully" in out
    log = subprocess.run(["git", "log", "--oneline", "-1"], cwd=ws, capture_output=True, text=True).stdout
    assert "add b" in log


def test_git_checkout_executes_after_approval(tmp_path):
    ws = _fresh_git_ws(tmp_path)
    args = {"branch": "feature-x", "create": True}
    payload = _approval_payload(execute_tool("git_checkout", args))
    assert payload["status"] == "approval_required"
    resolve_approval(payload["token"], True)
    out = execute_tool("git_checkout", args)
    assert "approval_required" not in out
    current = subprocess.run(["git", "branch", "--show-current"], cwd=ws, capture_output=True, text=True).stdout.strip()
    assert current == "feature-x"
