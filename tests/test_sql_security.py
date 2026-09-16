"""
tests/test_sql_security.py - TDD spec for the SQL tools (P0 #2).

execute_sql_query used to accept a model-supplied connection string (including
remote databases) and commit arbitrary statements. After the fix: only a
workspace-local SQLite file is reachable, remote schemes and out-of-workspace
paths are rejected, read-only queries run unprompted, and write statements
require explicit approval.
"""

import json
import sqlite3
from pathlib import Path

import pytest

import tools
from tools import clear_approval_state, execute_tool, set_workspace


def _fresh_ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    set_workspace(ws)
    clear_approval_state()
    tools.reset_cancel_flag()
    return ws


def _make_db(ws: Path, name: str = "app.db") -> Path:
    db = ws / name
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE t (id INTEGER, name TEXT)")
    conn.execute("INSERT INTO t VALUES (42, 'answer')")
    conn.commit()
    conn.close()
    return db


def _payload(out) -> dict:
    try:
        data = json.loads(out)
    except (json.JSONDecodeError, TypeError):
        return {"status": "not-approval-required", "raw": out}
    if isinstance(data, dict) and data.get("status") == "approval_required":
        return data
    return {"status": "not-approval-required", "raw": out}


def test_remote_scheme_rejected(tmp_path):
    _make_db(_fresh_ws(tmp_path))
    out = execute_tool("execute_sql_query", {
        "connection_string": "postgresql://user:pw@evil.example/db",
        "query": "SELECT 1",
    })
    assert "scheme" in out.lower()
    assert "sqlite" in out.lower()


def test_out_of_workspace_path_rejected(tmp_path):
    _fresh_ws(tmp_path)
    out = execute_tool("execute_sql_query", {
        "connection_string": "../outside.db",
        "query": "SELECT 1",
    })
    assert "workspace" in out.lower() or "not allowed" in out.lower()


def test_select_runs_without_approval(tmp_path):
    ws = _fresh_ws(tmp_path)
    _make_db(ws)
    out = execute_tool("execute_sql_query", {"connection_string": "app.db", "query": "SELECT * FROM t"})
    assert "approval_required" not in out
    assert "42" in out
    assert "answer" in out


def test_with_cte_is_readonly(tmp_path):
    ws = _fresh_ws(tmp_path)
    _make_db(ws)
    out = execute_tool("execute_sql_query", {
        "connection_string": "app.db",
        "query": "WITH x AS (SELECT id AS v FROM t) SELECT * FROM x",
    })
    assert "approval_required" not in out
    assert "42" in out


def test_non_select_requires_approval(tmp_path):
    ws = _fresh_ws(tmp_path)
    _make_db(ws)
    payload = _payload(execute_tool("execute_sql_query", {
        "connection_string": "app.db", "query": "DELETE FROM t",
    }))
    assert payload["status"] == "approval_required"
    assert payload["tool_name"] == "execute_sql_query"


def test_comment_prefixed_write_requires_approval(tmp_path):
    ws = _fresh_ws(tmp_path)
    _make_db(ws)
    payload = _payload(execute_tool("execute_sql_query", {
        "connection_string": "app.db", "query": "-- harmless comment\nDROP TABLE t",
    }))
    assert payload["status"] == "approval_required"


def test_write_executes_after_approval(tmp_path):
    ws = _fresh_ws(tmp_path)
    _make_db(ws)
    args = {"connection_string": "app.db", "query": "INSERT INTO t VALUES (7, 'seven')"}
    payload = _payload(execute_tool("execute_sql_query", args))
    assert payload["status"] == "approval_required"

    tools.resolve_approval(payload["token"], True)
    out = execute_tool("execute_sql_query", args)  # identical args -> same token -> approved
    assert "approval_required" not in out

    conn = sqlite3.connect(ws / "app.db")
    rows = conn.execute("SELECT * FROM t WHERE id = 7").fetchall()
    conn.close()
    assert rows == [(7, "seven")]


def test_get_database_schema_ungated_local(tmp_path):
    ws = _fresh_ws(tmp_path)
    _make_db(ws)
    out = execute_tool("get_database_schema", {"connection_string": "app.db"})
    assert "approval_required" not in out
    assert "t" in out  # table name present
    assert "id" in out


def test_get_database_schema_remote_rejected(tmp_path):
    _fresh_ws(tmp_path)
    out = execute_tool("get_database_schema", {"connection_string": "mysql://root@host/db"})
    assert "scheme" in out.lower()
