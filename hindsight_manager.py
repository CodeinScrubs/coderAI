"""
hindsight_manager.py - Deep long-term memory integration using Vectorize Hindsight.

Connects to a local or remote Hindsight instance (http://localhost:8888 by default)
with automated bank scoping per workspace and seamless local fallback to
internal MemoryManager/SQLite when Hindsight is offline.
"""

from __future__ import annotations

import logging
import os
import re
import time
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_HINDSIGHT_URL = os.getenv("HINDSIGHT_API_URL", "http://localhost:8888")
DEFAULT_HINDSIGHT_KEY = os.getenv("HINDSIGHT_API_KEY", None)

try:
    from hindsight_client import Hindsight, RecallResponse, ReflectResponse, RetainResponse
    HINDSIGHT_CLIENT_AVAILABLE = True
except ImportError:
    Hindsight = None  # type: ignore
    HINDSIGHT_CLIENT_AVAILABLE = False


def sanitize_bank_id(workspace_path: str | Path | None) -> str:
    """Generate a clean, deterministic bank_id for a workspace path."""
    if not workspace_path:
        return "default-workspace"
    p = Path(workspace_path).resolve()
    name = p.name or "root"
    cleaned = re.sub(r"[^a-zA-Z0-9_\-]", "_", name).lower()
    return f"ws_{cleaned}"[:48]


