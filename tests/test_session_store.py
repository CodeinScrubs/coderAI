import pytest
from session_manager import SessionStore
import web_app


def test_session_store_creation_and_isolation():
    template = {"conn_mode": "local", "messages": [], "tools_log": []}
    store = SessionStore(template_state=template)

    sid_a, sess_a = store.get_or_create("session_alpha")
    sid_b, sess_b = store.get_or_create("session_beta")

    assert sid_a == "session_alpha"
    assert sid_b == "session_beta"

    # Mutating session A should not affect session B
    sess_a["messages"].append({"role": "user", "content": "Hello from A"})
    assert len(sess_a["messages"]) == 1
    assert len(sess_b["messages"]) == 0

    sess_b["messages"].append({"role": "user", "content": "Hello from B"})
    sess_b["messages"].append({"role": "assistant", "content": "Response B"})
    assert len(sess_b["messages"]) == 2
    assert len(sess_a["messages"]) == 1


def test_session_store_listing_and_deletion():
    store = SessionStore({"workspace": "ws1"})
    store.get_or_create("sess_1")
    store.get_or_create("sess_2")

    sessions = store.list_sessions()
    assert len(sessions) == 2
    sids = {s["session_id"] for s in sessions}
    assert "sess_1" in sids
    assert "sess_2" in sids

    deleted = store.delete("sess_1")
    assert deleted is True
    assert store.get("sess_1") is None
    assert len(store.list_sessions()) == 1


def test_web_app_client_state_session_scoping():
    sid = "test_scoped_session_123"
    sess = web_app.get_session_state(sid)
    sess["messages"] = [{"role": "user", "content": "Unique message for this session"}]

    client_state = web_app._client_state(sid)
    assert client_state["session_id"] == sid
    assert len(client_state["messages"]) == 1
    assert client_state["messages"][0]["content"] == "Unique message for this session"
