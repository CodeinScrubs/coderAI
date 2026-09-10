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


# Global singleton instance
code_graph_service = CodeGraphService()
