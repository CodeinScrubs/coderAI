"""
context_builder.py - RAG context, prompt building, and token estimation helpers.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable


DEFAULT_CONTEXT_TOKEN_BUDGET = 32_000
DEFAULT_RESPONSE_TOKEN_BUDGET = 4_096
MAX_HISTORY_MESSAGE_CHARS = 12_000
MAX_ASSISTANT_HISTORY_CHARS = 18_000
MAX_KEPT_HISTORY_MESSAGES = 14


def clip_for_context(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = max(0, limit // 2)
    tail = max(0, limit - head - 120)
    tail_text = text[-tail:] if tail > 0 else ""
    return (
        text[:head]
        + f"\n\n...[context clipped: {len(text) - head - tail:,} chars omitted]...\n\n"
        + tail_text
    )


def compact_tool_output(content: str, max_chars: int = 1500, tool_name: str = "") -> str:
    """Compacts voluminous tool output (e.g. large file reads or command logs) while preserving key facts."""
    if not content or len(content) <= max_chars:
        return content

    # Try parsing structured JSON
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            # For file read operations
            if "content" in data and isinstance(data["content"], str) and len(data["content"]) > max_chars:
                lines = data["content"].splitlines()
                if len(lines) > 30:
                    preview = "\n".join(lines[:15]) + f"\n\n... [{len(lines) - 30} lines hidden for context economy] ...\n\n" + "\n".join(lines[-15:])
                else:
                    head = data["content"][:max_chars // 2]
                    tail = data["content"][-(max_chars // 2):]
                    preview = head + f"\n\n... [{len(data['content']) - max_chars} chars omitted] ...\n\n" + tail
                data["content"] = preview
                data["_compacted"] = True
                return json.dumps(data, ensure_ascii=False)
            # For bash command stdout
            if "stdout" in data and isinstance(data["stdout"], str) and len(data["stdout"]) > max_chars:
                out = data["stdout"]
                head = out[:max_chars // 2]
                tail = out[-(max_chars // 2):]
                data["stdout"] = head + f"\n\n... [{len(out) - max_chars} chars truncated] ...\n\n" + tail
                data["_compacted"] = True
                return json.dumps(data, ensure_ascii=False)
    except Exception:
        pass

    # Generic string clipping
    return clip_for_context(content, max_chars)


def adaptive_compact_messages(
    messages: list[dict],
    token_budget: int = DEFAULT_CONTEXT_TOKEN_BUDGET,
    model: str = "",
    keep_recent_full_turns: int = 2,
) -> list[dict]:
    """Adaptively compacts tool outputs and older turns to stay well within token_budget."""
    if not messages:
        return []

    compacted: list[dict] = []
    total_messages = len(messages)

    for idx, msg in enumerate(messages):
        is_recent = idx >= total_messages - (keep_recent_full_turns * 2)
        role = msg.get("role", "")
        content = msg.get("content", "")

        msg_copy = dict(msg)

        if role == "tool" or ("tool_calls" in msg and not is_recent):
            char_limit = 3500 if is_recent else 800
            msg_copy["content"] = compact_tool_output(content, max_chars=char_limit)
        elif role == "assistant" and not is_recent:
            msg_copy["content"] = clip_for_context(content, limit=MAX_ASSISTANT_HISTORY_CHARS // 2)
        elif role == "user" and not is_recent:
            msg_copy["content"] = clip_for_context(content, limit=MAX_HISTORY_MESSAGE_CHARS // 2)

        compacted.append(msg_copy)

    return compacted


_TIKTOKEN_CACHE: dict[str, Any] = {}


def _get_tiktoken_encoding(model: str = "") -> Any:
    global _TIKTOKEN_CACHE
    key = (model or "").lower().strip()
    if key in _TIKTOKEN_CACHE:
        return _TIKTOKEN_CACHE[key]
    try:
        import tiktoken
        if key:
            try:
                enc = tiktoken.encoding_for_model(key)
                _TIKTOKEN_CACHE[key] = enc
                return enc
            except Exception:
                pass
        if "cl100k_base" not in _TIKTOKEN_CACHE:
            _TIKTOKEN_CACHE["cl100k_base"] = tiktoken.get_encoding("cl100k_base")
        _TIKTOKEN_CACHE[key] = _TIKTOKEN_CACHE["cl100k_base"]
        return _TIKTOKEN_CACHE[key]
    except Exception:
        return None


def estimate_tokens_for_messages(messages: list[dict], model: str = "", litellm_counter: Callable | None = None) -> int:
    if litellm_counter:
        try:
            return int(litellm_counter(model=model, messages=messages))
        except Exception:
            pass
    enc = _get_tiktoken_encoding(model)
    if enc is not None:
        try:
            num_tokens = 3
            for message in messages:
                num_tokens += 3
                content = str(message.get("content", "") or "")
                num_tokens += len(enc.encode(content, disallowed_special=()))
                if "name" in message:
                    num_tokens += len(enc.encode(str(message["name"]), disallowed_special=()))
                if "tool_calls" in message:
                    num_tokens += len(enc.encode(str(message["tool_calls"]), disallowed_special=()))
            return max(1, num_tokens)
        except Exception:
            pass
    chars = sum(len(str(message.get("content", ""))) + 24 for message in messages)
    return max(1, chars // 4)


def estimate_tokens_for_text(text: str, model: str = "") -> int:
    if not text:
        return 0
    enc = _get_tiktoken_encoding(model)
    if enc is not None:
        try:
            return max(1, len(enc.encode(text, disallowed_special=())))
        except Exception:
            pass
    return max(1, len(text or "") // 4)


def fast_tokens_for_messages(messages: list[dict], model: str = "") -> int:
    return estimate_tokens_for_messages(messages, model=model)


def get_model_context_window(
    model: str,
    configured_budget: int = DEFAULT_CONTEXT_TOKEN_BUDGET,
    conn_mode: str = "",
    litellm_counter: Callable | None = None,
    litellm_cost_map: dict | None = None,
) -> tuple[int, str]:
    cleaned = (model or "").strip()
    budget = max(4_000, int(configured_budget or DEFAULT_CONTEXT_TOKEN_BUDGET))

    if litellm_counter and litellm_cost_map:
        candidates = [cleaned]
        if conn_mode == "🖥️ Local Ollama" and not cleaned.startswith("ollama/"):
            candidates.append(f"ollama/{cleaned}")
        for candidate in candidates:
            try:
                info = litellm_cost_map.get(candidate, {}) or {}
                max_input = int(info.get("max_input_tokens") or 0)
                if max_input > 0:
                    return max_input, "litellm"
            except Exception:
                pass

    lower = cleaned.lower()
    known_windows = {
        "gpt-4o": 128_000,
        "gpt-4o-mini": 128_000,
        "gpt-4.1": 1_000_000,
        "gpt-4.1-mini": 1_000_000,
        "gpt-4.1-nano": 1_000_000,
        "gpt-5": 400_000,
        "gpt-5-mini": 400_000,
        "gpt-5-nano": 400_000,
        "claude-3.5": 200_000,
        "claude-3-5": 200_000,
        "claude-3.7": 200_000,
        "claude-3-7": 200_000,
        "claude-sonnet-4": 200_000,
        "claude-opus-4": 200_000,
        "gemini-1.5": 1_000_000,
        "gemini-2.5": 1_000_000,
        "llama3.1": 128_000,
        "llama3.2": 128_000,
        "llama3.3": 128_000,
        "qwen2.5": 128_000,
        "qwen3": 128_000,
        "gemma4": 128_000,
        "gemma3": 128_000,
        "gpt-oss": 128_000,
    }
    for marker, window in known_windows.items():
        if marker in lower:
            return window, "estimated"
    return budget, "configured"


def message_summary_line(message: dict) -> str:
    role = message.get("role", "user")
    content = " ".join(str(message.get("content", "")).split())
    return f"- {role}: {clip_for_context(content, 700)}"
