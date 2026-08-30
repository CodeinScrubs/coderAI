import json
import pytest
from context_builder import compact_tool_output, adaptive_compact_messages


def test_compact_tool_output_short():
    short = json.dumps({"status": "ok", "path": "test.py"})
    assert compact_tool_output(short, max_chars=1000) == short


def test_compact_tool_output_large_file_read():
    large_lines = [f"line {i}: some important code snippet" for i in range(1, 200)]
    large_content = "\n".join(large_lines)
    raw = json.dumps({"path": "big_file.py", "content": large_content})
    
    compacted = compact_tool_output(raw, max_chars=500)
    data = json.loads(compacted)
    assert data.get("_compacted") is True
    assert "line 1:" in data["content"]
    assert "line 199:" in data["content"]
    assert "lines hidden for context economy" in data["content"]


def test_compact_tool_output_large_bash_stdout():
    large_stdout = "start log\n" + ("middle output details\n" * 100) + "end log: 0 errors"
    raw = json.dumps({"command": "pytest", "stdout": large_stdout, "exit_code": 0})
    
    compacted = compact_tool_output(raw, max_chars=300)
    data = json.loads(compacted)
    assert data.get("_compacted") is True
    assert "start log" in data["stdout"]
    assert "end log: 0 errors" in data["stdout"]


def test_adaptive_compact_messages():
    history = [
        {"role": "user", "content": "Initial prompt from 5 turns ago"},
        {"role": "assistant", "content": "I will read a huge file", "tool_calls": [{"name": "read_file"}]},
        {"role": "tool", "name": "read_file", "content": json.dumps({"content": "A" * 5000})},
        {"role": "user", "content": "Second request from 3 turns ago"},
        {"role": "assistant", "content": "Executing long build", "tool_calls": [{"name": "run_bash"}]},
        {"role": "tool", "name": "run_bash", "content": json.dumps({"stdout": "B" * 5000})},
        {"role": "user", "content": "Recent prompt"},
        {"role": "assistant", "content": "Recent response"},
    ]
    
    compacted = adaptive_compact_messages(history, token_budget=8000, keep_recent_full_turns=1)
    assert len(compacted) == len(history)
    # Older tool output should be aggressively compacted
    assert len(compacted[2]["content"]) < 1500
    assert len(compacted[5]["content"]) < 1500
