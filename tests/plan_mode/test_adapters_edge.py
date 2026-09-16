"""Edge-case tests for Plan Mode adapters (corrupt data, serialization fallback,
PyInstaller base-dir branch) plus the set_steps terminal guard."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from plan_mode.adapters.agents import ToolsAgentLoop
from plan_mode.adapters.factories import _base_dir
from plan_mode.adapters.repositories import JsonPlanRepository
from plan_mode.domain.entities import Plan, PlanStep
from plan_mode.domain.states import PlanState


def test_serialize_falls_back_to_str_for_unserializable():
    # A tool returning something json can't encode (e.g. an object with no
    # __repr__ issues) should still yield a string, not raise.
    class _Opaque:
        def __repr__(self) -> str:
            return "<opaque>"

    out = ToolsAgentLoop._serialize(_Opaque())
    assert out == "<opaque>"


def test_json_get_returns_none_on_corrupt_file(tmp_path):
    (tmp_path / "abcd1234abcd1234abcd1234abcd1234.json").write_text(
        "{ this is not json", encoding="utf-8"
    )
    repo = JsonPlanRepository(tmp_path)
    assert repo.get("abcd1234abcd1234abcd1234abcd1234") is None


def test_json_list_skips_corrupt_files(tmp_path):
    good = Plan.new("good")
    (tmp_path / f"{good.plan_id}.json").write_text(
        json.dumps(good.to_dict()), encoding="utf-8"
    )
    (tmp_path / "ffff0000ffff0000ffff0000ffff0000.json").write_text(
        "not json at all", encoding="utf-8"
    )
    repo = JsonPlanRepository(tmp_path)
    loaded = repo.list()
    assert [p.plan_id for p in loaded] == [good.plan_id]


def test_base_dir_uses_meipass_when_present(monkeypatch):
    monkeypatch.setattr(sys, "_MEIPASS", "/fake/meipass", raising=False)
    assert _base_dir() == Path("/fake/meipass")


def test_set_steps_rejected_on_terminal_plan():
    p = Plan.new("g")
    p.transition_to(PlanState.EXPLORING)
    p.transition_to(PlanState.DRAFTING)
    p.transition_to(PlanState.AWAITING_APPROVAL)
    p.transition_to(PlanState.REJECTED)
    try:
        p.set_steps([PlanStep("s", "t", "read_file")])
        raised = False
    except ValueError:
        raised = True
    assert raised is True
