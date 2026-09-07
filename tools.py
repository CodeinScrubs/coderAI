"""
tools.py - tool definitions and execution helpers.

The workspace path is mutable. Each tool resolves the current path through
get_workspace() before reading or writing files.
"""

import os
import sys
import subprocess
import json
import uuid
import re
import threading
import urllib.request
import urllib.error
import urllib.parse
import ipaddress
import socket
from pathlib import Path
from datetime import datetime
from typing import Callable

from git_manager import GitManager
from codebase_index import CodebaseIndex, IncrementalIndexer
from workspace_filter import iter_workspace_files, walk_workspace
from sandbox_runner import SandboxRunner
from approval_policy import policy_manager

MAX_OUTPUT_CHARS = 8_000
EXEC_TIMEOUT     = 15
TAVILY_ENABLED = os.getenv("TAVILY_ENABLED", "false").lower() == "true"
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
SANDBOX_MODE = os.getenv("SANDBOX_MODE", "auto")
SANDBOX_DOCKER_IMAGE = os.getenv("SANDBOX_DOCKER_IMAGE", "python:3.11-slim")

# Default workspace used before the user selects a project folder.
_DEFAULT_WORKSPACE = Path(os.getenv("AGENT_WORKSPACE", "./agent_workspace")).resolve()
_DEFAULT_WORKSPACE.mkdir(parents=True, exist_ok=True)

# Updated whenever the user changes the active workspace.
WORKSPACE_DIR: Path = _DEFAULT_WORKSPACE
GIT_APPROVAL_MODE = True
_tool_event_sink: Callable[[dict], None] | None = None


def set_sandbox_config(mode: str = "auto", docker_image: str = "python:3.11-slim") -> None:
    global SANDBOX_MODE, SANDBOX_DOCKER_IMAGE
    SANDBOX_MODE = str(mode or "auto").lower()
    SANDBOX_DOCKER_IMAGE = str(docker_image or "python:3.11-slim")


def set_git_config(approval_mode: bool = True) -> None:
    global GIT_APPROVAL_MODE
    GIT_APPROVAL_MODE = bool(approval_mode)


def set_tool_event_sink(sink: Callable[[dict], None] | None) -> None:
    global _tool_event_sink
    _tool_event_sink = sink


def _emit_tool_event(event: dict) -> None:
    if _tool_event_sink:
        _tool_event_sink(event)


_active_processes: set[subprocess.Popen] = set()
_process_lock = threading.Lock()
_cancel_event = threading.Event()


def is_execution_cancelled() -> bool:
    return _cancel_event.is_set()


def reset_cancel_flag() -> None:
    _cancel_event.clear()


def cancel_current_execution() -> bool:
    _cancel_event.set()
    with _process_lock:
        killed_any = False
        for proc in list(_active_processes):
            try:
                _kill_proc_tree(proc)
                killed_any = True
            except Exception:
                pass
        _active_processes.clear()
        return killed_any


def _register_process(proc: subprocess.Popen) -> None:
    with _process_lock:
        _active_processes.add(proc)


def _unregister_process(proc: subprocess.Popen) -> None:
    with _process_lock:
        _active_processes.discard(proc)


def _kill_proc_tree(proc: subprocess.Popen) -> None:
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=5,
            )
        else:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _update_code_index(path: str, deleted: bool = False) -> None:
    try:
        indexer = IncrementalIndexer(CodebaseIndex(get_workspace()))
        result = indexer.on_file_changed(path)
        _emit_tool_event({"type": "code_index_updated", "path": path, "deleted": deleted, "chunks": result.get("chunks", 0), "result": result})
    except Exception as exc:
        _emit_tool_event({"type": "code_index_error", "path": path, "message": str(exc)})


# ══════════════════════════════════════════════════════════════════════════════
# ── Execution Approval State
# ══════════════════════════════════════════════════════════════════════════════

class ToolApprovalRequired(Exception):
    """Raised when a tool call requires explicit user approval before execution."""
    def __init__(self, tool_name: str, arguments: dict, preview: str):
        self.tool_name = tool_name
        self.arguments = arguments
        self.preview = preview
        super().__init__(f"Approval required for {tool_name}")


_approval_state: dict = {
    "pending": False,
    "tool_name": "",
    "arguments": {},
    "preview": "",
    "approved": False,
    "rejected": False,
    "rejection_reason": "",
    "always_allow": False,
}


def get_approval_state() -> dict:
    """Return a copy of the current approval state."""
    return dict(_approval_state)


def approve_pending(always_allow_for_session: bool = False) -> None:
    """Mark the pending approval request as approved."""
    global _approval_state
    _approval_state["approved"] = True
    _approval_state["rejected"] = False
    _approval_state["pending"] = False
    if always_allow_for_session:
        _approval_state["always_allow"] = True


def reject_pending(reason: str = "") -> None:
    """Mark the pending approval request as rejected."""
    global _approval_state
    _approval_state["rejected"] = True
    _approval_state["approved"] = False
    _approval_state["pending"] = False
    _approval_state["rejection_reason"] = reason or ""


