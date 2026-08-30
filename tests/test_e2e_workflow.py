import json
import pytest
from pathlib import Path

from codebase_index import CodebaseIndex
from context_builder import estimate_tokens_for_messages, estimate_tokens_for_text
from tools import (
    tool_write_file,
    tool_read_file,
    tool_list_files,
    tool_run_python,
    cancel_current_execution,
    reset_cancel_flag,
    is_execution_cancelled,
    set_workspace,
    get_workspace,
    approve_pending,
)
from memory_manager import MemoryManager
from skill_tracker import SkillTracker


def test_full_workspace_lifecycle_e2e(tmp_path):
    ws = tmp_path / "test_project"
    ws.mkdir(parents=True, exist_ok=True)
    set_workspace(ws)
    approve_pending(always_allow_for_session=True)

    # 1. Tool write and read file
    write_res = tool_write_file("main.py", "def add(a, b):\n    return a + b\n\nprint(add(2, 3))\n")
    assert "File written" in write_res
    assert (ws / "main.py").exists()

    read_res = tool_read_file("main.py")
    assert "def add" in read_res

    # 2. Codebase indexing & RAG search
    index = CodebaseIndex(ws)
    index.rebuild()
    status = index.status()
    assert status["files"] >= 1
    assert status["chunks"] >= 1

    search_res = index.retrieve_relevant_code("add function", top_k=3)
    assert len(search_res) >= 1
    assert any("main.py" in r["file_path"] for r in search_res)

    # 3. Python script execution in sandbox
    py_res = tool_run_python("import sys\nprint('Computed:', 2 + 3)")
    assert "Computed: 5" in py_res
    assert "exit code: 0" in py_res

    # 4. Token estimation
    tokens = estimate_tokens_for_text(read_res)
    assert tokens > 0

    # 5. Cancellation workflow
    reset_cancel_flag()
    assert not is_execution_cancelled()
    cancel_current_execution()
    assert is_execution_cancelled()
    reset_cancel_flag()
    assert not is_execution_cancelled()

    # 6. Memory management
    mem = MemoryManager(ws, storage_root=tmp_path / "memory_data")
    mem.index_fact("FastAPI + Local Ollama workflow", source="test")
    facts = mem.retrieve_relevant("FastAPI architecture")
    assert len(facts) >= 1
    assert "FastAPI" in facts[0]["fact"]

    # 7. Skill tracker
    tracker = SkillTracker(ws, storage_root=tmp_path / "skill_data")
    tracker.log_usage("session_1", "python-expert", "keyword", ["python"], "applied", 1)
    report = tracker.report(["python-expert"])
    assert report["skills"][0]["applied"] >= 1
