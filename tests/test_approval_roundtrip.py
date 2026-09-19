"""
tests/test_approval_roundtrip.py - the approval token round-trips through the HTTP
backends and the agent loop (P0 #3, backend half).

Proves: a pending request exposes a token via GET /api/approval; approve/reject by
token (and by the legacy no-token fallback) drive get_approval_decision; and the
separate git-push contract (approved:true) is untouched.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import coderai.tools.tools as tools
import coderai.server.web_app as web_app
import coderai.server.fastapi_app as fastapi_app


@pytest.fixture()
def client(tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    tools.set_workspace(ws)
    tools.clear_approval_state()
    tools.reset_cancel_flag()
    try:
        with TestClient(fastapi_app.app) as c:
            yield c
    finally:
        tools.clear_approval_state()


def _prompt_write_file(path: str = "a.txt", content: str = "x") -> dict:
    out = tools.execute_tool("write_file", {"path": path, "content": content})
    return json.loads(out)


def test_pending_exposes_token_via_api(client, tmp_path):
    _prompt_write_file()
    resp = client.get("/api/approval").json()
    assert resp["pending"] is True
    assert resp["tool_name"] == "write_file"
    assert resp.get("token")


def test_approve_by_token_then_reexecute(client, tmp_path):
    ws = tmp_path / "ws"
    info = _prompt_write_file()
    token = info["token"]

    resp = client.post("/api/approval/approve", json={"token": token})
    assert resp.status_code == 200
    assert tools.get_approval_decision(token)["approved"] is True

    out = tools.execute_tool("write_file", {"path": "a.txt", "content": "x"})
    assert (ws / "a.txt").exists() is True


def test_reject_by_token(client, tmp_path):
    info = _prompt_write_file()
    token = info["token"]

    client.post("/api/approval/reject", json={"token": token, "reason": "no"})
    decision = tools.get_approval_decision(token)
    assert decision["rejected"] is True
    assert decision["rejection_reason"] == "no"


def test_approve_without_token_uses_latest_fallback(client, tmp_path):
    # Legacy clients that don't send a token must still work.
    _prompt_write_file()
    resp = client.post("/api/approval/approve", json={"always_allow_for_session": False})
    assert resp.status_code == 200

    # The most recent pending request was decided.
    ws = tmp_path / "ws"
    out = tools.execute_tool("write_file", {"path": "a.txt", "content": "x"})
    assert (ws / "a.txt").exists() is True


def test_git_approve_endpoint_also_token_aware(client, tmp_path):
    info = _prompt_write_file()
    token = info["token"]
    client.post("/api/git/approve", json={"token": token})
    assert tools.get_approval_decision(token)["approved"] is True


def test_git_push_requires_explicit_approval_flag(client):
    # The git-push path is separate from the tool-approval token model and must
    # still reject when approved:true is not present.
    resp = client.post("/api/git/push", json={"username": "u", "token": "t"})
    assert resp.status_code == 403


def test_poll_loop_uses_token_decision(client, tmp_path):
    # The agent loop resolves by token: a decision for a *different* token must not
    # satisfy this request (no cross-request leak).
    ws = tmp_path / "ws"
    info_a = _prompt_write_file("a.txt", "1")
    token_a = info_a["token"]
    info_b = _prompt_write_file("b.txt", "2")
    token_b = info_b["token"]
    assert token_a != token_b

    # Approve b only. Polling a must still see a pending (waiting) decision.
    client.post("/api/approval/approve", json={"token": token_b})
    assert tools.get_approval_decision(token_a) is None
    assert tools.get_approval_decision(token_b)["approved"] is True