def clear_approval_state() -> None:
    """Reset approval state (call on chat reset)."""
    global _approval_state
    _approval_state = {
        "pending": False,
        "tool_name": "",
        "arguments": {},
        "preview": "",
        "approved": False,
        "rejected": False,
        "rejection_reason": "",
        "always_allow": False,
    }


def _request_approval(tool_name: str, arguments: dict, preview: str) -> None:
    """Set pending approval state and raise ToolApprovalRequired."""
    global _approval_state
    _approval_state["pending"] = True
    _approval_state["tool_name"] = tool_name
    _approval_state["arguments"] = arguments
    _approval_state["preview"] = preview
    _approval_state["approved"] = False
    _approval_state["rejected"] = False
    _approval_state["rejection_reason"] = ""
    raise ToolApprovalRequired(tool_name, arguments, preview)


def set_workspace(path: str | Path) -> tuple[bool, str]:
    """
    Change the active workspace.
    Returns: (success, message)
    """
    global WORKSPACE_DIR
    p = Path(path).resolve()
    if not p.exists():
        return False, f"Path does not exist: {p}"
    if not p.is_dir():
        return False, f"Path is not a folder: {p}"
    WORKSPACE_DIR = p
    return True, str(p)


def get_workspace() -> Path:
    return WORKSPACE_DIR


def set_tavily_config(enabled: bool, api_key: str = "") -> None:
    global TAVILY_ENABLED, TAVILY_API_KEY
    TAVILY_ENABLED = bool(enabled)
    TAVILY_API_KEY = api_key.strip()


def tavily_configured() -> bool:
    return bool(TAVILY_ENABLED and TAVILY_API_KEY)


# ══════════════════════════════════════════════════════════════════════════════
# ── Tool Schemas
# ══════════════════════════════════════════════════════════════════════════════

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a text file from the active workspace. Supports LeanCTX surgical windowing (start_line, end_line) and compression modes ('raw', 'clean', 'outline') to conserve tokens.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to the workspace"},
                    "start_line": {"type": "integer", "description": "Optional starting line number (1-indexed)"},
                    "end_line": {"type": "integer", "description": "Optional ending line number (1-indexed)"},
                    "mode": {"type": "string", "enum": ["raw", "clean", "outline"], "description": "Reading mode: 'raw' (default), 'clean' (strips comments/blank lines), or 'outline' (structural class/function signatures with line numbers)"}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write or overwrite a text file in the active workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":    {"type": "string", "description": "File path relative to the workspace"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and folders in the active workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob filter. Default: **/*",
                        "default": "**/*",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": f"Run a shell command in the active workspace. Timeout: {EXEC_TIMEOUT}s",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to run"}
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "Run a Python code snippet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code"}
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch text content from a public URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url":       {"type": "string",  "description": "URL to fetch"},
                    "max_chars": {"type": "integer", "description": "Maximum characters to return. Default: 4000", "default": 4000},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web with Tavily and return summarized results, URLs, and snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "description": "Number of results. Default: 5", "default": 5},
                    "search_depth": {
                        "type": "string",
                        "description": "Search depth: basic or advanced",
                        "enum": ["basic", "advanced"],
                        "default": "basic",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_url",
            "description": "Extract clean content from one or more URLs with Tavily.",
            "parameters": {
                "type": "object",
                "properties": {
                    "urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "URLs to extract",
                    },
                    "max_chars": {"type": "integer", "description": "Maximum output characters", "default": 8000},
                },
                "required": ["urls"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search workspace files for text or a regex pattern.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Text or regex to search for"},
                    "pattern": {"type": "string", "description": "File glob. Default: **/*", "default": "**/*"},
                    "regex": {"type": "boolean", "description": "Treat query as a regex when true", "default": False},
                    "max_matches": {"type": "integer", "description": "Maximum number of matches", "default": 80},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_many_files",
            "description": "Read multiple text files from the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Relative file paths",
                    },
                    "max_chars_each": {"type": "integer", "description": "Maximum characters per file", "default": 6000},
                },
                "required": ["paths"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "replace_in_file",
            "description": "Replace exact text or regex matches in a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to the workspace"},
                    "old": {"type": "string", "description": "Existing text or regex"},
                    "new": {"type": "string", "description": "Replacement text"},
                    "regex": {"type": "boolean", "description": "Treat old as a regex when true", "default": False},
                    "count": {"type": "integer", "description": "Replacement count. 0 means all matches", "default": 0},
                },
                "required": ["path", "old", "new"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "append_file",
            "description": "Append text to a file in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "content": {"type": "string", "description": "Content to append"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_directory",
            "description": "Create a directory inside the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path relative to the workspace"}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "project_tree",
            "description": "Return a compact project tree with configurable depth.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_depth": {"type": "integer", "description": "Tree depth", "default": 3},
                    "max_entries": {"type": "integer", "description": "Maximum entries", "default": 300},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "current_time",
            "description": "Return the backend system time.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file from the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_codebase",
            "description": "Hybrid semantic and exact-keyword search over indexed code chunks. Use for a specific function, class, file, behavior, or implementation question. Use get_project_overview for whole-project purpose or architecture questions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Code symbol, filename, behavior, or implementation concept to find"},
                    "top_k": {"type": "integer", "description": "Maximum relevant code chunks", "default": 5}
                },
                "required": ["query"]
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_overview",
            "description": "Return the indexed project purpose, architecture summary, likely entry points, key file summaries, and dependency graph statistics. Use this for questions about the whole project, its structure, or how major modules collaborate.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_related_files",
            "description": "Return files connected to a specified file through resolved imports or function calls, including relation details and file summaries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Workspace-relative source file path"},
                    "depth": {"type": "integer", "description": "Graph traversal depth, usually 1 or 2", "default": 1}
                },
                "required": ["path"]
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scan_project",
            "description": (
                "Build a project scan report with file lists, detected languages, "
                "dependency/config files such as package.json or requirements.txt, "
                "and high-level statistics. Use this when starting work on a new project."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "max_files": {
                        "type": "integer",
                        "description": "Maximum files to scan. Default: 200",
                        "default": 200,
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember_fact",
            "description": "Store an important fact, architectural decision, user preference, or bug solution into long-term project memory (Hindsight).",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The information, observation, or lesson to retain.",
                    },
                    "context": {
                        "type": "string",
                        "description": "Optional context or category (e.g. 'architecture', 'user_preference', 'bug_fix').",
                    },
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_memory",
            "description": "Search long-term project memories, previous decisions, and past experiences using hybrid retrieval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query or concept to recall.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of memories to recall (default 5).",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reflect_memory",
            "description": "Synthesize patterns, risks, or deep conclusions from the project's cumulative memory (Hindsight reflection).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The question or topic to reflect upon (e.g. 'What are the main architectural patterns in this project?').",
                    },
                },
                "required": ["query"],
            },
        },
    },
]


