"""
code_graph_service.py - Code Review Graph (CRG) integration service.

Provides local-first AST code intelligence, blast-radius impact analysis,
hierarchical community architecture overviews, and token-optimized subgraphs
for large-scale projects and monorepos.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("code_graph_service")

try:
    import code_review_graph
    from code_review_graph.tools.build import build_or_update_graph
    from code_review_graph.tools.community_tools import get_architecture_overview_func
    from code_review_graph.tools.context import get_minimal_context
    from code_review_graph.tools.query import (
        get_impact_radius,
        list_graph_stats,
        query_graph,
    )
    CRG_AVAILABLE = True
except Exception as _crg_err:
    CRG_AVAILABLE = False
    build_or_update_graph = None  # type: ignore
    get_architecture_overview_func = None  # type: ignore
    get_minimal_context = None  # type: ignore
    get_impact_radius = None  # type: ignore
    list_graph_stats = None  # type: ignore
    query_graph = None  # type: ignore
    logger.warning("code-review-graph not available: %s", _crg_err)


class CodeGraphService:
    """Manages AST knowledge graph indexing, queries, and blast-radius analysis."""

    def __init__(self) -> None:
        self._available = CRG_AVAILABLE

    @property
    def is_available(self) -> bool:
        return self._available

    def _resolve_repo(self, workspace_path: str | Path | None) -> str:
        if workspace_path is None:
            p = Path.cwd().resolve()
        else:
            p = Path(workspace_path).resolve()
        # Ensure project root marker exists so CRG accepts non-git projects gracefully
        crg_dir = p / ".code-review-graph"
        if not (p / ".git").exists() and not (p / ".svn").exists() and not crg_dir.exists():
            try:
                crg_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
        return str(p)

    def build_or_update(
        self,
        workspace_path: str | Path | None = None,
        full_rebuild: bool = False,
    ) -> dict[str, Any]:
        """Build or incrementally update the AST code graph for the workspace."""
        if not self._available:
            return {
                "ok": False,
                "available": False,
                "error": "code-review-graph engine is not installed or unavailable.",
            }
        repo = self._resolve_repo(workspace_path)
        try:
            res = build_or_update_graph(
                full_rebuild=full_rebuild,
                repo_root=repo,
                postprocess="standard",
            )
            return {
                "ok": True,
                "available": True,
                "repo": repo,
                "data": res,
            }
        except Exception as exc:
            logger.exception("build_or_update_graph failed for %s", repo)
            return {
                "ok": False,
                "available": True,
                "repo": repo,
                "error": str(exc),
            }

    def get_impact_radius(
        self,
        workspace_path: str | Path | None = None,
        changed_files: list[str] | None = None,
        max_depth: int = 2,
    ) -> dict[str, Any]:
        """Calculate the blast radius (affected callers, dependents, and tests)."""
        if not self._available:
            return {
                "ok": False,
                "available": False,
                "error": "code-review-graph engine is not installed or unavailable.",
            }
        repo = self._resolve_repo(workspace_path)
        try:
            res = get_impact_radius(
                changed_files=changed_files,
                max_depth=max_depth,
                repo_root=repo,
                detail_level="standard",
            )
            return {
                "ok": True,
                "available": True,
                "repo": repo,
                "data": res,
            }
        except Exception as exc:
            logger.exception("get_impact_radius failed for %s", repo)
            return {
                "ok": False,
                "available": True,
                "repo": repo,
                "error": str(exc),
            }

    def get_architecture_overview(
        self,
        workspace_path: str | Path | None = None,
        detail_level: str = "minimal",
    ) -> dict[str, Any]:
        """Get high-level module architecture and community clusters without token waste."""
        if not self._available:
            return {
                "ok": False,
                "available": False,
                "error": "code-review-graph engine is not installed or unavailable.",
            }
        repo = self._resolve_repo(workspace_path)
        try:
            res = get_architecture_overview_func(
                repo_root=repo,
                detail_level=detail_level,
                max_results=50,
                max_members=8,
            )
            return {
                "ok": True,
                "available": True,
                "repo": repo,
                "data": res,
            }
        except Exception as exc:
            logger.exception("get_architecture_overview failed for %s", repo)
            return {
                "ok": False,
                "available": True,
                "repo": repo,
                "error": str(exc),
            }

    def get_minimal_context(
        self,
        workspace_path: str | Path | None = None,
        task: str = "",
        changed_files: list[str] | None = None,
    ) -> dict[str, Any]:
        """Extract a token-optimized subgraph context slice for a task or change."""
        if not self._available:
            return {
                "ok": False,
                "available": False,
                "error": "code-review-graph engine is not installed or unavailable.",
            }
        repo = self._resolve_repo(workspace_path)
        try:
            res = get_minimal_context(
                task=task,
                changed_files=changed_files,
                repo_root=repo,
            )
            return {
                "ok": True,
                "available": True,
                "repo": repo,
                "data": res,
            }
        except Exception as exc:
            logger.exception("get_minimal_context failed for %s", repo)
            return {
                "ok": False,
                "available": True,
                "repo": repo,
                "error": str(exc),
            }

    def query_graph(
        self,
        pattern: str,
        target: str,
        workspace_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Query graph edges and nodes (e.g. calls, callers, imports, extends)."""
        if not self._available:
            return {
                "ok": False,
                "available": False,
                "error": "code-review-graph engine is not installed or unavailable.",
            }
        repo = self._resolve_repo(workspace_path)
        try:
            res = query_graph(
                pattern=pattern,
                target=target,
                repo_root=repo,
                detail_level="standard",
                max_results=100,
            )
            return {
                "ok": True,
                "available": True,
                "repo": repo,
                "data": res,
            }
        except Exception as exc:
            logger.exception("query_graph failed for %s", repo)
            return {
                "ok": False,
                "available": True,
                "repo": repo,
                "error": str(exc),
            }

    def get_stats(self, workspace_path: str | Path | None = None) -> dict[str, Any]:
        """Get graph statistics (node counts, edge counts, density)."""
        if not self._available:
            return {
                "ok": False,
                "available": False,
                "error": "code-review-graph engine is not installed or unavailable.",
            }
        repo = self._resolve_repo(workspace_path)
        try:
            res = list_graph_stats(repo_root=repo)
            return {
                "ok": True,
                "available": True,
                "repo": repo,
                "data": res,
            }
        except Exception as exc:
            logger.exception("list_graph_stats failed for %s", repo)
            return {
                "ok": False,
                "available": True,
                "repo": repo,
                "error": str(exc),
            }

    def get_schematic_graph(
        self,
        workspace_path: str | Path | None = None,
        max_nodes: int = 180,
    ) -> dict[str, Any]:
        """Build an interactive UI schematic graph (nodes & edges) using Tree-sitter AST & SQLite knowledge graph."""
        if not self._available:
            return {"nodes": [], "edges": [], "source": "unavailable"}

        repo_str = self._resolve_repo(workspace_path)
        repo = Path(repo_str)

        try:
            from code_review_graph.tools._common import _get_store
            store, _ = _get_store(repo_str)
        except Exception as exc:
            logger.debug("Failed to get CRG store for %s: %s", repo_str, exc)
            return {"nodes": [], "edges": [], "source": "unavailable"}

        try:
            all_files = store.get_all_files()
            if not all_files:
                self.build_or_update(repo_str)
                all_files = store.get_all_files()

            if not all_files:
                return {"nodes": [], "edges": [], "source": "empty"}

            all_nodes = store.get_all_nodes()
            all_edges = store.get_all_edges()

            entry_names = {
                "main.py", "app.py", "web_app.py", "fastapi_app.py", "launcher.py",
                "index.js", "server.js", "index.ts", "server.ts", "main.go", "main.rs"
            }
            nodes: list[dict[str, Any]] = []
            edges: list[dict[str, Any]] = []
            folder_nodes: dict[str, dict[str, Any]] = {}
            node_ids: set[str] = set()
            file_symbol_counts: dict[str, int] = {}

            for n in all_nodes:
                if n.file_path:
                    file_symbol_counts[n.file_path] = file_symbol_counts.get(n.file_path, 0) + 1

            # 1. File nodes & folder containment
            for fpath in all_files:
                p = Path(fpath)
                try:
                    rel = p.relative_to(repo).as_posix()
                except Exception:
                    rel = p.as_posix()

                is_entry = p.name.lower() in entry_names or rel in entry_names
                sym_count = file_symbol_counts.get(fpath, 0)

                nodes.append({
                    "id": rel,
                    "label": p.name,
                    "full_path": rel,
                    "type": "file",
                    "is_entry": is_entry,
                    "symbols_count": sym_count,
                    "start_line": 1,
                    "end_line": 1,
                })
                node_ids.add(rel)

                parent = Path(rel).parent
                while parent and parent.as_posix() != ".":
                    p_str = parent.as_posix()
                    f_id = f"folder::{p_str}"
                    if f_id not in folder_nodes:
                        folder_nodes[f_id] = {
                            "id": f_id,
                            "label": parent.name,
                            "full_path": p_str,
                            "type": "folder",
                            "start_line": 1,
                            "end_line": 1,
                        }
                        node_ids.add(f_id)
                    parent = parent.parent if parent.parent != parent and parent.parent.as_posix() != "." else None

                parent_dir = Path(rel).parent.as_posix()
                if parent_dir and parent_dir != ".":
                    edges.append({
                        "source": f"folder::{parent_dir}",
                        "target": rel,
                        "type": "contains",
                        "label": "contains",
                    })

            nodes.extend(folder_nodes.values())

            # 2. Key Classes & Functions
            sorted_nodes = sorted(
                all_nodes,
                key=lambda x: (0 if x.kind == "Class" else 1 if x.kind == "Function" else 2)
            )

            file_added_symbols: dict[str, int] = {}
            for n in sorted_nodes:
                if len(nodes) >= max_nodes:
                    break
                if n.kind not in ("Class", "Function") or not n.file_path:
                    continue

                p = Path(n.file_path)
                try:
                    rel_file = p.relative_to(repo).as_posix()
                except Exception:
                    rel_file = p.as_posix()

                if file_added_symbols.get(rel_file, 0) >= 6:
                    continue

                sym_id = f"{rel_file}::{n.name}"
                if sym_id in node_ids:
                    continue

                file_added_symbols[rel_file] = file_added_symbols.get(rel_file, 0) + 1
                nodes.append({
                    "id": sym_id,
                    "label": n.name,
                    "file_path": rel_file,
                    "type": "class" if n.kind == "Class" else "function",
                    "start_line": n.line_start or 1,
                    "end_line": n.line_end or 1,
                })
                node_ids.add(sym_id)

                edges.append({
                    "source": rel_file,
                    "target": sym_id,
                    "type": "defines",
                    "label": "defines",
                })

            # 3. Call and Import Edges
            seen_edges: set[tuple[str, str, str]] = set()
            for e in all_edges:
                src_file = e.file_path
                if not src_file:
                    continue
                try:
                    src_rel = Path(src_file).relative_to(repo).as_posix()
                except Exception:
                    src_rel = Path(src_file).as_posix()

                target_qn = e.target_qualified or ""
                target_name = Path(target_qn).name if target_qn else None

                target_id = None
                if target_qn in node_ids:
                    target_id = target_qn
                elif target_name and target_name in node_ids:
                    target_id = target_name

                if target_id and src_rel in node_ids and src_rel != target_id:
                    edge_type = "calls" if e.kind == "CALLS" else "inherits" if e.kind == "INHERITS" else "imports"
                    edge_key = (src_rel, target_id, edge_type)
                    if edge_key not in seen_edges:
                        seen_edges.add(edge_key)
                        edges.append({
                            "source": src_rel,
                            "target": target_id,
                            "type": edge_type,
                            "label": edge_type,
                        })

            file_count = len(all_files)
            symbol_count = len([n for n in all_nodes if n.kind in ("Class", "Function", "Test")])
            return {
                "nodes": nodes,
                "edges": edges,
                "file_count": file_count,
                "symbol_count": symbol_count,
                "source": "code-review-graph",
                "stats": {
                    "total_files": file_count,
                    "total_nodes": len(all_nodes),
                    "total_edges": len(all_edges),
                },
            }
        except Exception as exc:
            logger.exception("Error building schematic graph from code-review-graph: %s", exc)
            return {"nodes": [], "edges": [], "file_count": 0, "symbol_count": 0, "source": "error", "error": str(exc)}
        finally:
            try:
                store.close()
            except Exception:
                pass


# Global singleton instance
code_graph_service = CodeGraphService()
