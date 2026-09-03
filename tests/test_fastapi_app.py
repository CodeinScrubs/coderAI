import json
import pytest
from fastapi.testclient import TestClient

from fastapi_app import create_app
import web_app


def test_fastapi_app_state_and_cancel():
    app = create_app()
    client = TestClient(app)

    # Test GET /api/state
    resp = client.get("/api/state")
    assert resp.status_code == 200
    data = resp.json()
    assert "messages" in data
    assert "workspace" in data

    # Test POST /api/cancel
    resp = client.post("/api/cancel")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert data.get("cancelled") is True


def test_fastapi_endpoints():
    app = create_app()
    client = TestClient(app)

    resp = client.get("/api/projects")
    assert resp.status_code == 200
    assert "projects" in resp.json()

    resp = client.get("/api/index/graph")
    assert resp.status_code == 200
    assert "nodes" in resp.json()
    assert "edges" in resp.json()

    resp = client.post("/api/settings", json={"temperature": 0.65})
    assert resp.status_code == 200
    data = resp.json()
    settings = data.get("settings", {})
    assert settings.get("temperature") == 0.65 or web_app.STATE.get("temperature") == 0.65


def test_fastapi_websocket_ping_and_cancel():
    app = create_app()
    client = TestClient(app)

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_text(json.dumps({"type": "ping"}))
        data = json.loads(websocket.receive_text())
        assert data.get("type") == "pong"

        websocket.send_text(json.dumps({"type": "cancel"}))
        data = json.loads(websocket.receive_text())
        assert data.get("type") == "cancelled"


def test_fastapi_embedding_status_and_dismiss():
    app = create_app()
    client = TestClient(app)

    resp = client.get("/api/ollama/embedding-status")
    assert resp.status_code == 200
    data = resp.json()
    assert "installed" in data
    assert data.get("target_model") == "embeddinggemma"

    resp = client.post("/api/ollama/dismiss-embedding")
    assert resp.status_code == 200
    assert resp.json().get("ok") is True

    resp = client.get("/api/ollama/embedding-status")
    assert resp.json().get("dismissed") is True

