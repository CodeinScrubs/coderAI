from pathlib import Path

from memory_manager import MemoryManager, get_memory_manager


def test_get_memory_manager_is_fresh_and_workspace_bound(tmp_path: Path):
    storage = tmp_path / "app-data"
    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    project_a.mkdir()
    project_b.mkdir()

    manager_a = get_memory_manager(project_a)
    manager_b = get_memory_manager(project_a)
    # A fresh instance is returned on every call (no shared stale singleton).
    assert manager_a is not manager_b
    # But both bind to the same workspace/project.
    assert manager_a.workspace_path == manager_b.workspace_path
    assert manager_a.project_id == manager_b.project_id

    manager_c = get_memory_manager(project_b)
    assert manager_c.project_id != manager_a.project_id


def test_get_memory_manager_default_uses_active_workspace(tmp_path: Path, monkeypatch):
    from tools import get_workspace, set_workspace

    ws = tmp_path / "active-ws"
    ws.mkdir()
    old_ws = get_workspace()
    set_workspace(ws)
    monkeypatch.setenv("CODERAI_DATA_DIR", str(tmp_path / "data"))
    try:
        manager = get_memory_manager()
        assert manager.workspace_path == ws.resolve()
    finally:
        monkeypatch.delenv("CODERAI_DATA_DIR", raising=False)
        set_workspace(old_ws)


def test_get_summary_lists_facts_and_is_empty_when_none(tmp_path: Path):
    storage = tmp_path / "app-data"
    project = tmp_path / "project"
    project.mkdir()
    manager = MemoryManager(project, storage_root=storage)

    assert manager.get_summary() == ""

    manager.index_fact("Use FastAPI for the API layer", source="note")
    summary = manager.get_summary()
    assert "Use FastAPI for the API layer" in summary


def managers(tmp_path: Path):
    storage = tmp_path / "app-data"
    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    project_a.mkdir()
    project_b.mkdir()
    return MemoryManager(project_a, storage_root=storage), MemoryManager(project_b, storage_root=storage)


def test_central_database_separates_projects_and_sessions(tmp_path: Path):
    first, second = managers(tmp_path)
    first.save_turn("session-a", "user", "Use FastAPI for this service")
    first.save_turn("session-a", "assistant", "Implemented the route")
    second.save_turn("session-b", "user", "Use Flask for this project")

    assert first.db_path == second.db_path
    assert first.project_id != second.project_id
    assert len(first.list_projects()) == 2
    assert first.list_sessions(first.project_id)[0]["id"] == "session-a"
    assert second.list_sessions(second.project_id)[0]["id"] == "session-b"
    assert first.load_session("session-b")["workspace_path"].endswith("project-b")


def test_all_three_memory_layers_are_project_scoped(tmp_path: Path):
    first, second = managers(tmp_path)
    first.save_turn("session-a", "user", "Use FastAPI")
    first.index_fact("The API is built with FastAPI", "app/main.py")
    first.update_preference("tests", "Use pytest")
    second.index_fact("The API is built with Flask", "server.py")

    assert first.load_recent_turns("session-a")[0]["content"] == "Use FastAPI"
    assert first.retrieve_relevant("API", 5)[0]["source"] == "app/main.py"
    assert second.retrieve_relevant("API", 5)[0]["source"] == "server.py"
    assert first.get_user_preferences() == {"tests": "Use pytest"}
    assert second.get_user_preferences() == {}


def test_summary_fact_edit_and_audit(tmp_path: Path):
    first, _ = managers(tmp_path)
    first.save_turn("old-session", "user", "Refactor the parser")
    first.save_turn("old-session", "assistant", "Moved parsing into parser.py")
    fact_id = first.index_fact("Uses Flask", "README.md")
    first.update_fact(fact_id, "Uses FastAPI", "README.md")

    assert "parser.py" in first.summarize_old_session("old-session")
    assert first.list_facts()[0]["fact"] == "Uses FastAPI"
    assert first.audit_path.read_text(encoding="utf-8").count("\n") >= 2


def test_forget_project_keeps_other_projects_and_database(tmp_path: Path):
    first, second = managers(tmp_path)
    first.save_turn("session-a", "user", "forget this")
    second.save_turn("session-b", "user", "keep this")

    first.forget_project()

    assert first.db_path.exists()
    projects = second.list_projects()
    assert len(projects) == 1
    assert projects[0]["name"] == "project-b"
    assert second.load_session("session-b") is not None
