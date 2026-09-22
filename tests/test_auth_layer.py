"""tests/test_auth_layer.py - the access-token boundary.

The server previously relied solely on the default 127.0.0.1 bind. This adds an
independent token gate: loopback (and test) clients are trusted, any other client
must present the token (Authorization header or ?token=), else 401. Tests here:
  * check_auth unit behavior (trusted vs. remote, header vs. query),
  * the FastAPI /api/* HTTP middleware (401 without token, pass with token),
  * /api/auth/status (never leaks the token),
  * the WebSocket boundary (close before accept when unauthenticated).
"""

from __future__ import annotations

import pytest

import coderai.server.web_app as web_app


# ── check_auth (pure) ────────────────────────────────────────────────────────

def test_loopback_is_trusted():
    assert web_app.check_auth("127.0.0.1", {}, {}) is True
    assert web_app.check_auth("::1", {}, {}) is True
    assert web_app.check_auth("localhost", {}, {}) is True


def test_testclient_is_trusted(monkeypatch):
    # Starlette's TestClient reports host "testclient"; it must stay trusted so
    # the ~30 existing fastapi tests keep working without a token.
    assert web_app._is_trusted_client("testclient") is True
    assert web_app.check_auth("testclient", {}, {}) is True


def test_remote_needs_token(monkeypatch):
    monkeypatch.setattr(web_app, "_auth_token", "sekrit")
    host = "10.0.0.5"
    # no token -> refused
    assert web_app.check_auth(host, {}, {}) is False
    # wrong token -> refused
    assert web_app.check_auth(host, {"Authorization": "Bearer nope"}, {}) is False
    # bearer header -> accepted
    assert web_app.check_auth(host, {"Authorization": "Bearer sekrit"}, {}) is True
    # raw header -> accepted
    assert web_app.check_auth(host, {"Authorization": "sekrit"}, {}) is True
    # query param -> accepted
    assert web_app.check_auth(host, {}, {"token": "sekrit"}) is True
    # query param as list (parse_qs shape) -> accepted
    assert web_app.check_auth(host, {}, {"token": ["sekrit"]}) is True


# ── FastAPI /api/* HTTP middleware ───────────────────────────────────────────

@pytest.fixture
def remote_client(monkeypatch):
    """A FastAPI TestClient where every /api/ client is treated as REMOTE.

    _is_trusted_client is forced False so the token gate engages (TestClient's
    real host, "testclient", is otherwise trusted). A fixed token is installed
    so the expected value is known and no token is printed.
    """
    monkeypatch.setattr(web_app, "_auth_token", "sekrit")
    monkeypatch.setattr(web_app, "_is_trusted_client", lambda host: False)

    from fastapi.testclient import TestClient
    from coderai.server.fastapi_app import create_app

    return TestClient(create_app())


def test_http_api_remote_refused_without_token(remote_client):
    r = remote_client.get("/api/state")
    assert r.status_code == 401
    assert "WWW-Authenticate" in r.headers
    assert r.json().get("error") == "unauthorized"


def test_http_api_remote_allowed_with_bearer(remote_client):
    r = remote_client.get("/api/state", headers={"Authorization": "Bearer sekrit"})
    assert r.status_code == 200


def test_http_api_remote_allowed_with_query(remote_client):
    r = remote_client.get("/api/state?token=sekrit")
    assert r.status_code == 200


def test_http_api_post_remote_refused_without_token(remote_client):
    r = remote_client.post("/api/clear")
    assert r.status_code == 401


def test_auth_status_does_not_leak_token(remote_client):
    r = remote_client.get("/api/auth/status", headers={"Authorization": "Bearer sekrit"})
    assert r.status_code == 200
    body = r.text
    assert "sekrit" not in body  # the token itself is never returned
    assert r.json()["auth_enabled"] is True


# ── WebSocket boundary ───────────────────────────────────────────────────────

def test_ws_chat_remote_refused_without_token(monkeypatch):
    monkeypatch.setattr(web_app, "_auth_token", "sekrit")
    monkeypatch.setattr(web_app, "_is_trusted_client", lambda host: False)
    from fastapi.testclient import TestClient
    from coderai.server.fastapi_app import create_app

    client = TestClient(create_app())
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/chat?session_id=t"):
            pass  # reaching here would mean the socket was (wrongly) accepted
