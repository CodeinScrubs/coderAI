import pytest
from tool_parser import repair_json_tool_arguments, extract_fallback_tool_calls_from_text


def test_clean_json_parsing():
    assert repair_json_tool_arguments('{"path": "main.py", "lines": 20}') == {"path": "main.py", "lines": 20}
    assert repair_json_tool_arguments({"already": "dict"}) == {"already": "dict"}
    assert repair_json_tool_arguments("") == {}


def test_markdown_fenced_json():
    raw = """```json
    {
      "path": "app.py",
      "overwrite": true
    }
    ```"""
    assert repair_json_tool_arguments(raw) == {"path": "app.py", "overwrite": True}


def test_python_literals_and_trailing_commas():
    raw = '{"path": "config.json", "enabled": True, "debug": False, "secret": None,}'
    res = repair_json_tool_arguments(raw)
    assert res.get("path") == "config.json"
    assert res.get("enabled") is True
    assert res.get("debug") is False
    assert res.get("secret") is None


def test_single_quoted_and_unquoted_keys():
    raw = "{'path': 'server.js', count: 42}"
    res = repair_json_tool_arguments(raw)
    assert res.get("path") == "server.js"
    assert res.get("count") == 42


def test_fallback_tool_call_markdown():
    text = """I will now create the file:
```tool_call:tool_write_file
{
  "path": "test.txt",
  "content": "Hello World"
}
```
Done!"""
    calls = extract_fallback_tool_calls_from_text(text, ["tool_write_file", "tool_read_file"])
    assert len(calls) == 1
    assert calls[0]["name"] == "tool_write_file"
    assert calls[0]["arguments"] == {"path": "test.txt", "content": "Hello World"}


def test_fallback_tool_call_xml_and_action_format():
    xml_text = '<tool_call>{"name": "tool_read_file", "arguments": {"path": "README.md"}}</tool_call>'
    calls = extract_fallback_tool_calls_from_text(xml_text, ["tool_read_file"])
    assert len(calls) == 1
    assert calls[0]["name"] == "tool_read_file"
    assert calls[0]["arguments"] == {"path": "README.md"}

    action_text = """Thought: Need to run tests
Action: tool_run_bash
Action Input: {"command": "pytest"}
"""
    calls_act = extract_fallback_tool_calls_from_text(action_text, ["tool_run_bash"])
    assert len(calls_act) == 1
    assert calls_act[0]["name"] == "tool_run_bash"
    assert calls_act[0]["arguments"] == {"command": "pytest"}
