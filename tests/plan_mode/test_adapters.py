"""Tests for the Plan Mode adapters (concrete ports) and the service factory.

These define the adapter contract before implementation (TDD). The repository
tests exercise persistence and thread-safety; the agent-loop tests exercise the
result->ToolOutcome mapping (including fail-closed handling of approval-required
and error output); the workspace and factory tests verify correct wiring.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from plan_mode.adapters.agents import ToolsAgentLoop
from plan_mode.adapters.factories import build_default_service, default_plans_dir
from plan_mode.adapters.repositories import JsonPlanRepository, MemoryPlanRepository
from plan_mode.adapters.workspace import PathWorkspace
from plan_mode.application.ports import ToolOutcome
from plan_mode.domain.entities import Plan


# ---------------------------------------------------------------------------
# MemoryPlanRepository
# ---------------------------------------------------------------------------


class TestMemoryPlanRepository:
    def test_save_get_roundtrip(self):
        repo = MemoryPlanRepository()
        p = Plan.new("goal", workspace="/ws")
        repo.save(p)
        assert repo.get(p.plan_id) is p

    def test_get_missing_is_none(self):
        assert MemoryPlanRepository().get("nope") is None

    def test_list(self):
        repo = MemoryPlanRepository()
        a, b = Plan.new("a"), Plan.new("b")
        repo.save(a)
        repo.save(b)
        assert {p.plan_id for p in repo.list()} == {a.plan_id, b.plan_id}

    def test_instances_are_isolated(self):
        a, b = MemoryPlanRepository(), MemoryPlanRepository()
        a.save(Plan.new("x"))
        assert b.list() == []

    def test_thread_safe_writes(self):
        repo = MemoryPlanRepository()

        def worker(n):
            for i in range(20):
                repo.save(Plan.new(f"p{n}-{i}"))

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(repo.list()) == 80


# ---------------------------------------------------------------------------
# JsonPlanRepository
# ---------------------------------------------------------------------------


class TestJsonPlanRepository:
    def test_persists_to_disk(self, tmp_path):
        repo = JsonPlanRepository(tmp_path)
        p = Plan.new("goal", workspace="/ws")
        p.observations.append("a note")
        repo.save(p)
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1
        on_disk = json.loads(files[0].read_text(encoding="utf-8"))
        assert on_disk["goal"] == "goal"
        assert on_disk["observations"] == ["a note"]

    def test_get_reads_back(self, tmp_path):
        repo = JsonPlanRepository(tmp_path)
        p = Plan.new("goal")
        repo.save(p)
        loaded = repo.get(p.plan_id)
        assert loaded is not None
        assert loaded.goal == "goal"
        assert loaded.plan_id == p.plan_id

    def test_get_missing_is_none(self, tmp_path):
        assert JsonPlanRepository(tmp_path).get("nope") is None

    def test_list(self, tmp_path):
        repo = JsonPlanRepository(tmp_path)
        a, b = Plan.new("a"), Plan.new("b")
        repo.save(a)
        repo.save(b)
        assert {p.plan_id for p in repo.list()} == {a.plan_id, b.plan_id}

    def test_survives_new_instance(self, tmp_path):
        # A fresh repository over the same directory sees the same plans.
        repo1 = JsonPlanRepository(tmp_path)
        p = Plan.new("persist me")
        repo1.save(p)
        repo2 = JsonPlanRepository(tmp_path)
        assert repo2.get(p.plan_id).goal == "persist me"


class TestJsonPlanRepositoryTraversal:
    def test_save_with_bad_id_raises(self, tmp_path):
        repo = JsonPlanRepository(tmp_path)
        p = Plan.new("evil")
        p.plan_id = "../escape"
        with pytest.raises(ValueError):
            repo.save(p)

    def test_get_with_bad_id_returns_none(self, tmp_path):
        repo = JsonPlanRepository(tmp_path)
        assert repo.get("../escape") is None
        assert repo.get("a/b") is None


# ---------------------------------------------------------------------------
# ToolsAgentLoop
# ---------------------------------------------------------------------------


class _FakeTools:
    """Stands in for the `tools` module so the loop is tested without it."""

    def __init__(self, responses: dict) -> None:
        self._responses = responses
        self.calls: list[tuple[str, dict]] = []

    def execute_tool(self, name: str, arguments):
        self.calls.append((name, arguments))
        return self._responses.get(name, "ok:" + name)


class TestToolsAgentLoop:
    def test_success_string(self):
        loop = ToolsAgentLoop(tools_module=_FakeTools({"read_file": "file contents"}))
        out = loop.execute("read_file", {"path": "a.py"})
        assert isinstance(out, ToolOutcome)
        assert out.ok is True
        assert out.output == "file contents"
        assert out.tool_name == "read_file"

    def test_error_string_is_not_ok(self):
        loop = ToolsAgentLoop(
            tools_module=_FakeTools({"write_file": "Error: permission denied"})
        )
        out = loop.execute("write_file", {"path": "a.py", "content": "x"})
        assert out.ok is False
        assert "permission denied" in out.output

    def test_unknown_tool_is_not_ok(self):
        loop = ToolsAgentLoop(tools_module=_FakeTools({}))
        out = loop.execute("not_a_real_tool", {})
        # The real tools.execute_tool returns "Unknown tool: ..." for these.
        loop2 = ToolsAgentLoop(
            tools_module=_FakeTools({"not_a_real_tool": "Unknown tool: not_a_real_tool"})
        )
        out = loop2.execute("not_a_real_tool", {})
        assert out.ok is False

    def test_missing_required_argument_is_not_ok(self):
        loop = ToolsAgentLoop(
            tools_module=_FakeTools({"read_file": "Missing required argument: 'path'"})
        )
        assert loop.execute("read_file", {}).ok is False

    def test_approval_required_is_not_ok(self):
        # A tool that triggers the approval flow returns a dict, not a string.
        resp = {
            "status": "approval_required",
            "tool_name": "write_file",
            "arguments": {"path": "a.py"},
            "preview": "will write",
        }
        loop = ToolsAgentLoop(tools_module=_FakeTools({"write_file": resp}))
        out = loop.execute("write_file", {"path": "a.py", "content": "x"})
        assert out.ok is False
        assert "approval_required" in out.output

    def test_dict_result_is_serialized_ok(self):
        loop = ToolsAgentLoop(tools_module=_FakeTools({"git_status": {"clean": True}}))
        out = loop.execute("git_status", {})
        assert out.ok is True
        assert json.loads(out.output) == {"clean": True}

    def test_exception_is_caught_as_failure(self):
        class _Boom:
            def execute_tool(self, name, arguments):
                raise RuntimeError("boom")

        loop = ToolsAgentLoop(tools_module=_Boom())
        out = loop.execute("read_file", {"path": "a"})
        assert out.ok is False
        assert "boom" in out.output

    def test_arguments_passed_through(self):
        fake = _FakeTools({"run_bash": "out"})
        loop = ToolsAgentLoop(tools_module=fake)
        loop.execute("run_bash", {"command": "ls"})
        assert fake.calls == [("run_bash", {"command": "ls"})]

    def test_soft_read_failure_still_ok(self):
        # A read that finds nothing returns a soft message, not an "Error:"
        # prefix; the loop treats it as a successful (empty) read.
        loop = ToolsAgentLoop(
            tools_module=_FakeTools({"read_file": "File does not exist: a.py"})
        )
        assert loop.execute("read_file", {"path": "a.py"}).ok is True


# ---------------------------------------------------------------------------
# PathWorkspace
# ---------------------------------------------------------------------------


class TestPathWorkspace:
    def test_resolves_via_tools(self, monkeypatch):
        import tools

        target = Path("C:/some/ws")
        monkeypatch.setattr(tools, "get_workspace", lambda: target)
        assert Path(PathWorkspace().resolve()) == target


# ---------------------------------------------------------------------------
# build_default_service (factory)
# ---------------------------------------------------------------------------


class TestFactory:
    def test_returns_plan_mode_service(self):
        svc = build_default_service(directory=None)
        from plan_mode.application.service import PlanModeService

        assert isinstance(svc, PlanModeService)

    def test_uses_json_repo_when_directory_given(self, tmp_path):
        svc = build_default_service(directory=tmp_path)
        plan = svc.start_plan("goal")
        # it should have persisted to the given directory
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1
        assert plan["state"] == "exploring"

    def test_default_plans_dir_is_under_coderai_data(self):
        d = default_plans_dir()
        assert d.name == "plans"
        assert "coderai_data" in str(d).replace("\\", "/")
