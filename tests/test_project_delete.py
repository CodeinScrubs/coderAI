import pytest
from pathlib import Path
from memory_manager import MemoryManager


def test_memory_manager_delete_project_by_id(tmp_path):
    manager = MemoryManager(tmp_path / 'project_a')
    project_id_a = manager.project_id
    manager.update_preference('theme', 'dark')
    manager.ensure_session('sess-1', 'Test session')
    manager.save_turn('sess-1', 'user', 'hello')
    manager.index_fact('fact 1', source='unit_test')
    manager.index_fact('fact 2', source='unit_test')

    # Create another project
    manager_b = MemoryManager(tmp_path / 'project_b')
    project_id_b = manager_b.project_id
    manager_b.index_fact('fact in B', source='unit_test')

    # Verify both exist
    projects = manager.list_projects()
    project_ids = [p['id'] for p in projects]
    assert project_id_a in project_ids
    assert project_id_b in project_ids

    # Delete project A
    deleted = manager.delete_project_by_id(project_id_a)
    assert deleted is True

    # Verify project A is gone and project B remains
    remaining = manager.list_projects()
    remaining_ids = [p['id'] for p in remaining]
    assert project_id_a not in remaining_ids
    assert project_id_b in remaining_ids
    assert len(manager.list_facts(project_id=project_id_a)) == 0
    assert len(manager.get_user_preferences(project_id=project_id_a)) == 0


def test_delete_non_existent_project(tmp_path):
    manager = MemoryManager(tmp_path)
    deleted = manager.delete_project_by_id(999999)
    assert deleted is False
