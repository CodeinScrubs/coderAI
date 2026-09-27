"""tests/test_tool_context_persistence.py - P1-13.

Tool calls and their results used to live only in the per-turn, in-memory
agent history. Only the user prompt and the final assistant text were
persisted to ``STATE["messages"]``, so the next turn rebuilt its context from
scratch and the model re-read files / re-ran commands it had already seen.

These tests pin the new behavior:

  * a completed assistant tool-call exchange (the assistant ``tool_calls``
    message + every tool result) is persisted to ``STATE["messages"]``;
  * the *next* turn's model input therefore contains the previous turn's tool
    context (no re-read);
  * an incomplete exchange (cancelled mid-iteration, or a call with no result)
    is NOT persisted — a dangling assistant tool_calls / tool response is
    invalid for strict APIs;
  * ``_build_api_messages`` never selects half an exchange: a tool response is
    either kept together with its assistant ``tool_calls`` message or dropped
    with it, and a leading orphaned tool message is dropped.
"""

from __future__ import annotations

import coderai.server.web_app as web_app
from coderai.server.web_app import MODE_CUSTOM


def _clear_state(monkeypatch):
    """Reset the pieces of STATE these tests touch, without clobbering the
    rest (other tests in the suite may have populated it)."""
    monkeypatch.setitem(web_app.STATE, "messages", [])
    monkeypatch.setitem(web_app.STATE, "tools_log", [])
    monkeypatch.setitem(web_app.STATE, "memory_enabled", False)
    monkeypatch.setitem(web_app.STATE, "memory_session_id", "default")
    monkeypatch.setitem(web_app.STATE, "conn_mode", web_app.MODE_LOCAL)
    monkeypatch.setitem(web_app.STATE, "context_token_budget", 100_000)
    # Keep the test offline/deterministic: no litellm/tiktoken token estimate
    # and no Hindsight recall (which would touch chroma / the network).
    monkeypatch.setattr(web_app, "_estimate_tokens_for_text", lambda text: 10)

    class _NoHindsight:
        def is_available(self):
            return False

    monkeypatch.setattr(
        "coderai.memory.hindsight_manager.get_hindsight_manager",
        lambda: _NoHindsight(),
    )


# ── _persist_tool_history (the unit both loops share) ────────────────────────

def test_persist_tool_history_appends_call_and_results(monkeypatch):
    _clear_state(monkeypatch)
    web_app.STATE["messages"].append({"role": "user", "content": "read me"})

    tc = [
        {"name": "read_file", "arguments": {"path": "a.py"}, "id": "call_0"},
        {"name": "read_file", "arguments": {"path": "b.py"}, "id": "call_1"},
    ]
    turn_tools = [
        {"name": "read_file", "args": {"path": "a.py"}, "result": "A-CONTENT"},
        {"name": "read_file", "args": {"path": "b.py"}, "result": "B-CONTENT"},
    ]

    web_app._persist_tool_history(web_app.STATE["messages"], "let me read", tc, turn_tools)

    msgs = web_app.STATE["messages"]
    # assistant tool_calls message + one tool message per call
    assert len(msgs) == 1 + 1 + 2
    assistant = msgs[1]
    assert assistant["role"] == "assistant"
    assert assistant["content"] == "let me read"
    assert len(assistant["tool_calls"]) == 2
    assert msgs[2]["role"] == "tool" and msgs[2]["name"] == "read_file"
    assert msgs[2]["content"] == "A-CONTENT"
    assert msgs[3]["role"] == "tool" and msgs[3]["content"] == "B-CONTENT"


def test_persist_tool_history_skips_incomplete_exchange(monkeypatch):
    _clear_state(monkeypatch)
    web_app.STATE["messages"].append({"role": "user", "content": "hi"})

    # Two calls, but only one result (cancelled mid-iteration) -> must be
    # dropped wholesale so we never persist a dangling tool_calls block.
    tc = [
        {"name": "read_file", "arguments": {"path": "a.py"}, "id": "call_0"},
        {"name": "read_file", "arguments": {"path": "b.py"}, "id": "call_1"},
    ]
    turn_tools = [{"name": "read_file", "args": {"path": "a.py"}, "result": "A"}]

    web_app._persist_tool_history(web_app.STATE["messages"], "partial", tc, turn_tools)

    # only the original user message remains
    assert web_app.STATE["messages"] == [{"role": "user", "content": "hi"}]


# ── _run_agent_loop persists a completed turn ────────────────────────────────

def test_run_agent_loop_persists_tool_exchange(monkeypatch):
    _clear_state(monkeypatch)

    tc = [{"name": "read_file", "arguments": {"path": "a.py"}, "id": "call_0"}]
    responses = [
        # first: model asks for a tool call
        {"content": "reading", "thinking": "", "tool_calls": tc, "finish_reason": "stop"},
        # second: model answers using the result
        {"content": "The file contains HELLO.", "thinking": "", "tool_calls": [], "finish_reason": "stop"},
    ]
    monkeypatch.setattr(web_app, "_call_model", lambda history: responses.pop(0))
    monkeypatch.setattr(
        web_app, "_execute_tool_with_approval",
        lambda name, args, write_event=None: "HELLO",
    )

    text, _thinking, tools_done = web_app._run_agent_loop(
        [{"role": "user", "content": "read a.py"}]
    )

    # the turn's response accumulates the pre-tool call note + the final text
    assert text.endswith("The file contains HELLO.")
    assert len(tools_done) == 1
    # the exchange was persisted (assistant tool_calls + tool result)
    msgs = web_app.STATE["messages"]
    assert msgs[-2]["role"] == "assistant" and msgs[-2]["tool_calls"]
    assert msgs[-1]["role"] == "tool" and msgs[-1]["content"] == "HELLO"


