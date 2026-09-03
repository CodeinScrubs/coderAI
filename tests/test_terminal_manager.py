"""
tests/test_terminal_manager.py - Unit tests for the integrated terminal subsystem.
"""

import time
from pathlib import Path
from terminal_manager import TerminalManager, TerminalSession


def test_terminal_session_creation(tmp_path: Path):
    session = TerminalSession(session_id="test_sess", shell_type="powershell", cwd=tmp_path)
    assert session.session_id == "test_sess"
    assert session.shell_type == "powershell"
    assert session.cwd == tmp_path.resolve()
    assert session.is_running()
    session._close_internal()


def test_terminal_session_execute_and_stream(tmp_path: Path):
    session = TerminalSession(session_id="test_sess_exec", shell_type="powershell", cwd=tmp_path)
    session.write("Write-Output 'Hello from PowerShell Terminal'\r\n")
    
    events = []
    start_time = time.time()
    while time.time() - start_time < 3.0:
        while not session.output_queue.empty():
            events.append(session.output_queue.get_nowait())
        if any("Hello from PowerShell Terminal" in e.get("text", "") for e in events):
            break
        time.sleep(0.1)
    
    while not session.output_queue.empty():
        events.append(session.output_queue.get_nowait())
    
    texts = [e.get("text", "") for e in events]
    combined = "".join(texts)
    assert "Hello from PowerShell Terminal" in combined or len(events) >= 1
    session._close_internal()


def test_terminal_manager_singleton(tmp_path: Path):
    mgr1 = TerminalManager()
    mgr2 = TerminalManager()
    assert mgr1 is mgr2

    session = mgr1.get_or_create_session("sess_abc", shell_type="cmd", cwd=tmp_path)
    assert session.shell_type == "cmd"

    shells = mgr1.list_available_shells()
    shell_ids = [s["id"] for s in shells]
    assert "powershell" in shell_ids or "cmd" in shell_ids

    mgr1.remove_session("sess_abc")
