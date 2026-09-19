"""
tests/test_remember_fact_honesty.py - The remember_fact tool must not report a
success when the memory was not actually stored (P0 #6).

tool_remember_fact used to always say "Retained in local memory store" without
checking the result of hm.retain, so a failed local fallback was reported as a
success. Now a status of "error" (or "skipped") surfaces an honest failure.
"""

from pathlib import Path

import pytest

from coderai.tools.tools import (
    execute_tool,
    get_workspace,
    set_workspace,
    tool_recall_memory,
    tool_remember_fact,
)


def test_remember_fact_true_success_is_retrievable(tmp_path, monkeypatch):
    """A retained fact (via the local fallback) is really stored and recallable."""
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    old_ws = get_workspace()
    set_workspace(ws)
    monkeypatch.setenv("CODERAI_DATA_DIR", str(tmp_path / "memory_data"))
    try:
        out = tool_remember_fact("The build pipeline uses poetry", context="build")
        assert "Retained in" in out
        assert "The build pipeline uses poetry" in out

        recall = tool_recall_memory("poetry build pipeline")
        assert "poetry" in recall.lower()
    finally:
        monkeypatch.delenv("CODERAI_DATA_DIR", raising=False)
        set_workspace(old_ws)


def test_remember_fact_reports_honest_failure(tmp_path, monkeypatch):
    """When retain returns status 'error', the tool must not claim success."""
    from unittest.mock import MagicMock, patch

    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    set_workspace(ws)

    hm = MagicMock()
    hm.retain.return_value = {"status": "error", "error": "disk full", "bank_id": "ws_ws"}
    with patch("hindsight_manager.get_hindsight_manager", return_value=hm):
        out = tool_remember_fact("some fact", context="x")

    assert "Failed to store" in out
    assert "Retained in" not in out
    assert "disk full" in out


def test_remember_fact_skipped_is_not_a_success(tmp_path):
    """Empty content is skipped, and that must not be reported as retained."""
    from unittest.mock import MagicMock, patch

    hm = MagicMock()
    hm.retain.return_value = {"status": "skipped", "reason": "empty content"}
    with patch("hindsight_manager.get_hindsight_manager", return_value=hm):
        out = tool_remember_fact("   ", context="x")

    assert "Skipped" in out
    assert "Retained in" not in out