class HindsightMemoryManager:
    def __init__(
        self,
        base_url: str = DEFAULT_HINDSIGHT_URL,
        api_key: str | None = DEFAULT_HINDSIGHT_KEY,
        timeout: float = 5.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client: Any = None
        self._is_online: bool | None = None
        self._last_health_check: float = 0.0
        self._health_check_interval: float = 15.0  # seconds

    def _get_client(self) -> Any:
        if not HINDSIGHT_CLIENT_AVAILABLE:
            return None
        if self._client is None:
            try:
                self._client = Hindsight(
                    base_url=self.base_url,
                    api_key=self.api_key,
                    timeout=self.timeout,
                )
            except Exception as e:
                logger.debug(f"Failed to initialize Hindsight client: {e}")
                self._client = None
        return self._client

    def is_available(self, force_refresh: bool = False) -> bool:
        """Check if Hindsight API is reachable within a low timeout."""
        if not HINDSIGHT_CLIENT_AVAILABLE:
            return False

        now = time.time()
        if not force_refresh and self._is_online is not None:
            if now - self._last_health_check < self._health_check_interval:
                return self._is_online

        self._last_health_check = now
        try:
            req = urllib.request.Request(
                f"{self.base_url}/health",
                headers={"User-Agent": "CoderAI-HindsightManager"},
            )
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                self._is_online = (200 <= resp.status < 300)
                return self._is_online
        except Exception:
            # Also try checking root or OpenAPI specs
            try:
                req = urllib.request.Request(
                    f"{self.base_url}/openapi.json",
                    headers={"User-Agent": "CoderAI-HindsightManager"},
                )
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    self._is_online = (200 <= resp.status < 300)
                    return self._is_online
            except Exception:
                self._is_online = False
                return False

    def get_bank_id(self, workspace_path: str | Path | None = None) -> str:
        """Get the bank identifier scoped to the given or active workspace."""
        if not workspace_path:
            try:
                from tools import get_workspace
                workspace_path = get_workspace()
            except ImportError:
                workspace_path = "default"
        return sanitize_bank_id(workspace_path)

    def retain(
        self,
        content: str,
        context: str | None = None,
        workspace_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """
        Store a new memory, fact, or experience into Hindsight.
        Falls back gracefully to internal MemoryManager if offline.
        """
        bank_id = self.get_bank_id(workspace_path)
        content_clean = str(content or "").strip()
        if not content_clean:
            return {"status": "skipped", "reason": "empty content"}

        client = self._get_client()
        if client and self.is_available():
            try:
                resp = client.retain(
                    bank_id=bank_id,
                    content=content_clean,
                    context=context,
                )
                return {
                    "status": "retained",
                    "bank_id": bank_id,
                    "engine": "hindsight",
                    "id": getattr(resp, "id", None) or getattr(resp, "operation_id", None),
                }
            except Exception as e:
                logger.warning(f"Hindsight retain error: {e}. Falling back to local memory.")

        # Local fallback via memory_manager
        try:
            from memory_manager import get_memory_manager
            mm = get_memory_manager()
            mm.add_fact(content_clean, category="hindsight_fallback")
            return {
                "status": "retained_locally",
                "bank_id": bank_id,
                "engine": "local_fallback",
                "note": "Stored in local memory store because Hindsight server is offline.",
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def recall(
        self,
        query: str,
        max_tokens: int = 2048,
        workspace_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """
        Retrieve relevant memories using Hindsight's 4-way parallel retrieval
        (Semantic + BM25 + Graph + Temporal) with cross-encoder reranking.
        """
        bank_id = self.get_bank_id(workspace_path)
        query_clean = str(query or "").strip()
        if not query_clean:
            return {"prompt_string": "", "count": 0, "results": []}

        client = self._get_client()
        if client and self.is_available():
            try:
                resp: RecallResponse = client.recall(
                    bank_id=bank_id,
                    query=query_clean,
                    max_tokens=max_tokens,
                )
                prompt_str = ""
                if hasattr(resp, "to_prompt_string"):
                    prompt_str = resp.to_prompt_string()
                elif hasattr(resp, "results"):
                    items = [str(r.content if hasattr(r, "content") else r) for r in (resp.results or [])]
                    prompt_str = "\n".join(items)

                results = getattr(resp, "results", []) or []
                return {
                    "prompt_string": prompt_str,
                    "count": len(results),
                    "engine": "hindsight",
                    "bank_id": bank_id,
                }
            except Exception as e:
                logger.warning(f"Hindsight recall error: {e}. Falling back to local memory.")

        # Fallback to local vector/memory store
        try:
            from memory_manager import get_memory_manager
            mm = get_memory_manager()
            local_facts = mm.get_relevant_facts(query_clean, limit=4)
            if local_facts:
                prompt_str = "\n".join(f"- {f.get('fact', '')}" for f in local_facts if f.get('fact'))
                return {
                    "prompt_string": prompt_str,
                    "count": len(local_facts),
                    "engine": "local_fallback",
                    "bank_id": bank_id,
                }
        except Exception:
            pass

        return {"prompt_string": "", "count": 0, "engine": "none", "bank_id": bank_id}

    def reflect(
        self,
        query: str,
        workspace_path: str | Path | None = None,
    ) -> str:
        """
        Synthesize deeper observations and mental models using Hindsight reflect.
        """
        bank_id = self.get_bank_id(workspace_path)
        query_clean = str(query or "").strip()
        if not query_clean:
            return "No query provided for reflection."

        client = self._get_client()
        if client and self.is_available():
            try:
                resp: ReflectResponse = client.reflect(
                    bank_id=bank_id,
                    query=query_clean,
                )
                return getattr(resp, "text", "") or str(resp)
            except Exception as e:
                logger.warning(f"Hindsight reflect error: {e}. Falling back to local memory.")

        # Local fallback
        try:
            from memory_manager import get_memory_manager
            mm = get_memory_manager()
            summary = mm.get_summary()
            if summary:
                return f"[Local Memory Reflection based on summary]:\n{summary}"
        except Exception:
            pass
        return "Hindsight reflection unavailable (server offline and no local summary found)."

    def get_status(self, workspace_path: str | Path | None = None) -> dict[str, Any]:
        """Return connectivity and configuration status for the UI."""
        bank_id = self.get_bank_id(workspace_path)
        online = self.is_available(force_refresh=True)
        return {
            "client_installed": HINDSIGHT_CLIENT_AVAILABLE,
            "online": online,
            "base_url": self.base_url,
            "active_bank_id": bank_id,
            "engine": "hindsight" if online else "local_fallback",
        }


# Global singleton
_hindsight_instance: HindsightMemoryManager | None = None


def get_hindsight_manager() -> HindsightMemoryManager:
    global _hindsight_instance
    if _hindsight_instance is None:
        _hindsight_instance = HindsightMemoryManager()
    return _hindsight_instance
