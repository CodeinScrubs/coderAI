"""
Shared pytest fixtures for the coderAI test suite.

The suite must be hermetic: no test may mutate the git history of the
repository it is running from. ``tool_write_file`` / ``tool_replace_in_file``
auto-commit when ``AUTO_COMMIT`` is on, so we pin it off for every test as a
belt-and-braces guarantee (independent of any process-global state a previous
test may have left behind).
"""

import pytest

import coderai.tools.tools as tools


@pytest.fixture(autouse=True)
def _no_auto_commit(monkeypatch):
    """Auto-commit must never fire during a test run."""
    monkeypatch.setattr(tools, "AUTO_COMMIT", False)
    yield
