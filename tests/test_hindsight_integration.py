import pytest
from unittest.mock import MagicMock, patch
from hindsight_manager import (
    sanitize_bank_id,
    HindsightMemoryManager,
    get_hindsight_manager,
)
from tools import (
    tool_remember_fact,
    tool_recall_memory,
    tool_reflect_memory,
    execute_tool,
)


def test_sanitize_bank_id():
    assert sanitize_bank_id("E:\\llm_projects\\my-project") == "ws_my-project"
    assert sanitize_bank_id("/home/user/code/AwesomeApp") == "ws_awesomeapp"
    assert sanitize_bank_id(None) == "default-workspace"


def test_hindsight_manager_offline_fallback():
    hm = HindsightMemoryManager(base_url="http://127.0.0.1:99999", timeout=0.1)
    # is_available should be False since server does not exist
    assert hm.is_available(force_refresh=True) is False

    # Retain should fallback to local storage gracefully
    res = hm.retain("Important architectural decision: use FastAPI", context="architecture")
    assert res.get("status") in {"retained_locally", "error"}
    assert res.get("engine") == "local_fallback" or "error" in res

    # Recall should fallback
    recall_res = hm.recall("FastAPI", max_tokens=100)
    assert "count" in recall_res
    assert recall_res.get("engine") in {"local_fallback", "none"}

    # Status should report offline
    status = hm.get_status()
    assert status["online"] is False
    assert status["client_installed"] is True


def test_hindsight_manager_mocked_online():
    hm = HindsightMemoryManager(base_url="http://localhost:8888")

    mock_client = MagicMock()
    # Mock retain
    mock_retain_resp = MagicMock()
    mock_retain_resp.id = "mem-123"
    mock_client.retain.return_value = mock_retain_resp

    # Mock recall
    mock_recall_resp = MagicMock()
    mock_recall_resp.to_prompt_string.return_value = "- User prefers ruff formatter"
    mock_recall_resp.results = ["fact1"]
    mock_client.recall.return_value = mock_recall_resp

    # Mock reflect
    mock_reflect_resp = MagicMock()
    mock_reflect_resp.text = "Analysis shows high test coverage."
    mock_client.reflect.return_value = mock_reflect_resp

    with patch.object(hm, "is_available", return_value=True):
        with patch.object(hm, "_get_client", return_value=mock_client):
            # Test retain
            res = hm.retain("User prefers ruff formatter", context="code_style")
            assert res["status"] == "retained"
            assert res["engine"] == "hindsight"
            assert res["id"] == "mem-123"

            # Test recall
            rec = hm.recall("formatter")
            assert rec["engine"] == "hindsight"
            assert "User prefers ruff" in rec["prompt_string"]

            # Test reflect
            ref = hm.reflect("test coverage")
            assert "high test coverage" in ref


def test_hindsight_tools():
    # Test remember_fact tool
    out = tool_remember_fact("Use pydantic v2 for data models", context="architecture")
    assert "Retained in" in out
    assert "pydantic v2" in out

    # Test recall_memory tool
    recall_out = tool_recall_memory("pydantic")
    assert isinstance(recall_out, str)

    # Test reflect_memory tool
    reflect_out = tool_reflect_memory("project patterns")
    assert isinstance(reflect_out, str)

    # Test via execute_tool dispatcher
    disp_out = execute_tool("remember_fact", {"content": "Test fact via dispatcher"})
    assert "Retained in" in str(disp_out)
