import pytest
from pathlib import Path
from context_builder import (
    extract_code_outline,
    compress_source_code,
    compact_history_assistant_turns,
)
from tools import tool_read_file, set_workspace


def test_extract_code_outline_python():
    py_code = '''"""Module docstring."""

import os
import sys

GLOBAL_VAR = 42

class DataProcessor:
    """Class docstring."""
    def __init__(self, name: str):
        self.name = name

    def process(self, items: list) -> int:
        """Process items."""
        total = 0
        for item in items:
            total += item
        return total

def standalone_func(x: int, y: int = 10) -> bool:
    """Check if x > y."""
    return x > y
'''
    outline = extract_code_outline(py_code, file_path="processor.py")
    assert "class DataProcessor" in outline
    assert "def __init__(self, name)" in outline
    assert "def process(self, items)" in outline
    assert "def standalone_func(x, y)" in outline
    # Bodies should be elided with ...
    assert "total += item" not in outline
    assert "Line 8:" in outline


def test_extract_code_outline_regex_fallback():
    js_code = '''
export class UserService {
    constructor(db) {
        this.db = db;
    }

    async getUser(id) {
        return await this.db.find(id);
    }
}

function helper(a, b) {
    return a + b;
}
'''
    outline = extract_code_outline(js_code, file_path="service.js")
    assert "class UserService" in outline
    assert "async getUser(id)" in outline
    assert "function helper(a, b)" in outline


def test_compress_source_code_modes():
    code = '''# Comment 1
def foo():
    # Inner comment
    print("hello")
    
'''
    # Clean mode removes comment lines
    clean = compress_source_code(code, mode="clean")
    assert "# Comment 1" not in clean
    assert 'print("hello")' in clean

    # Outline mode
    outline = compress_source_code(code, mode="outline")
    assert "def foo()" in outline

    # Raw mode
    raw = compress_source_code(code, mode="raw")
    assert raw == code


def test_compact_history_assistant_turns():
    big_code = "\n".join([f"    line_{i} = {i}" for i in range(25)])
    messages = [
        {"role": "user", "content": "Write some code"},
        {"role": "assistant", "content": f"Here is code 1:\n```python\n{big_code}\n```\nAll done."},
        {"role": "user", "content": "Now update it"},
        {"role": "assistant", "content": f"Here is code 2:\n```python\n{big_code}\n```\nUpdated."},
    ]

    compacted = compact_history_assistant_turns(messages, keep_recent_assistant_code=1, min_lines_to_collapse=10)
    assert len(compacted) == 4
    # The older assistant turn (index 1) should have its code block collapsed
    assert "collapsed to save tokens" in compacted[1]["content"]
    assert "line_20" not in compacted[1]["content"]
    assert "Here is code 1:" in compacted[1]["content"]

    # The most recent assistant turn (index 3) should have its code block preserved intact
    assert "line_20" in compacted[3]["content"]
    assert "collapsed to save tokens" not in compacted[3]["content"]


def test_tool_read_file_windowing(tmp_path: Path):
    set_workspace(str(tmp_path))
    test_file = tmp_path / "sample.py"
    lines = [f"line {i}" for i in range(1, 21)]
    test_file.write_text("\n".join(lines), encoding="utf-8")

    # Read window: lines 5 to 10
    result = tool_read_file("sample.py", start_line=5, end_line=10, mode="raw")
    assert "lines 5-10 of 20" in result
    assert "5: line 5" in result
    assert "10: line 10" in result
    assert "line 4" not in result
    assert "line 11" not in result

    # Read outline mode
    py_sample = tmp_path / "sample_outline.py"
    py_sample.write_text("class MyTest:\n    def run(self):\n        pass\n", encoding="utf-8")
    outline_result = tool_read_file("sample_outline.py", mode="outline")
    assert "class MyTest" in outline_result
    assert "def run(self)" in outline_result
