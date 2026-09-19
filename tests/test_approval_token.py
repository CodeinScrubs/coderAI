"""
tests/test_approval_token.py - TDD spec for the per-request approval token model (P0 #3).

The legacy approval state was a single module-global dict keyed by tool *name* only, so one
approval authorized any later call of that tool and "always allow" leaked across all tools.
These tests pin the replacement: a deterministic per-request token (hash of tool + arguments),
a token-scoped decision, per-tool session allow, single-use tokens, and the flat
get_approval_state() shape (now a superset that also carries `token`).
"""

import json
from pathlib import Path

import coderai.tools.tools as tools
from coderai.tools.tools import (
    _compute_approval_token,
    allow_tool_for_session,
    clear_approval_state,
    execute_tool,
    get_approval_decision,
    get_approval_state,
    resolve_approval,
)


def _fresh_ws(tmp_path: Path, name: str = "ws") -> Path:
    ws = tmp_path / name
    ws.mkdir(parents=True, exist_ok=True)
    tools.set_workspace(ws)
    clear_approval_state()
    tools.reset_cancel_flag()
    return ws


def test_token_is_deterministic_arg_and_tool_sensitive() -> None:
    a = _compute_approval_token("write_file", {"path": "a.txt", "content": "x"})
    b = _compute_approval_token("write_file", {"content": "x", "path": "a.txt"})  # key order differs
    c = _compute_approval_token("write_file", {"path": "b.txt", "content": "x"})  # different arg
    d = _compute_approval_token("append_file", {"path": "a.txt", "content": "x"})  # different tool
    assert a == b  # argument key order is irrelevant
    assert a != c  # arguments matter
    assert a != d  # tool name matters


def test_write_file_requires_approval_and_returns_token(tmp_path: Path) -> None:
    ws = _fresh_ws(tmp_path)
    out = execute_tool("write_file", {"path": "a.txt", "content": "hello"})

    assert (ws / "a.txt").exists() is False  # not written until approved
    info = json.loads(out)
    assert info["status"] == "approval_required"
    assert info["tool_name"] == "write_file"
    assert info["arguments"] == {"path": "a.txt", "content": "hello"}
    assert info.get("token")

    token = info["token"]
    assert get_approval_decision(token) is None  # still waiting
    state = get_approval_state()
    assert state["pending"] is True
    assert state["tool_name"] == "write_file"
    assert state["token"] == token


def test_approve_then_reexecute_runs_and_writes(tmp_path: Path) -> None:
    ws = _fresh_ws(tmp_path)
    args = {"path": "a.txt", "content": "hello"}
    info = json.loads(execute_tool("write_file", args))
    token = info["token"]

    assert resolve_approval(token, True) is True
    assert get_approval_decision(token) == {
        "approved": True,
        "rejected": False,
        "rejection_reason": "",
        "always_allow": False,
    }

    out = execute_tool("write_file", args)  # identical args -> same token -> approved
    assert "approval_required" not in out
    assert (ws / "a.txt").exists() is True
    assert (ws / "a.txt").read_text(encoding="utf-8") == "hello"


def test_reject_sets_rejection_decision(tmp_path: Path) -> None:
    ws = _fresh_ws(tmp_path)
    args = {"path": "a.txt", "content": "hello"}
    info = json.loads(execute_tool("write_file", args))
    token = info["token"]

    assert resolve_approval(token, False, reason="nope") is True
    decision = get_approval_decision(token)
    assert decision is not None
    assert decision["rejected"] is True
    assert decision["approved"] is False
    assert decision["rejection_reason"] == "nope"


def test_resolve_unknown_token_returns_false(tmp_path: Path) -> None:
    _fresh_ws(tmp_path)
    assert resolve_approval("does-not-exist", True) is False


def test_session_allow_is_per_tool(tmp_path: Path) -> None:
    ws = _fresh_ws(tmp_path)
    allow_tool_for_session("write_file")

    out = execute_tool("write_file", {"path": "a.txt", "content": "x"})
    assert (ws / "a.txt").exists() is True  # write_file allowed -> runs without prompt

    # run_python is NOT in the allow set -> still prompts (no cross-tool leak)
    py = json.loads(execute_tool("run_python", {"code": "print(1)"}))
    assert py["status"] == "approval_required"
    assert py["tool_name"] == "run_python"


def test_always_allow_on_approve_scopes_to_that_tool(tmp_path: Path) -> None:
    ws = _fresh_ws(tmp_path)
    args = {"path": "a.txt", "content": "x"}
    info = json.loads(execute_tool("write_file", args))
    token = info["token"]

    # Approve with "always allow" -> only write_file is session-allowed.
    resolve_approval(token, True, always_allow=True)

    # The approved call executes, and a *new* write_file (different args) no longer prompts.
    assert execute_tool("write_file", {"path": "b.txt", "content": "y"}) != "approval_required"
    assert (ws / "b.txt").exists() is True

    # But run_python must still prompt: "always allow" is per-tool, not global.
    py = json.loads(execute_tool("run_python", {"code": "print(1)"}))
    assert py["status"] == "approval_required"


def test_token_is_single_use_and_replay_blocked(tmp_path: Path) -> None:
    ws = _fresh_ws(tmp_path)
    args = {"path": "a.txt", "content": "x"}
    info = json.loads(execute_tool("write_file", args))
    token = info["token"]

    resolve_approval(token, True)
    execute_tool("write_file", args)  # consumes the granted token

    # A third call with the same arguments must prompt again (token was single-use).
    out3 = json.loads(execute_tool("write_file", args))
    assert out3["status"] == "approval_required"
    assert out3["token"] == token


def test_get_approval_state_shape_is_superset_with_token(tmp_path: Path) -> None:
    _fresh_ws(tmp_path)
    empty = get_approval_state()
    for key in (
        "pending", "token", "tool_name", "arguments", "preview",
        "approved", "rejected", "rejection_reason", "always_allow",
    ):
        assert key in empty, f"missing key {key}"
    assert empty["pending"] is False
    assert empty["token"] == ""


def test_clear_approval_state_resets_records_and_session_allow(tmp_path: Path) -> None:
    ws = _fresh_ws(tmp_path)
    info = json.loads(execute_tool("write_file", {"path": "a.txt", "content": "x"}))
    token = info["token"]
    allow_tool_for_session("run_python")

    clear_approval_state()

    assert get_approval_state()["pending"] is False
    assert get_approval_decision(token) is None
    # session allow is cleared too -> write_file prompts again
    out = json.loads(execute_tool("write_file", {"path": "a.txt", "content": "x"}))
    assert out["status"] == "approval_required"