# ══════════════════════════════════════════════════════════════════════════════
# ── Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _safe_path(rel_path: str) -> Path:
    ws = get_workspace()
    target = (ws / rel_path).resolve()
    try:
        target.relative_to(ws.resolve())
    except ValueError:
        raise PermissionError(f"Access outside the workspace is not allowed: {rel_path}")
    return target


def _is_probably_text(path: Path, sample_size: int = 2048) -> bool:
    try:
        sample = path.read_bytes()[:sample_size]
        if b"\x00" in sample:
            return False
        sample.decode("utf-8", errors="strict")
        return True
    except Exception:
        return False


def _tavily_post(endpoint: str, payload: dict) -> dict:
    if not TAVILY_ENABLED:
        return {"error": "Tavily web search is disabled in Settings."}
    if not TAVILY_API_KEY:
        return {"error": "Tavily API key is empty. Enable Tavily and add an API key in Settings."}
    errors = []
    auth_attempts = [
        (payload, {"Authorization": f"Bearer {TAVILY_API_KEY}"}),
        ({"api_key": TAVILY_API_KEY, **payload}, {}),
    ]
    for body_payload, extra_headers in auth_attempts:
        body = json.dumps(body_payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.tavily.com/{endpoint}",
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Ollama-Agentic-Workspace/1.0",
                **extra_headers,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            errors.append(f"HTTP {exc.code}: {detail[:600]}")
        except Exception as exc:
            errors.append(str(exc))
    return {"error": "Tavily request failed. " + " | ".join(errors)}


# ══════════════════════════════════════════════════════════════════════════════
# ── Tool Handlers
# ══════════════════════════════════════════════════════════════════════════════

def tool_read_file(
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
    mode: str = "raw",
) -> str:
    try:
        p = _safe_path(path)
        if not p.exists():
            return f"File does not exist: {path}"
        content = p.read_text(encoding="utf-8", errors="replace")

        # LeanCTX outline/map mode
        mode_str = str(mode or "raw").lower()
        if mode_str in {"outline", "map"}:
            from context_builder import extract_code_outline
            return extract_code_outline(content, file_path=path)

        # LeanCTX clean/aggressive mode (strips comments and redundant whitespace)
        if mode_str in {"clean", "aggressive"}:
            from context_builder import compress_source_code
            content = compress_source_code(content, mode="clean")

        lines = content.splitlines()
        total_lines = len(lines)

        # Surgical line windowing
        if start_line is not None or end_line is not None:
            s = max(1, int(start_line or 1))
            e = min(total_lines, int(end_line or total_lines))
            if s > total_lines:
                return f"Requested start_line {s} exceeds total lines ({total_lines}) in {path}."
            selected = lines[s - 1:e]
            numbered = [f"{i}: {line}" for i, line in enumerate(selected, s)]
            result = f"--- {path} (lines {s}-{e} of {total_lines}) ---\n" + "\n".join(numbered)
            if len(result) > MAX_OUTPUT_CHARS:
                result = result[:MAX_OUTPUT_CHARS] + f"\n\n... [truncated - {len(result)} characters]"
            return result

        if len(content) > MAX_OUTPUT_CHARS:
            content = content[:MAX_OUTPUT_CHARS] + f"\n\n... [truncated - {len(content)} total characters. Use start_line/end_line for surgical reading]"
        return content
    except Exception as e:
        return f"Error: {e}"


def tool_write_file(path: str, content: str) -> str:
    try:
        p = _safe_path(path)
        manager = GitManager(get_workspace())
        ws = get_workspace()
        arguments = {"path": path, "content": content}
        req_approval, reason, _ = policy_manager.should_require_approval("write_file", arguments, ws)
        if not GIT_APPROVAL_MODE:
            req_approval = False

        if req_approval and not _approval_state["always_allow"]:
            preview = manager.get_diff_preview(path, content) if manager.is_repo() else f"Create/overwrite file: {path} ({len(content)} bytes)"
            if not _approval_state["approved"] or _approval_state["tool_name"] != "write_file":
                _request_approval("write_file", arguments, preview)
            _approval_state["approved"] = False
            _approval_state["tool_name"] = ""
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        _update_code_index(path)
        commit_hash = ""
        if manager.is_repo():
            commit_hash = manager.stage_and_commit([path], f"Update {path} with CoderAI")
            if commit_hash:
                _emit_tool_event({"type": "git_commit_created", "commit": commit_hash, "message": f"Update {path} with CoderAI", "files": [path]})
        suffix = f"; committed as {commit_hash[:8]}" if commit_hash else ""
        return f"File written: {path} ({p.stat().st_size:,} bytes){suffix}"
    except Exception as e:
        return f"Error: {e}"


def tool_list_files(pattern: str = "**/*") -> str:
    try:
        ws = get_workspace()
        IGNORE = {'.git', '.agent_memory', '__pycache__', 'node_modules', '.venv', 'venv', '.idea', '.vscode', 'dist', 'build', '.next'}
        matches = []
        for p in sorted(ws.glob(pattern)):
            parts = p.relative_to(ws).parts
            if any(part in IGNORE for part in parts):
                continue
            matches.append(p)

        if not matches:
            return "Workspace is empty."

        lines = []
        for p in matches[:300]:
            rel = p.relative_to(ws)
            if p.is_dir():
                lines.append(f"📁 {rel}/")
            else:
                size  = p.stat().st_size
                mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%m/%d %H:%M")
                lines.append(f"📄 {rel}  ({size:,}b, {mtime})")
        if len(matches) > 300:
            lines.append(f"\n... and {len(matches)-300} more files")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


_DANGEROUS_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\brm\s+(-[rfRF]{1,4}\s+)?(/\s*$|/\*|~\s*$|\$HOME\b)", re.IGNORECASE), "Root / home directory deletion"),
    (re.compile(r"\b(rd|rmdir)\s+/[sS]\s+/[qQ]\s+[cC]:\\?", re.IGNORECASE), "C:\\ drive root directory wipe"),
    (re.compile(r"\bdel\s+/[fF]\s+/[sS]\s+/[qQ]\s+[cC]:\\?", re.IGNORECASE), "C:\\ drive root file wipe"),
    (re.compile(r"\bformat\s+[a-zA-Z]:", re.IGNORECASE), "Drive format command"),
    (re.compile(r"\bmkfs(\.\w+)?\b", re.IGNORECASE), "Filesystem format command"),
    (re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", re.IGNORECASE), "Fork bomb"),
    (re.compile(r"\b(shutdown|reboot|poweroff|init\s+[06])\b", re.IGNORECASE), "System shutdown / reboot command"),
]

_SENSITIVE_ENV_KEYS = {
    "CUSTOM_API_KEY",
    "TAVILY_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "AWS_SECRET_ACCESS_KEY",
    "GITHUB_TOKEN",
    "GIT_PASSWORD",
    "LD_PRELOAD",
    "DYLD_INSERT_LIBRARIES",
}


def _is_destructive_command(command: str) -> tuple[bool, str]:
    cmd_clean = command.strip()
    for pattern, description in _DANGEROUS_PATTERNS:
        if pattern.search(cmd_clean):
            return True, description
    return False, ""


def _get_sanitized_env() -> dict[str, str]:
    env = dict(os.environ)
    for key in _SENSITIVE_ENV_KEYS:
        env.pop(key, None)
    env["PYTHONPATH"] = str(get_workspace().resolve())
    return env


def tool_run_bash(command: str) -> str:
    if is_execution_cancelled():
        return "Execution cancelled by user."
    is_dangerous, danger_reason = _is_destructive_command(command)
    if is_dangerous:
        return f"Security Error: Command blocked due to potentially destructive system operation ({danger_reason})."
    ws = get_workspace()
    arguments = {"command": command}
    req_approval, reason, _ = policy_manager.should_require_approval("run_bash", arguments, ws)

    if req_approval and not _approval_state["always_allow"]:
        if not _approval_state["approved"] or _approval_state["tool_name"] != "run_bash":
            _request_approval("run_bash", arguments, command)
        # Clear approval flag after consuming it
        _approval_state["approved"] = False
        _approval_state["tool_name"] = ""
    if _approval_state.get("rejected"):
        reason = _approval_state.get("rejection_reason") or "User rejected execution."
        _approval_state["rejected"] = False
        return f"Execution rejected: {reason}"

    runner = SandboxRunner(
        workspace_path=get_workspace(),
        mode=SANDBOX_MODE,
        docker_image=SANDBOX_DOCKER_IMAGE,
        timeout_seconds=EXEC_TIMEOUT,
    )
    result = runner.run_bash_command(
        command=command,
        env=_get_sanitized_env(),
        process_register_cb=_register_process,
    )
    parts = []
    if result.stdout and result.stdout.strip():
        parts.append(f"STDOUT:\n{result.stdout.strip()}")
    if result.stderr and result.stderr.strip():
        parts.append(f"STDERR:\n{result.stderr.strip()}")
    parts.append(f"exit code: {result.exit_code}")
    if result.used_sandbox == "docker":
        parts.append("(Executed inside Docker container sandbox)")
    output = "\n\n".join(parts)
    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + "\n... [truncated]"
    return output or "(empty output)"


def tool_run_python(code: str) -> str:
    if is_execution_cancelled():
        return "Execution cancelled by user."
    ws = get_workspace()
    arguments = {"code": code}
    req_approval, reason, _ = policy_manager.should_require_approval("run_python", arguments, ws)

    if req_approval and not _approval_state["always_allow"]:
        if not _approval_state["approved"] or _approval_state["tool_name"] != "run_python":
            _request_approval("run_python", arguments, code)
        # Clear approval flag after consuming it
        _approval_state["approved"] = False
        _approval_state["tool_name"] = ""
    if _approval_state.get("rejected"):
        reason = _approval_state.get("rejection_reason") or "User rejected execution."
        _approval_state["rejected"] = False
        return f"Execution rejected: {reason}"

    runner = SandboxRunner(
        workspace_path=get_workspace(),
        mode=SANDBOX_MODE,
        docker_image=SANDBOX_DOCKER_IMAGE,
        timeout_seconds=EXEC_TIMEOUT,
    )
    result = runner.run_python_code(
        code=code,
        env=_get_sanitized_env(),
        process_register_cb=_register_process,
    )
    parts = []
    if result.stdout and result.stdout.strip():
        parts.append(f"OUTPUT:\n{result.stdout.strip()}")
    if result.stderr and result.stderr.strip():
        parts.append(f"STDERR:\n{result.stderr.strip()}")
    parts.append(f"exit code: {result.exit_code}")
    if result.used_sandbox == "docker":
        parts.append("(Executed inside Docker container sandbox)")
    output = "\n\n".join(parts)
    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + "\n... [truncated]"
    return output or "(empty output)"


def _is_url_safe(url: str) -> tuple[bool, str]:
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False, f"Unsupported URL scheme: {parsed.scheme}"
        hostname = parsed.hostname
        if not hostname:
            return False, "Invalid URL hostname"
        if hostname.lower() in {"localhost", "127.0.0.1", "::1"}:
            return False, "Requests to localhost/loopback addresses are blocked"
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False, f"Requests to private/internal IP address {ip} are blocked"
        except ValueError:
            pass
        return True, ""
    except Exception as exc:
        return False, f"URL parse error: {exc}"


def tool_fetch_url(url: str, max_chars: int = 4000) -> str:
    try:
        safe, reason = _is_url_safe(url)
        if not safe:
            return f"Error: {reason}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
        enc  = resp.headers.get_content_charset() or "utf-8"
        text = raw.decode(enc, errors="replace")
        if len(text) > max_chars:
            text = text[:max_chars] + "\n... [truncated]"
        return text
    except Exception as e:
        return f"Error: {e}"


def tool_web_search(query: str, max_results: int = 5, search_depth: str = "basic") -> str:
    max_results = max(1, min(int(max_results or 5), 10))
    data = _tavily_post("search", {
        "query": query,
        "search_depth": search_depth if search_depth in {"basic", "advanced"} else "basic",
        "max_results": max_results,
        "include_answer": True,
        "include_raw_content": False,
    })
    if data.get("error"):
        return f"❌ {data['error']}"

    lines = [f"# Tavily search: {query}"]
    if data.get("answer"):
        lines += ["", "## Answer", str(data["answer"])]
    results = data.get("results", []) or []
    if results:
        lines += ["", "## Results"]
        for index, item in enumerate(results, 1):
            title = item.get("title") or "(untitled)"
            url = item.get("url") or ""
            content = (item.get("content") or "").strip()
            score = item.get("score")
            lines.append(f"{index}. {title}")
            if url:
                lines.append(f"   URL: {url}")
            if score is not None:
                lines.append(f"   Score: {score}")
            if content:
                lines.append(f"   Snippet: {content[:900]}")
    return "\n".join(lines)[:MAX_OUTPUT_CHARS]


def tool_extract_url(urls: list[str], max_chars: int = 8000) -> str:
    if isinstance(urls, str):
        urls = [urls]
    data = _tavily_post("extract", {
        "urls": urls,
        "extract_depth": "basic",
        "include_images": False,
    })
    if data.get("error"):
        return f"❌ {data['error']}"
    lines = ["# Tavily extract"]
    for item in data.get("results", []) or []:
        url = item.get("url") or ""
        content = item.get("raw_content") or item.get("content") or ""
        lines.append(f"\n## {url}\n{content[:max_chars]}")
    failed = data.get("failed_results", []) or []
    if failed:
        lines.append("\n## Failed")
        for item in failed:
            lines.append(json.dumps(item, ensure_ascii=False)[:1000])
    return "\n".join(lines)[:max_chars]


def tool_search_files(query: str, pattern: str = "**/*", regex: bool = False, max_matches: int = 80) -> str:
    try:
        ws = get_workspace()
        max_matches = max(1, min(int(max_matches or 80), 500))
        flags = re.IGNORECASE
        compiled = re.compile(query, flags) if regex else None
        ignore = {'.git', '.agent_memory', '__pycache__', 'node_modules', '.venv', 'venv', '.idea', '.vscode', 'dist', 'build', '.next'}
        matches = []
        for path in sorted(ws.glob(pattern or "**/*")):
            if not path.is_file():
                continue
            rel = path.relative_to(ws)
            if any(part in ignore for part in rel.parts) or not _is_probably_text(path):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for line_no, line in enumerate(text.splitlines(), 1):
                hit = compiled.search(line) if compiled else query.lower() in line.lower()
                if hit:
                    matches.append(f"{rel}:{line_no}: {line[:260]}")
                    if len(matches) >= max_matches:
                        return "\n".join(matches)
        return "\n".join(matches) if matches else "No matches found."
    except Exception as e:
        return f"Error: {e}"


def tool_read_many_files(paths: list[str], max_chars_each: int = 6000) -> str:
    if isinstance(paths, str):
        paths = [paths]
    max_chars_each = max(500, min(int(max_chars_each or 6000), 20000))
    chunks = []
    for path in paths[:20]:
        chunks.append(f"\n\n--- FILE: {path} ---\n{tool_read_file(path)[:max_chars_each]}")
    return "".join(chunks).strip() or "No files were provided."


def tool_replace_in_file(path: str, old: str, new: str, regex: bool = False, count: int = 0) -> str:
    try:
        p = _safe_path(path)
        if not p.exists():
            return f"File does not exist: {path}"
        text = p.read_text(encoding="utf-8", errors="replace")
        if regex:
            updated, changed = re.subn(old, new, text, count=max(0, int(count or 0)))
        else:
            changed = text.count(old) if int(count or 0) == 0 else min(text.count(old), int(count))
            updated = text.replace(old, new, int(count or 0))
        if updated == text:
            return f"No replacements were made: {path}"
        ws = get_workspace()
        arguments = {"path": path, "old": old, "new": new, "regex": regex, "count": count}
        req_approval, reason, _ = policy_manager.should_require_approval("replace_in_file", arguments, ws)
        if not GIT_APPROVAL_MODE:
            req_approval = False

        if req_approval and not _approval_state["always_allow"]:
            preview = manager.get_diff_preview(path, updated) if manager.is_repo() else f"Replace occurrences in {path}"
            if not _approval_state["approved"] or _approval_state["tool_name"] != "replace_in_file":
                _request_approval("replace_in_file", arguments, preview)
            _approval_state["approved"] = False
            _approval_state["tool_name"] = ""
        p.write_text(updated, encoding="utf-8")
        _update_code_index(path)
        commit_hash = ""
        if manager.is_repo():
            commit_hash = manager.stage_and_commit([path], f"Update {path} with CoderAI")
            if commit_hash:
                _emit_tool_event({"type": "git_commit_created", "commit": commit_hash, "message": f"Update {path} with CoderAI", "files": [path]})
        suffix = f" Committed as {commit_hash[:8]}." if commit_hash else ""
        return f"Replaced {changed} occurrence(s) in {path}.{suffix}"
    except Exception as e:
        return f"Error: {e}"


def tool_append_file(path: str, content: str) -> str:
    try:
        p = _safe_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(content)
        _update_code_index(path)
        return f"Appended to file: {path} ({p.stat().st_size:,} bytes)"
    except Exception as e:
        return f"Error: {e}"


def tool_create_directory(path: str) -> str:
    try:
        p = _safe_path(path)
        p.mkdir(parents=True, exist_ok=True)
        return f"Directory is ready: {path}"
    except Exception as e:
        return f"Error: {e}"


def tool_project_tree(max_depth: int = 3, max_entries: int = 300) -> str:
    try:
        ws = get_workspace()
        max_depth = max(1, min(int(max_depth or 3), 8))
        max_entries = max(20, min(int(max_entries or 300), 1000))
        ignore = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', '.idea', '.vscode', 'dist', 'build', '.next'}
        lines = [f"{ws.name}/"]
        count = 0
        for current, directories, files in walk_workspace(ws, ignore):
            rel_dir = current.relative_to(ws)
            if len(rel_dir.parts) >= max_depth:
                directories[:] = []
            entries = [(current / name, True) for name in directories] + [(current / name, False) for name in files]
            for path, is_dir in entries:
                rel = path.relative_to(ws)
                if len(rel.parts) > max_depth:
                    continue
                count += 1
                if count > max_entries:
                    lines.append("... more entries omitted")
                    return "\n".join(lines)
                indent = "  " * (len(rel.parts) - 1)
                lines.append(f"{indent}- {rel.name}{'/' if is_dir else ''}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def tool_current_time() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def tool_delete_file(path: str) -> str:
    try:
        p = _safe_path(path)
        if not p.exists():
            return f"File does not exist: {path}"
        p.unlink()
        _update_code_index(path, deleted=True)
        return f"Deleted: {path}"
    except Exception as e:
        return f"Error: {e}"


def tool_search_codebase(query: str, top_k: int = 5) -> str:
    try:
        index = CodebaseIndex(get_workspace())
        hits = index.retrieve_relevant_code(query, top_k)
        if not hits:
            status = index.status()
            if not status["files"]:
                return "Codebase index is empty. Build it from Files > Index before using search_codebase."
            return f"No indexed code matched: {query}"
        sections = [f"# Codebase search: {query}"]
        for number, hit in enumerate(hits, 1):
            symbol = f" · {hit['symbol_type']} `{hit['symbol_name']}`" if hit.get("symbol_name") else ""
            sections.append(
                f"\n## {number}. `{hit['file_path']}:{hit['start_line']}-{hit['end_line']}`{symbol}\n"
                f"```\n{hit['content'][:3500]}\n```"
            )
        return "\n".join(sections)[:MAX_OUTPUT_CHARS]
    except Exception as e:
        return f"Error: {e}"


def tool_get_project_overview() -> str:
    try:
        overview = CodebaseIndex(get_workspace()).get_project_overview()
        sections = ["# Project overview", overview["summary"]]
        if overview["key_files"]:
            sections.append("\n## Entry points and key files")
            sections.extend(f"- `{item['file_path']}`: {item['summary']}" for item in overview["key_files"])
        sections.append(f"\nGraph: {overview['nodes']} files, {overview['edges']} resolved dependency edges")
        return "\n".join(sections)[:MAX_OUTPUT_CHARS]
    except Exception as e:
        return f"Error: {e}"


def tool_get_related_files(path: str, depth: int = 1) -> str:
    try:
        related = CodebaseIndex(get_workspace()).get_related_files(path, max(1, min(int(depth), 3)))
        if not related:
            return f"No resolved import or call relations found for: {path}"
        sections = [f"# Files related to `{path}`"]
        for item in related:
            relations = ", ".join(
                f"{edge['relation_type']}:{edge['detail']} ({edge['from_file']} -> {edge['to_file']})"
                for edge in item["relations"]
            )
            sections.append(f"- `{item['file_path']}` — {relations}\n  {item['summary']}")
        return "\n".join(sections)[:MAX_OUTPUT_CHARS]
    except Exception as e:
        return f"Error: {e}"


def tool_scan_project(max_files: int = 200) -> str:
    """Build an initial project structure report."""
    ws = get_workspace()
    IGNORE = {'.git', '.agent_memory', '__pycache__', 'node_modules', '.venv', 'venv',
              '.idea', '.vscode', 'dist', 'build', '.next', '.mypy_cache'}

    all_files: list[Path] = []
    for p in sorted(iter_workspace_files(ws, IGNORE)):
        all_files.append(p)

    if not all_files:
        return "The project is empty."

    ext_count: dict[str, int] = {}
    for f in all_files:
        ext = f.suffix.lower() or "(no extension)"
        ext_count[ext] = ext_count.get(ext, 0) + 1

    CONFIG_FILES = {
        "requirements.txt", "pyproject.toml", "setup.py", "Pipfile",
        "package.json", "package-lock.json", "yarn.lock",
        "Cargo.toml", "go.mod", "pom.xml", "build.gradle",
        "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
        ".env.example", "Makefile", "README.md", "README.rst",
    }
    found_configs = [f for f in all_files if f.name in CONFIG_FILES]

    top_level: dict[str, list] = {}
    for f in all_files[:max_files]:
        rel   = f.relative_to(ws)
        parts = rel.parts
        key   = parts[0] if len(parts) > 1 else "."
        top_level.setdefault(key, []).append(rel)

    lines = [
        "# Project scan report",
        f"**Path:** `{ws}`",
        f"**Total files:** {len(all_files)}",
        "",
        "## Languages / file types",
    ]
    for ext, cnt in sorted(ext_count.items(), key=lambda x: -x[1])[:15]:
        lines.append(f"- `{ext}`: {cnt} file(s)")

    if found_configs:
        lines += ["", "## Detected configuration files"]
        for cf in found_configs:
            lines.append(f"- `{cf.relative_to(ws)}`")

    lines += ["", "## Main structure"]
    for folder, files in sorted(top_level.items()):
        lines.append(f"**{folder}/** - {len(files)} item(s)")

    if len(all_files) > max_files:
        lines.append(f"\n_(Showing only the first {max_files} files out of {len(all_files)} total.)_")

    return "\n".join(lines)


def tool_remember_fact(content: str, context: str = "") -> str:
    """Retain a key observation, rule, or architectural fact into long-term Hindsight memory."""
    try:
        from hindsight_manager import get_hindsight_manager
        hm = get_hindsight_manager()
        res = hm.retain(content=content, context=context)
        bank_id = res.get("bank_id", "default")
        if res.get("engine") == "hindsight":
            return f"Retained in Hindsight memory bank '{bank_id}': {content}"
        return f"Retained in local memory store (bank '{bank_id}'): {content}"
    except Exception as e:
        return f"Error storing memory: {e}"


def tool_recall_memory(query: str, limit: int = 5) -> str:
    """Recall relevant project memories, facts, and lessons using Hindsight hybrid search."""
    try:
        from hindsight_manager import get_hindsight_manager
        hm = get_hindsight_manager()
        res = hm.recall(query=query, max_tokens=2048)
        p_str = res.get("prompt_string", "")
        if p_str:
            return f"--- Recalled Memories ({res.get('engine')}, {res.get('count')} item(s)) ---\n{p_str}"
        return f"No memories found for query: '{query}'."
    except Exception as e:
        return f"Error recalling memory: {e}"


def tool_reflect_memory(query: str) -> str:
    """Synthesize deep lessons and project patterns using Hindsight reflection."""
    try:
        from hindsight_manager import get_hindsight_manager
        hm = get_hindsight_manager()
        return hm.reflect(query=query)
    except Exception as e:
        return f"Error reflecting on memory: {e}"


# ── Dispatcher ─────────────────────────────────────────────────────────────────
_HANDLERS: dict = {
    "read_file":    lambda a: tool_read_file(a["path"], a.get("start_line"), a.get("end_line"), a.get("mode", "raw")),
    "write_file":   lambda a: tool_write_file(a["path"], a["content"]),
    "list_files":   lambda a: tool_list_files(a.get("pattern", "**/*")),
    "run_bash":     lambda a: tool_run_bash(a["command"]),
    "run_python":   lambda a: tool_run_python(a["code"]),
    "fetch_url":    lambda a: tool_fetch_url(a["url"], a.get("max_chars", 4000)),
    "web_search":   lambda a: tool_web_search(a["query"], a.get("max_results", 5), a.get("search_depth", "basic")),
    "extract_url":  lambda a: tool_extract_url(a["urls"], a.get("max_chars", 8000)),
    "search_files": lambda a: tool_search_files(a["query"], a.get("pattern", "**/*"), a.get("regex", False), a.get("max_matches", 80)),
    "read_many_files": lambda a: tool_read_many_files(a["paths"], a.get("max_chars_each", 6000)),
    "replace_in_file": lambda a: tool_replace_in_file(a["path"], a["old"], a["new"], a.get("regex", False), a.get("count", 0)),
    "append_file":  lambda a: tool_append_file(a["path"], a["content"]),
    "create_directory": lambda a: tool_create_directory(a["path"]),
    "project_tree": lambda a: tool_project_tree(a.get("max_depth", 3), a.get("max_entries", 300)),
    "current_time": lambda a: tool_current_time(),
    "delete_file":  lambda a: tool_delete_file(a["path"]),
    "search_codebase": lambda a: tool_search_codebase(a["query"], a.get("top_k", 5)),
    "get_project_overview": lambda a: tool_get_project_overview(),
    "get_related_files": lambda a: tool_get_related_files(a["path"], a.get("depth", 1)),
    "scan_project": lambda a: tool_scan_project(a.get("max_files", 200)),
    "remember_fact":  lambda a: tool_remember_fact(a["content"], a.get("context", "")),
    "recall_memory":  lambda a: tool_recall_memory(a["query"], a.get("limit", 5)),
    "reflect_memory": lambda a: tool_reflect_memory(a["query"]),
}


def execute_tool(name: str, arguments: dict | str) -> str | dict:
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return f"Could not parse tool arguments: {arguments}"
    handler = _HANDLERS.get(name)
    if handler is None:
        return f"Unknown tool: {name}"
    try:
        return handler(arguments)
    except ToolApprovalRequired as exc:
        return json.dumps({
            "status": "approval_required",
            "tool_name": exc.tool_name,
            "arguments": exc.arguments,
            "preview": exc.preview,
        })
    except KeyError as e:
        return f"Missing required argument: {e}"
    except Exception as e:
        return f"Error in '{name}': {e}"
