import json
import sqlite3
from pathlib import Path
import pytest

from vector_store import (
    is_sqlite_vec_available,
    load_sqlite_vec,
    serialize_vector_f32,
    SQLITE_VEC_AVAILABLE,
)
from codebase_index import CodebaseIndex


def test_sqlite_vec_helpers():
    assert is_sqlite_vec_available() is True
    assert SQLITE_VEC_AVAILABLE is True

    db = sqlite3.connect(":memory:")
    loaded = load_sqlite_vec(db)
    assert loaded is True

    version_row = db.execute("SELECT vec_version()").fetchone()
    assert version_row is not None and version_row[0].startswith("v")

    buf = serialize_vector_f32([1.0, 2.0, 3.0])
    assert isinstance(buf, (bytes, bytearray))
    assert len(buf) == 12  # 3 * 4 bytes for float32


def test_codebase_index_uses_sqlite_vec_when_chroma_unavailable(tmp_path: Path, monkeypatch):
    index = CodebaseIndex(tmp_path)

    # Mock embeddings with 3 dimensions for test simplicity
    def fake_embed(values):
        texts = [values] if isinstance(values, str) else list(values)
        res = []
        for text in texts:
            t = text.lower()
            if "alpha" in t:
                res.append([1.0, 0.0, 0.0])
            elif "beta" in t:
                res.append([0.0, 1.0, 0.0])
            else:
                res.append([0.0, 0.0, 1.0])
        return res

    monkeypatch.setattr(index.embedding_provider, "embed", fake_embed)
    index.vector_store.available = False

    assert index.sqlite_vec_available is True
    status = index.status()
    assert status["vector_backend"] == "sqlite-vec"

    # Create test files
    (tmp_path / "mod_a.py").write_text("def alpha_task():\n    return 'alpha'\n", encoding="utf-8")
    (tmp_path / "mod_b.py").write_text("def beta_worker():\n    return 'beta'\n", encoding="utf-8")

    index.index_file(tmp_path / "mod_a.py")
    index.index_file(tmp_path / "mod_b.py")

    # Verify vec_code_chunks virtual table was created in SQLite
    with index._connect() as db:
        table_row = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='vec_code_chunks'").fetchone()
        assert table_row is not None
        count_row = db.execute("SELECT count(*) FROM vec_code_chunks").fetchone()
        assert count_row[0] >= 2

    # Query for alpha
    results = index._semantic_search("find alpha", limit=2)
    assert len(results) >= 1
    top_chunk_id = results[0]["id"]
    with index._connect() as db:
        chunk = db.execute("SELECT file_path, symbol_name FROM code_chunks WHERE id=?", (top_chunk_id,)).fetchone()
        assert chunk["file_path"] == "mod_a.py"
        assert chunk["symbol_name"] == "alpha_task"

    # Verify scores are normalized (1.0 for exact match)
    assert results[0]["score"] > 0.8


def test_codebase_index_fallback_when_sqlite_vec_disabled(tmp_path: Path, monkeypatch):
    # Simulate an environment where sqlite-vec is not installed
    monkeypatch.setattr("codebase_index.is_sqlite_vec_available", lambda: False)

    index = CodebaseIndex(tmp_path)
    assert index.sqlite_vec_available is False

    def fake_embed(values):
        texts = [values] if isinstance(values, str) else list(values)
        return [[1.0 if "target" in t.lower() else 0.0, 0.5, 0.0] for t in texts]

    monkeypatch.setattr(index.embedding_provider, "embed", fake_embed)
    index.vector_store.available = False

    status = index.status()
    assert status["vector_backend"] == "sqlite-embedding-fallback"

    (tmp_path / "target.py").write_text("def target_fn():\n    pass\n", encoding="utf-8")
    index.index_file(tmp_path / "target.py")

    results = index._semantic_search("target query", limit=1)
    assert len(results) == 1
    assert results[0]["score"] > 0.0


def test_sqlite_vec_rebuild_and_remove(tmp_path: Path, monkeypatch):
    index = CodebaseIndex(tmp_path)

    def fake_embed(values):
        texts = [values] if isinstance(values, str) else list(values)
        return [[1.0, 0.0, 0.0] for _ in texts]

    monkeypatch.setattr(index.embedding_provider, "embed", fake_embed)
    index.vector_store.available = False

    f1 = tmp_path / "first.py"
    f2 = tmp_path / "second.py"
    f1.write_text("def func_one(): pass\n", encoding="utf-8")
    f2.write_text("def func_two(): pass\n", encoding="utf-8")

    index.index_file(f1)
    index.index_file(f2)

    with index._connect() as db:
        initial_count = db.execute("SELECT count(*) FROM vec_code_chunks").fetchone()[0]
        assert initial_count >= 2

    # Remove f1
    index.remove_file("first.py")
    with index._connect() as db:
        after_remove = db.execute("SELECT count(*) FROM vec_code_chunks").fetchone()[0]
        assert after_remove < initial_count

    # Rebuild
    index.rebuild()
    with index._connect() as db:
        after_rebuild = db.execute("SELECT count(*) FROM vec_code_chunks").fetchone()[0]
        assert after_rebuild >= 1
