"""tests/test_codebase_index_cache.py - P1-16.

Constructing ``CodebaseIndex(workspace)`` is expensive: it resolves the
embedding model over a blocking Ollama round-trip, opens a chroma
``PersistentClient``, and initializes the sqlite schema. The agent tools and
the per-turn RAG context built a fresh instance on *every* call, so a single
turn paid the round-trip several times — the "thinking…" stall.

``get_codebase_index`` returns one shared instance per workspace, for a short
TTL (the index data itself lives on disk, so the cached handle is always
reading fresh data; the TTL only bounds how long a sticky instance state —
e.g. a transient embedding outage flag — can persist).

These tests pin the caching contract without depending on Ollama:
  * one construction per workspace within the TTL (instance identity);
  * distinct workspaces get distinct instances;
  * TTL expiry rebuilds;
  * the cache is bounded and clearable;
  * the agent tools share one instance across calls (the user-visible fix).
"""

from __future__ import annotations

import time

import pytest

import coderai.codebase.codebase_index as ci
from coderai.codebase.codebase_index import (
    clear_codebase_index_cache,
    get_codebase_index,
)


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_codebase_index_cache()
    yield
    clear_codebase_index_cache()


def _counting_init(monkeypatch):
    """Wrap CodebaseIndex.__init__ and count constructions."""
    original = ci.CodebaseIndex.__init__
    calls = []

    def spy(self, workspace_path):
        calls.append(workspace_path)
        original(self, workspace_path)

    monkeypatch.setattr(ci.CodebaseIndex, "__init__", spy)
    return calls


def test_single_construction_within_ttl(tmp_path, monkeypatch):
    calls = _counting_init(monkeypatch)
    a = get_codebase_index(tmp_path)
    b = get_codebase_index(tmp_path)
    assert a is b
    assert len(calls) == 1


def test_distinct_workspaces_distinct_instances(tmp_path, monkeypatch):
    calls = _counting_init(monkeypatch)
    ws_a = tmp_path / "a"
    ws_b = tmp_path / "b"
    ws_a.mkdir()
    ws_b.mkdir()
    a = get_codebase_index(ws_a)
    b = get_codebase_index(ws_b)
    assert a is not b
    assert len(calls) == 2
    # same path, different spelling -> same instance
    assert get_codebase_index(str(ws_a)) is a


def test_ttl_expiry_rebuilds(tmp_path, monkeypatch):
    calls = _counting_init(monkeypatch)
    monkeypatch.setattr(ci, "_CODE_INDEX_CACHE_TTL_S", 0.01)
    a = get_codebase_index(tmp_path)
    time.sleep(0.02)
    b = get_codebase_index(tmp_path)
    assert a is not b
    assert len(calls) == 2


def test_cache_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(ci, "_CODE_INDEX_CACHE_TTL_S", 300.0)
    for i in range(ci._CODE_INDEX_CACHE_MAX + 3):
        ws = tmp_path / f"ws{i}"
        ws.mkdir()
        get_codebase_index(ws)
    assert len(ci._CODE_INDEX_CACHE) <= ci._CODE_INDEX_CACHE_MAX


def test_clear_cache_forces_rebuild(tmp_path, monkeypatch):
    calls = _counting_init(monkeypatch)
    a = get_codebase_index(tmp_path)
    clear_codebase_index_cache()
    b = get_codebase_index(tmp_path)
    assert a is not b
    assert len(calls) == 2


def test_tools_share_one_instance(tmp_path, monkeypatch):
    """The payoff: a turn's codebase tools construct the index once, not
    once per tool call."""
    from coderai.tools import tools

    calls = _counting_init(monkeypatch)
    from coderai.tools.tools import set_workspace, tool_search_codebase

    ws = tmp_path / "project"
    ws.mkdir()
    set_workspace(ws)

    # Empty index -> the tools short-circuit with "index is empty", which is
    # exactly the path that previously still paid a full construction.
    out1 = tool_search_codebase("anything", 3)
    out2 = tool_search_codebase("anything else", 3)
    assert "empty" in out1.lower()
    assert len(calls) == 1, f"expected 1 construction, got {len(calls)}"
