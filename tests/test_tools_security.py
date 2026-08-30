import os
import pytest
from tools import _is_destructive_command, _get_sanitized_env, tool_run_bash


def test_destructive_command_blocking():
    is_danger, reason = _is_destructive_command("rm -rf /")
    assert is_danger
    assert "Root" in reason

    is_danger, reason = _is_destructive_command("del /f /s /q C:\\")
    assert is_danger
    assert "C:\\" in reason

    is_danger, reason = _is_destructive_command("format D:")
    assert is_danger

    is_danger, reason = _is_destructive_command("echo hello world")
    assert not is_danger


def test_destructive_command_in_run_bash():
    from tools import reset_cancel_flag
    reset_cancel_flag()
    result = tool_run_bash("rm -rf /")
    assert "Security Error" in result
    assert "Command blocked" in result


def test_sanitized_env():
    os.environ["CUSTOM_API_KEY"] = "secret_12345"
    os.environ["TAVILY_API_KEY"] = "tvly_secret"
    sanitized = _get_sanitized_env()
    assert "CUSTOM_API_KEY" not in sanitized
    assert "TAVILY_API_KEY" not in sanitized
    assert "PYTHONPATH" in sanitized