# ── the payoff: next turn sees the previous turn's tool context ──────────────

def test_next_turn_sees_previous_tool_context(monkeypatch):
    _clear_state(monkeypatch)

    tc = [{"name": "read_file", "arguments": {"path": "a.py"}, "id": "call_0"}]
    web_app.STATE["messages"].extend([
        {"role": "user", "content": "read a.py"},
        # a completed exchange from turn 1, persisted:
        {"role": "assistant", "content": "reading",
         "tool_calls": [{"function": {"name": "read_file", "arguments": {"path": "a.py"}}}]},
        {"role": "tool", "name": "read_file", "content": "def hello(): pass",
         "tool_call_id": "call_0"},
        {"role": "assistant", "content": "It defines hello()."},
        # turn 2 begins
        {"role": "user", "content": "what does a.py define?"},
    ])

    messages = web_app._build_api_messages("SYSTEM", compact=True)

    # the tool result from turn 1 must be in the model input for turn 2
    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    assert tool_msgs, "previous tool result should be in context"
    assert any("def hello(): pass" in m["content"] for m in tool_msgs)
    # and it is paired: its assistant tool_calls message is also present
    assert any(
        m.get("role") == "assistant" and m.get("tool_calls") for m in messages
    )


# ── _build_api_messages keeps exchanges intact under the budget ──────────────

def test_budget_keeps_exchange_intact(monkeypatch):
    _clear_state(monkeypatch)
    # A tiny budget so truncation kicks in, but the exchange must stay whole.
    monkeypatch.setitem(web_app.STATE, "context_token_budget", 6_000)

    web_app.STATE["messages"].extend([
        {"role": "user", "content": "turn 1"},
        {"role": "assistant", "content": "reading",
         "tool_calls": [{"function": {"name": "read_file", "arguments": {"path": "a.py"}}}]},
        {"role": "tool", "name": "read_file", "content": "X" * 4000, "tool_call_id": "call_0"},
        {"role": "assistant", "content": "done."},
    ])

    messages = web_app._build_api_messages("SYSTEM", compact=True)
    body = messages[1:]  # drop leading system

    # invariant: no tool message appears without an assistant tool_calls
    # immediately preceding it
    for i, m in enumerate(body):
        if m.get("role") == "tool":
            prev = body[i - 1]
            assert prev.get("role") == "assistant" and prev.get("tool_calls"), (
                f"tool response at {i} orphaned from its tool_calls"
            )


def test_budget_drops_whole_exchange_not_half(monkeypatch):
    _clear_state(monkeypatch)
    # Budget too small to fit the exchange: it must be dropped, not split.
    monkeypatch.setitem(web_app.STATE, "context_token_budget", 4_500)

    web_app.STATE["messages"].extend([
        {"role": "user", "content": "turn 1"},
        {"role": "assistant", "content": "reading",
         "tool_calls": [{"function": {"name": "read_file", "arguments": {"path": "a.py"}}}]},
        {"role": "tool", "name": "read_file", "content": "X" * 4000, "tool_call_id": "call_0"},
        {"role": "assistant", "content": "done."},
    ])

    messages = web_app._build_api_messages("SYSTEM", compact=True)
    body = messages[1:]

    # the oversized exchange is either fully present or fully absent
    has_tool = any(m.get("role") == "tool" for m in body)
    has_call = any(m.get("role") == "assistant" and m.get("tool_calls") for m in body)
    assert has_tool == has_call, "exchange must be selected as a unit"


def test_leading_orphan_tool_is_dropped(monkeypatch):
    _clear_state(monkeypatch)
    # The recent window may begin mid-exchange (leading tool message whose
    # assistant tool_calls fell out of the window). It must be dropped.
    web_app.STATE["messages"].extend([
        {"role": "tool", "name": "read_file", "content": "ORPHAN", "tool_call_id": "call_0"},
        {"role": "assistant", "content": "final answer."},
    ])

    messages = web_app._build_api_messages("SYSTEM", compact=True)
    body = [m for m in messages if m.get("role") != "system"]

    # no orphaned leading tool message
    assert body, "body should not be empty"
    assert body[0].get("role") != "tool" or body[0].get("tool_calls")
    assert not any(m.get("content") == "ORPHAN" for m in body if m.get("role") == "tool")


# ── _message_for_context preserves tool_call_id (needed for strict APIs) ─────

def test_message_for_context_keeps_tool_call_id():
    out = web_app._message_for_context(
        {"role": "tool", "name": "read_file", "content": "body", "tool_call_id": "call_9"}
    )
    assert out["role"] == "tool"
    assert out["tool_call_id"] == "call_9"
    assert out["content"] == "body"


def test_message_for_context_keeps_assistant_tool_calls():
    out = web_app._message_for_context(
        {"role": "assistant", "content": "reading",
         "tool_calls": [{"function": {"name": "read_file", "arguments": {}}}]},
    )
    assert out["tool_calls"]
