import sys
import traceback
sys.path.insert(0, r"E:\llm_projects\agantic_ai\ollama_workspace_v4")
from tools import _HANDLERS, set_workspace
set_workspace(r"E:\llm_projects\agantic_ai\ollama_workspace_v4")

dummy_args = {
    "read_file": {"path": "README.md"},
    "write_file": {"path": "test_dummy.txt", "content": "hello"},
    "list_files": {"pattern": "*"},
    "extract_url": {"urls": ["https://example.com"]},
    "search_files": {"query": "test"},
    "read_many_files": {"paths": ["README.md"]},
    "replace_in_file": {"path": "test_dummy.txt", "old": "hello", "new": "world"},
    "append_file": {"path": "test_dummy.txt", "content": "!"},
    "create_directory": {"path": "test_dir"},
    "project_tree": {},
    "current_time": {},
    "delete_file": {"path": "test_dummy.txt"},
    "search_codebase": {"query": "test"},
    "get_project_overview": {},
    "get_related_files": {"path": "README.md"},
    "scan_project": {},
    "remember_fact": {"content": "test"},
    "recall_memory": {"query": "test"},
    "reflect_memory": {"query": "test"},
    "get_project_architecture": {},
    "get_impact_radius": {"files": ["README.md"]},
    "query_code_graph": {"pattern": "*", "symbol": "test"},
    "git_status": {},
    "git_log": {},
    "git_diff": {},
    "git_commit": {"message": "Test"},
    "git_checkout": {"branch": "main"},
    "get_database_schema": {"connection_string": ""},
    "execute_sql_query": {"connection_string": "", "query": ""},
    "navigate_web": {"url": "https://example.com"},
    "take_screenshot": {"url": "https://example.com", "output_path": "test.png"},
    "run_docker_container": {"image": "alpine", "command": "ls"}
}

failed = False
for name, handler in _HANDLERS.items():
    if name not in dummy_args:
        continue # skip tools that require complex setup like web browsers or docker if they block
    if name in ["navigate_web", "take_screenshot", "run_docker_container", "extract_url"]:
        continue
    try:
        args = dummy_args[name]
        res = handler(args)
        # print(f"[OK] {name}")
    except Exception as e:
        print(f"[FAIL] {name}: {e}")
        traceback.print_exc()
        failed = True

if not failed:
    print("All tested tools executed without crashing.")
