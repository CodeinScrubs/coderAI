"""Shared local vector infrastructure for memory and code collections."""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import threading
import urllib.request
import urllib.error
from pathlib import Path


def list_ollama_models(base_url: str | None = None) -> list[str]:
    url = (base_url or os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")).rstrip("/")
    req = urllib.request.Request(f"{url}/api/tags")
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        return []


def is_embeddinggemma_available(base_url: str | None = None) -> bool:
    models = list_ollama_models(base_url)
    return any("embeddinggemma" in m.lower() for m in models)


def resolve_embedding_model(preferred: str | None = None, base_url: str | None = None) -> str:
    if preferred:
        return preferred
    env_model = os.getenv("OLLAMA_EMBEDDING_MODEL")
    if env_model:
        return env_model
    if is_embeddinggemma_available(base_url):
        return "embeddinggemma"
    return "nomic-embed-text"


class EmbeddingModelManager:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.is_pulling = False
        self.progress_text = ""
        self.error: str | None = None
        self.completed = False
        self.pull_thread: threading.Thread | None = None

    @classmethod
    def get_instance(cls) -> "EmbeddingModelManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = EmbeddingModelManager()
            return cls._instance

    def get_status(self, base_url: str | None = None) -> dict:
        installed = is_embeddinggemma_available(base_url)
        return {
            "installed": installed,
            "target_model": "embeddinggemma",
            "active_model": "embeddinggemma" if installed else "nomic-embed-text",
            "is_pulling": self.is_pulling,
            "progress_text": self.progress_text,
            "completed": self.completed,
            "error": self.error,
        }

    def start_pull(self, model: str = "embeddinggemma", base_url: str | None = None) -> bool:
        with self._lock:
            if self.is_pulling:
                return True
            self.is_pulling = True
            self.progress_text = "Starting download..."
            self.error = None
            self.completed = False

            def _worker():
                try:
                    ollama_bin = shutil.which("ollama")
                    if ollama_bin:
                        self.progress_text = f"Executing ollama pull {model}..."
                        proc = subprocess.Popen(
                            [ollama_bin, "pull", model],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            encoding="utf-8",
                            errors="replace",
                        )
                        for line in iter(proc.stdout.readline, ""):
                            line_str = line.strip()
                            if line_str:
                                self.progress_text = line_str
                        proc.wait()
                        if proc.returncode == 0:
                            self.completed = True
                            self.progress_text = "Download completed successfully!"
                            self.is_pulling = False
                            return

                    # Fallback to Ollama HTTP /api/pull
                    url = (base_url or os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")).rstrip("/")
                    req = urllib.request.Request(
                        f"{url}/api/pull",
                        data=json.dumps({"name": model, "stream": True}).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                    )
                    with urllib.request.urlopen(req, timeout=1800) as resp:
                        for raw_line in resp:
                            line = raw_line.decode("utf-8").strip()
                            if not line:
                                continue
                            try:
                                payload = json.loads(line)
                                status = payload.get("status", "")
                                completed = payload.get("completed", 0)
                                total = payload.get("total", 0)
                                if total > 0:
                                    pct = int((completed / total) * 100)
                                    self.progress_text = f"{status}: {pct}%"
                                else:
                                    self.progress_text = status
                            except Exception:
                                pass
                    self.completed = True
                    self.progress_text = "Download completed successfully!"
                except Exception as exc:
                    self.error = str(exc)
                    self.progress_text = f"Download failed: {exc}"
                finally:
                    self.is_pulling = False

            self.pull_thread = threading.Thread(target=_worker, daemon=True)
            self.pull_thread.start()
            return True


class LocalEmbeddingProvider:
    def __init__(self, model: str | None = None, base_url: str | None = None, timeout: int = 8):
        self.base_url = (base_url or os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")).rstrip("/")
        self.model = model or resolve_embedding_model(base_url=self.base_url)
        self.timeout = timeout

    def embed(self, texts: str | list[str]) -> list[list[float]]:
        values = [texts] if isinstance(texts, str) else list(texts)
        if not values:
            return []
        body = json.dumps({"model": self.model, "input": values}).encode("utf-8")
        request = urllib.request.Request(f"{self.base_url}/api/embed", data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            return self._embed_legacy(values)
        embeddings = payload.get("embeddings") or []
        if len(embeddings) != len(values):
            raise RuntimeError(f"Ollama returned {len(embeddings)} embeddings for {len(values)} inputs")
        return [[float(item) for item in vector] for vector in embeddings]

    def _embed_legacy(self, values: list[str]) -> list[list[float]]:
        vectors = []
        for value in values:
            body = json.dumps({"model": self.model, "prompt": value}).encode("utf-8")
            request = urllib.request.Request(f"{self.base_url}/api/embeddings", data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            vector = payload.get("embedding") or []
            if not vector:
                raise RuntimeError("Ollama legacy embeddings endpoint returned no embedding")
            vectors.append([float(item) for item in vector])
        return vectors


class SharedVectorStore:
    """Chroma client shared by named collections; callers provide embeddings."""

    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        self.path.mkdir(parents=True, exist_ok=True)
        self.available = False
        self.error = ""
        self._client = None
        try:
            import chromadb

            self._client = chromadb.PersistentClient(path=str(self.path))
            self.available = True
        except Exception as exc:
            self.error = repr(exc)

    def upsert(self, collection: str, ids: list[str], documents: list[str], metadatas: list[dict], embeddings: list[list[float]]) -> None:
        if not self.available or not ids:
            return
        self._client.get_or_create_collection(collection).upsert(
            ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings,
        )

    def delete(self, collection: str, ids: list[str] | None = None, where: dict | None = None) -> None:
        if not self.available:
            return
        target = self._client.get_or_create_collection(collection)
        if ids:
            target.delete(ids=ids)
        elif where:
            target.delete(where=where)

    def query(self, collection: str, embedding: list[float], limit: int) -> list[dict]:
        if not self.available or not embedding:
            return []
        result = self._client.get_or_create_collection(collection).query(query_embeddings=[embedding], n_results=limit)
        rows = []
        for index, chunk_id in enumerate((result.get("ids") or [[]])[0]):
            distance = ((result.get("distances") or [[]])[0] or [None] * (index + 1))[index]
            rows.append({"id": chunk_id, "score": 1.0 - float(distance or 0.0)})
        return rows


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(sum(value * value for value in right))
    return sum(a * b for a, b in zip(left, right)) / denominator if denominator else 0.0
