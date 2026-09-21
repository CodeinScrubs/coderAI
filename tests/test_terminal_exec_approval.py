"""
tests/test_terminal_exec_approval.py - /api/terminal/exec is guarded.

This REST endpoint runs an arbitrary command on a live PTY and had no auth or
approval — only the default 127.0.0.1 bind protected it (and it is exposed on
both web_app and fastapi_app; the latter is the default live server). Now it:
  * refuses non-loopback clients by default (WEB_APP_LOOPBACK_ONLY), and
  * routes through the run_bash approval policy (destructive = hard block,
    anything else = single-use approval token).
The interactive browser terminal uses the WebSocket path (/api/terminal/ws),
which is guarded at the same loopback boundary (per-keystroke approval on a
live PTY is impractical, so the network boundary is the guard).
"""

import pytest

import coderai.server.web_app as web_app
from coderai.server.fastapi_app import create_app


@pytest.fixture
def client(monkeypatch):
    # Loopback guard off by default in these tests (individual tests re-enable
    # it); approval state reset between tests.
    monkeypatch.setattr(web_app, "_LOOPBACK_ONLY", False)
    web_app.clear_approval_state()
    app = create_app()
    from fastapi.testclient import TestClient
    return TestClient(app)


# ── loopback guard (pure helpers) ────────────────────────────────────────────

def test_loopback_detection():
    assert web_app._is_loopback_client("127.0.0.1") is True
    assert web_app._is_loopback_client("::1") is True
    assert web_app._is_loopback_client("localhost") is True
    assert web_app._is_loopback_client("192.168.1.5") is False
    assert web_app._is_loopback_client("10.0.0.1") is False


# ── loopback guard (endpoint) ────────────────────────────────────────────────

def test_exec_refuses_non_loopback(client, monkeypatch):
    monkeypatch.setattr(web_app, "_terminal_exec_allowed", lambda host: False)
    r = client.post("/api/terminal/exec", json={"command": "echo hi"})
    assert r.status_code == 403
    assert r.json().get("status") == "forbidden"


def test_ws_refuses_non_loopback(client, monkeypatch):
    # The interactive terminal WebSocket carries a live PTY. A non-loopback
    # client must be refused at the boundary (closed before it is accepted),
    # so no shell is ever spawned for a remote socket.
    monkeypatch.setattr(web_app, "_terminal_exec_allowed", lambda host: False)
    with pytest.raises(Exception):
        with client.websocket_connect("/api/terminal/ws?session_id=t"):
            pass  # reaching here would mean the socket was (wrongly) accepted


# ── destructive hard block ───────────────────────────────────────────────────

def test_exec_dangerous_is_blocked(client):
    r = client.post("/api/terminal/exec", json={"command": "rm -rf /"})
    assert r.status_code == 403
    assert r.json().get("status") == "blocked"


# ── approval gate ────────────────────────────────────────────────────────────

def test_exec_benign_requires_approval(client):
    r = client.post("/api/terminal/exec", json={"command": "echo hello"})
    assert r.status_code == 202
    data = r.json()
    assert data.get("status") == "approval_required"
    assert data.get("token")
    assert data.get("tool_name") == "run_bash"


def test_exec_allowed_after_approval(client, monkeypatch):
    # Fake session so no real shell is spawned when the command is approved.
    class _FakeSession:
        cwd = "."
        def __init__(self):
            self.written = None
        def is_running(self):
            return True
        def write_stdin(self, text):
            self.written = text
    fake = _FakeSession()
    monkeypatch.setattr(web_app.terminal_manager, "get_or_create_session",
                        lambda *a, **k: fake)

    from coderai.tools.tools import resolve_approval

    r1 = client.post("/api/terminal/exec", json={"command": "echo marked"})
    assert r1.json().get("status") == "approval_required"
    token = r1.json()["token"]

    # Not yet approved -> command not written.
    assert fake.written is None

    resolve_approval(token, True)
    r2 = client.post("/api/terminal/exec", json={"command": "echo marked"})
    assert r2.status_code == 200
    assert r2.json().get("ok") is True
    assert fake.written == "echo marked"
