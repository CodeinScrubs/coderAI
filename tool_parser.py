"""
tool_parser.py - Robust JSON Auto-Repair, Fuzzy Parser, and Fallback Tool Call Extractor
Specifically designed to handle outputs from smaller local LLMs (Ollama / Qwen / Llama / Gemma).
"""

from __future__ import annotations

import json
import re
from typing import Any


def repair_json_tool_arguments(raw: Any) -> dict[str, Any]:
    """Tolerantly parses and repairs malformed JSON arguments from model responses."""
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}

    text = raw.strip()

    # Fast path: valid standard JSON
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # Strip markdown codeblock fences (e.g., ```json ... ```)
    code_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if code_block_match:
        text = code_block_match.group(1).strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    # Extract JSON object substring between outer { and }
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        text = text[first_brace : last_brace + 1]

    # Heuristic repairs:
    repaired = text

    # 1. Replace Python-style literals
    repaired = re.sub(r"\bTrue\b", "true", repaired)
    repaired = re.sub(r"\bFalse\b", "false", repaired)
    repaired = re.sub(r"\bNone\b", "null", repaired)

    # 2. Remove trailing commas before closing braces/brackets
    repaired = re.sub(r",\s*([\]}])", r"\1", repaired)

    # 3. Fix unquoted keys, e.g. { path: "main.py", count: 5 }
    repaired = re.sub(r'([{,]\s*)([A-Za-z0-9_]+)\s*:', r'\1"\2":', repaired)

    # 4. Fix single-quoted keys and values
    # Replace 'key': with "key":
    repaired = re.sub(r"([{,]\s*)'([^']+)'\s*:", r'\1"\2":', repaired)
    # Replace : 'value' with : "value"
    repaired = re.sub(r":\s*'([^']*)'(\s*[,}])", r': "\1"\2', repaired)

    try:
        parsed = json.loads(repaired)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # Fallback: key-value regex extraction for common parameters
    extracted: dict[str, Any] = {}
    kv_pattern = re.compile(
        r'["\']?([A-Za-z0-9_]+)["\']?\s*[:=]\s*(?:"([^"]*)"|\'([^\']*)\'|([0-9]+(?:\.[0-9]+)?)|(true|false|null))',
        re.IGNORECASE,
    )
    for m in kv_pattern.finditer(text):
        key = m.group(1)
        val_str_d = m.group(2)
        val_str_s = m.group(3)
        val_num = m.group(4)
        val_bool = m.group(5)

        if val_str_d is not None:
            extracted[key] = val_str_d
        elif val_str_s is not None:
            extracted[key] = val_str_s
        elif val_num is not None:
            extracted[key] = float(val_num) if "." in val_num else int(val_num)
        elif val_bool is not None:
            b = val_bool.lower()
            extracted[key] = True if b == "true" else (False if b == "false" else None)

    return extracted


def extract_fallback_tool_calls_from_text(
    text: str, available_tool_names: set[str] | list[str]
) -> list[dict[str, Any]]:
    """Detects and extracts tool calls written in text when small models fail to use native function calling."""
    if not text or not text.strip():
        return []

    tools_set = set(available_tool_names)
    calls: list[dict[str, Any]] = []

    # Pattern 1: ```tool_call:tool_name\n{...}\n``` or ```tool:tool_name\n{...}\n```
    p1 = re.compile(r"```(?:tool_call|tool):([A-Za-z0-9_]+)\s*([\s\S]*?)\s*```", re.IGNORECASE)
    for m in p1.finditer(text):
        name = m.group(1).strip()
        body = m.group(2).strip()
        if name in tools_set:
            args = repair_json_tool_arguments(body)
            calls.append({"name": name, "arguments": args})

    if calls:
        return calls

    # Pattern 2: <tool_call>{"name": "...", "arguments": {...}}</tool_call>
    p2 = re.compile(r"<tool_call>([\s\S]*?)</tool_call>", re.IGNORECASE)
    for m in p2.finditer(text):
        body = m.group(1).strip()
        try:
            data = repair_json_tool_arguments(body)
            name = data.get("name")
            args = data.get("arguments", {})
            if isinstance(args, str):
                args = repair_json_tool_arguments(args)
            if name and name in tools_set:
                calls.append({"name": name, "arguments": args})
        except Exception:
            pass

    if calls:
        return calls

    # Pattern 3: Action: tool_name\nAction Input: {...}
    p3 = re.compile(
        r"(?:Action|Tool):\s*([A-Za-z0-9_]+)\s*(?:\n|\r\n)(?:Action Input|Tool Input|Arguments):\s*([\s\S]*?)(?=(?:\n\s*(?:Action|Tool):|\Z))",
        re.IGNORECASE,
    )
    for m in p3.finditer(text):
        name = m.group(1).strip()
        body = m.group(2).strip()
        if name in tools_set:
            args = repair_json_tool_arguments(body)
            calls.append({"name": name, "arguments": args})

    if calls:
        return calls

    # Pattern 4: tool_name({"path": "..."})
    for t_name in tools_set:
        pattern_str = r"\b" + re.escape(t_name) + r"\s*\(\s*(\{[\s\S]*?\})\s*\)"
        p4 = re.compile(pattern_str, re.IGNORECASE)
        for m in p4.finditer(text):
            body = m.group(1).strip()
            args = repair_json_tool_arguments(body)
            calls.append({"name": t_name, "arguments": args})

    return calls
