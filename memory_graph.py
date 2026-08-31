"""
memory_graph.py - Embedded Knowledge Graph (KG-RAG) Memory Subsystem.

Provides local graph-based memory storage, entity resolution, bi-temporal
fact tracking, multi-hop relationship expansion, and prompt context injection.
"""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Entity:
    id: str
    name: str
    type: str = "concept"
    aliases: list[str] = field(default_factory=list)
    embedding: list[float] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0


@dataclass
class Fact:
    id: str
    from_entity_id: str
    to_entity_id: str
    from_name: str
    to_name: str
    relation: str
    fact_text: str
    confidence: float = 1.0
    valid_from: float = 0.0
    valid_until: Optional[float] = None
    source_episode_id: Optional[str] = None


@dataclass
class Episode:
    id: str
    role: str
    content: str
    source_ref: str = ""
    created_at: float = 0.0


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)


class BaseGraphBackend:
    def add_entity(self, entity: Entity) -> None:
        raise NotImplementedError

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        raise NotImplementedError

    def find_entity_by_name_or_alias(self, query: str) -> Optional[Entity]:
        raise NotImplementedError

    def list_entities(self, limit: int = 100) -> list[Entity]:
        raise NotImplementedError

    def add_episode(self, episode: Episode) -> None:
        raise NotImplementedError

    def add_fact(self, fact: Fact) -> None:
        raise NotImplementedError

    def invalidate_fact(self, from_id: str, to_id: str, relation: str, until_time: float) -> None:
        raise NotImplementedError

    def expand_graph(self, seed_entity_ids: list[str], hops: int = 2, limit: int = 40) -> list[Fact]:
        raise NotImplementedError

    def forget_entity(self, entity_id: str) -> bool:
        raise NotImplementedError

    def get_stats(self) -> dict:
        raise NotImplementedError


class SQLiteGraphBackend(BaseGraphBackend):
    """Embedded SQLite-backed Graph Storage with Recursive CTE Traversal."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS graph_entities (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL DEFAULT 'concept',
                    aliases TEXT NOT NULL DEFAULT '[]',
                    embedding TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_entity_name ON graph_entities(name);

                CREATE TABLE IF NOT EXISTS graph_episodes (
                    id TEXT PRIMARY KEY,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_ref TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS graph_facts (
                    id TEXT PRIMARY KEY,
                    from_entity_id TEXT NOT NULL REFERENCES graph_entities(id) ON DELETE CASCADE,
                    to_entity_id TEXT NOT NULL REFERENCES graph_entities(id) ON DELETE CASCADE,
                    relation TEXT NOT NULL,
                    fact_text TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 1.0,
                    valid_from REAL NOT NULL,
                    valid_until REAL,
                    source_episode_id TEXT REFERENCES graph_episodes(id) ON DELETE SET NULL
                );
                CREATE INDEX IF NOT EXISTS idx_fact_from ON graph_facts(from_entity_id, valid_until);
                CREATE INDEX IF NOT EXISTS idx_fact_to ON graph_facts(to_entity_id, valid_until);
                CREATE INDEX IF NOT EXISTS idx_fact_rel ON graph_facts(relation);

                CREATE TABLE IF NOT EXISTS graph_mentions (
                    episode_id TEXT NOT NULL REFERENCES graph_episodes(id) ON DELETE CASCADE,
                    entity_id TEXT NOT NULL REFERENCES graph_entities(id) ON DELETE CASCADE,
                    PRIMARY KEY(episode_id, entity_id)
                );
            """)

    def add_entity(self, entity: Entity) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("""
                INSERT INTO graph_entities (id, name, type, aliases, embedding, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    type = excluded.type,
                    aliases = excluded.aliases,
                    embedding = excluded.embedding,
                    updated_at = excluded.updated_at
            """, (
                entity.id,
                entity.name,
                entity.type,
                json.dumps(entity.aliases),
                json.dumps(entity.embedding),
                entity.created_at,
                entity.updated_at,
            ))

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM graph_entities WHERE id = ?", (entity_id,)).fetchone()
            if not row:
                return None
            return self._row_to_entity(row)

    def find_entity_by_name_or_alias(self, query: str) -> Optional[Entity]:
        q_norm = query.strip().lower()
        if not q_norm:
            return None
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM graph_entities WHERE lower(name) = ? LIMIT 1", (q_norm,)).fetchone()
            if row:
                return self._row_to_entity(row)
            rows = conn.execute("SELECT * FROM graph_entities").fetchall()
            for r in rows:
                aliases = [a.lower() for a in json.loads(r["aliases"])]
                if q_norm in aliases:
                    return self._row_to_entity(r)
        return None

    def list_entities(self, limit: int = 100) -> list[Entity]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM graph_entities ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
            return [self._row_to_entity(r) for r in rows]

    def _row_to_entity(self, row: sqlite3.Row) -> Entity:
        return Entity(
            id=row["id"],
            name=row["name"],
            type=row["type"],
            aliases=json.loads(row["aliases"]),
            embedding=json.loads(row["embedding"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def add_episode(self, episode: Episode) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("""
                INSERT INTO graph_episodes (id, role, content, source_ref, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    role = excluded.role,
                    content = excluded.content,
                    source_ref = excluded.source_ref
            """, (
                episode.id,
                episode.role,
                episode.content,
                episode.source_ref,
                episode.created_at,
            ))

    def add_fact(self, fact: Fact) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("""
                INSERT INTO graph_facts (
                    id, from_entity_id, to_entity_id, relation,
                    fact_text, confidence, valid_from, valid_until, source_episode_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    relation = excluded.relation,
                    fact_text = excluded.fact_text,
                    confidence = excluded.confidence,
                    valid_from = excluded.valid_from,
                    valid_until = excluded.valid_until,
                    source_episode_id = excluded.source_episode_id
            """, (
                fact.id,
                fact.from_entity_id,
                fact.to_entity_id,
                fact.relation,
                fact.fact_text,
                fact.confidence,
                fact.valid_from,
                fact.valid_until,
                fact.source_episode_id,
            ))

    def invalidate_fact(self, from_id: str, to_id: str, relation: str, until_time: float) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("""
                UPDATE graph_facts
                SET valid_until = ?
                WHERE from_entity_id = ? AND to_entity_id = ? AND relation = ? AND valid_until IS NULL
            """, (until_time, from_id, to_id, relation))

    def expand_graph(self, seed_entity_ids: list[str], hops: int = 2, limit: int = 40) -> list[Fact]:
        if not seed_entity_ids:
            return []

        placeholders = ",".join("?" for _ in seed_entity_ids)
        query = f"""
            WITH RECURSIVE search_graph(node_id, depth) AS (
                SELECT id, 0 FROM graph_entities WHERE id IN ({placeholders})
                UNION
                SELECT
                    CASE WHEN f.from_entity_id = sg.node_id THEN f.to_entity_id ELSE f.from_entity_id END,
                    sg.depth + 1
                FROM search_graph sg
                JOIN graph_facts f ON (f.from_entity_id = sg.node_id OR f.to_entity_id = sg.node_id)
                WHERE sg.depth < ? AND f.valid_until IS NULL
            )
            SELECT DISTINCT
                f.id, f.from_entity_id, f.to_entity_id,
                e1.name AS from_name, e2.name AS to_name,
                f.relation, f.fact_text, f.confidence,
                f.valid_from, f.valid_until, f.source_episode_id
            FROM search_graph sg
            JOIN graph_facts f ON (f.from_entity_id = sg.node_id OR f.to_entity_id = sg.node_id)
            JOIN graph_entities e1 ON e1.id = f.from_entity_id
            JOIN graph_entities e2 ON e2.id = f.to_entity_id
            WHERE f.valid_until IS NULL
            ORDER BY f.confidence DESC, f.valid_from DESC
            LIMIT ?
        """
        params = list(seed_entity_ids) + [hops, limit]
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            facts = []
            for r in rows:
                facts.append(Fact(
                    id=r["id"],
                    from_entity_id=r["from_entity_id"],
                    to_entity_id=r["to_entity_id"],
                    from_name=r["from_name"],
                    to_name=r["to_name"],
                    relation=r["relation"],
                    fact_text=r["fact_text"],
                    confidence=r["confidence"],
                    valid_from=r["valid_from"],
                    valid_until=r["valid_until"],
                    source_episode_id=r["source_episode_id"],
                ))
            return facts

    def forget_entity(self, entity_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM graph_entities WHERE id = ? OR lower(name) = ?", (entity_id, entity_id.lower()))
            return cur.rowcount > 0

    def get_stats(self) -> dict:
        with self._connect() as conn:
            entity_count = conn.execute("SELECT count(*) FROM graph_entities").fetchone()[0]
            active_facts = conn.execute("SELECT count(*) FROM graph_facts WHERE valid_until IS NULL").fetchone()[0]
            total_facts = conn.execute("SELECT count(*) FROM graph_facts").fetchone()[0]
            episodes = conn.execute("SELECT count(*) FROM graph_episodes").fetchone()[0]
            db_size = self.db_path.stat().st_size if self.db_path.exists() else 0
            return {
                "backend": "sqlite-graph",
                "entities": entity_count,
                "active_facts": active_facts,
                "total_facts": total_facts,
                "episodes": episodes,
                "storage_bytes": db_size,
            }


class GraphMemoryStore:
    """
    KG-RAG Memory Store orchestrating triple extraction, entity resolution,
    bi-temporal edge invalidation, and multi-hop graph expansion.
    """

    def __init__(self, workspace_path: Path | str, storage_root: Path | str | None = None):
        self.workspace_path = Path(workspace_path).resolve()
        if storage_root:
            self.storage_dir = Path(storage_root).resolve()
        else:
            self.storage_dir = self.workspace_path / ".agent_memory" / "graph"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.storage_dir / "knowledge_graph.db"
        self.backend: BaseGraphBackend = SQLiteGraphBackend(self.db_path)
        self._lock = threading.RLock()

    def resolve_entity(
        self,
        name: str,
        entity_type: str = "concept",
        aliases: list[str] | None = None,
        embedding: list[float] | None = None,
    ) -> Entity:
        name_clean = name.strip()
        if not name_clean:
            name_clean = "Unnamed"

        with self._lock:
            existing = self.backend.find_entity_by_name_or_alias(name_clean)
            if existing:
                updated = False
                if aliases:
                    for a in aliases:
                        if a not in existing.aliases:
                            existing.aliases.append(a)
                            updated = True
                if embedding and not existing.embedding:
                    existing.embedding = embedding
                    updated = True
                if updated:
                    existing.updated_at = time.time()
                    self.backend.add_entity(existing)
                return existing

            if embedding:
                for ent in self.backend.list_entities(limit=200):
                    if ent.embedding and _cosine_similarity(embedding, ent.embedding) >= 0.88:
                        if name_clean not in ent.aliases:
                            ent.aliases.append(name_clean)
                            ent.updated_at = time.time()
                            self.backend.add_entity(ent)
                        return ent

            now = time.time()
            new_id = f"entity_{uuid.uuid4().hex[:10]}"
            new_entity = Entity(
                id=new_id,
                name=name_clean,
                type=entity_type or "concept",
                aliases=list(aliases or []),
                embedding=list(embedding or []),
                created_at=now,
                updated_at=now,
            )
            self.backend.add_entity(new_entity)
            return new_entity

    def add_episode(self, role: str, content: str, source_ref: str = "") -> str:
        ep_id = f"ep_{uuid.uuid4().hex[:10]}"
        episode = Episode(
            id=ep_id,
            role=role,
            content=content,
            source_ref=source_ref,
            created_at=time.time(),
        )
        self.backend.add_episode(episode)
        return ep_id

    def add_fact(
        self,
        subject: str,
        relation: str,
        object_: str,
        confidence: float = 1.0,
        episode_id: Optional[str] = None,
        subject_type: str = "concept",
        object_type: str = "concept",
        invalidate_previous: bool = True,
    ) -> Fact:
        with self._lock:
            sub_ent = self.resolve_entity(subject, entity_type=subject_type)
            obj_ent = self.resolve_entity(object_, entity_type=object_type)
            now = time.time()

            rel_clean = relation.strip().lower().replace(" ", "_")
            if invalidate_previous:
                self.backend.invalidate_fact(sub_ent.id, obj_ent.id, rel_clean, now)

            fact_id = f"fact_{uuid.uuid4().hex[:10]}"
            fact_text = f"({sub_ent.name}) --[{rel_clean}]--> ({obj_ent.name})"
            fact = Fact(
                id=fact_id,
                from_entity_id=sub_ent.id,
                to_entity_id=obj_ent.id,
                from_name=sub_ent.name,
                to_name=obj_ent.name,
                relation=rel_clean,
                fact_text=fact_text,
                confidence=max(0.1, min(1.0, float(confidence))),
                valid_from=now,
                valid_until=None,
                source_episode_id=episode_id,
            )
            self.backend.add_fact(fact)
            return fact

    def extract_triples_rule_based(self, text: str) -> list[dict]:
        """Deterministic pattern-based triple extraction for developer facts."""
        triples = []
        lines = text.splitlines()
        patterns = [
            (re.compile(r"([A-Za-z0-9_\-\.]+)\s+(?:uses|is using|built with)\s+([A-Za-z0-9_\-\.]+)", re.I), "uses", "project", "technology"),
            (re.compile(r"([A-Za-z0-9_\-\.]+)\s+(?:depends on|requires)\s+([A-Za-z0-9_\-\.]+)", re.I), "depends_on", "technology", "library"),
            (re.compile(r"([A-Za-z0-9_\-\.]+)\s+(?:implements|features|has)\s+([A-Za-z0-9_\-\.\s]{3,30})", re.I), "implements", "project", "feature"),
            (re.compile(r"prefer(?:s)?\s+([A-Za-z0-9_\-\.]+)\s+over\s+([A-Za-z0-9_\-\.]+)", re.I), "prefers_over", "concept", "concept"),
            (re.compile(r"([A-Za-z0-9_\-\.]+)\s+(?:works on|assigned to|maintains)\s+([A-Za-z0-9_\-\.]+)", re.I), "works_on", "person", "project"),
            (re.compile(r"([A-Za-z0-9_\-\.]+)\s+(?:created|authored|wrote)\s+([A-Za-z0-9_\-\.]+)", re.I), "created", "person", "artifact"),
        ]
        for line in lines:
            line_str = line.strip().strip("-*#")
            for pat, rel, stype, otype in patterns:
                m = pat.search(line_str)
                if m:
                    sub, obj = m.group(1).strip(), m.group(2).strip()
                    if sub and obj and len(sub) > 1 and len(obj) > 1:
                        triples.append({
                            "subject": sub,
                            "relation": rel,
                            "object": obj,
                            "confidence": 0.9,
                            "subject_type": stype,
                            "object_type": otype,
                        })
        return triples

    def ingest_turn_async(self, role: str, content: str, source_ref: str = "") -> None:
        """Asynchronously extract and ingest knowledge graph facts in a background thread."""
        def _worker():
            try:
                ep_id = self.add_episode(role, content, source_ref=source_ref)
                triples = self.extract_triples_rule_based(content)
                for item in triples:
                    self.add_fact(
                        subject=item["subject"],
                        relation=item["relation"],
                        object_=item["object"],
                        confidence=item.get("confidence", 0.9),
                        episode_id=ep_id,
                        subject_type=item.get("subject_type", "concept"),
                        object_type=item.get("object_type", "concept"),
                    )
            except Exception:
                pass

        t = threading.Thread(target=_worker, daemon=True, name="KG-IngestWorker")
        t.start()

    def find_seed_entities(self, query: str, top_k: int = 5) -> list[Entity]:
        words = [w.strip().lower() for w in re.split(r"[\s,\.;:!?\'\"\\/()\[\]{}]+", query) if len(w.strip()) > 2]
        if not words:
            return []

        matched = []
        seen = set()
        for ent in self.backend.list_entities(limit=200):
            ent_name_lower = ent.name.lower()
            aliases_lower = [a.lower() for a in ent.aliases]
            for w in words:
                if w == ent_name_lower or w in ent_name_lower or any(w in a for a in aliases_lower):
                    if ent.id not in seen:
                        matched.append(ent)
                        seen.add(ent.id)
                        break
            if len(matched) >= top_k:
                break
        return matched

    def retrieve_context(self, query_text: str, token_budget: int = 400) -> str:
        """Retrieve multi-hop Knowledge Graph context formatted for system prompt injection."""
        seeds = self.find_seed_entities(query_text, top_k=5)
        if not seeds:
            facts = self.backend.expand_graph([e.id for e in self.backend.list_entities(limit=5)], hops=1, limit=10)
        else:
            seed_ids = [s.id for s in seeds]
            facts = self.backend.expand_graph(seed_ids, hops=2, limit=20)

        if not facts:
            return ""

        lines = ["[Knowledge graph context]"]
        char_count = len(lines[0])
        max_chars = token_budget * 4

        for fact in facts:
            line = f"- ({fact.from_name}) --{fact.relation}--> ({fact.to_name})"
            if char_count + len(line) + 1 > max_chars:
                break
            lines.append(line)
            char_count += len(line) + 1

        if len(lines) <= 1:
            return ""
        return "\n".join(lines) + "\n"

    def search(self, query: str, limit: int = 20) -> dict:
        seeds = self.find_seed_entities(query, top_k=limit)
        facts = self.backend.expand_graph([s.id for s in seeds], hops=2, limit=limit) if seeds else []
        return {
            "query": query,
            "entities": [{"id": s.id, "name": s.name, "type": s.type, "aliases": s.aliases} for s in seeds],
            "facts": [
                {
                    "id": f.id,
                    "from": f.from_name,
                    "to": f.to_name,
                    "relation": f.relation,
                    "confidence": f.confidence,
                    "valid_from": f.valid_from,
                    "valid_until": f.valid_until,
                }
                for f in facts
            ],
            "stats": self.backend.get_stats(),
        }

    def forget_entity(self, entity_id_or_name: str) -> bool:
        return self.backend.forget_entity(entity_id_or_name)

    def get_stats(self) -> dict:
        return self.backend.get_stats()

    def index_project_workspace(self, force_refresh: bool = False) -> dict:
        """
        Automatically scan and index a project folder:
        - Detects project name, dependencies, frameworks, languages, entrypoints.
        - Parses README and configuration files into Knowledge Graph facts.
        - Extracts key architectural modules and symbols.
        - Returns indexing metrics and populated graph statistics.
        """
        if not self.workspace_path.exists() or not self.workspace_path.is_dir():
            return {"error": "Workspace directory does not exist"}

        from workspace_filter import iter_workspace_files

        project_name = self.workspace_path.name
        dependencies: list[str] = []
        languages: set[str] = set()
        entrypoints: list[str] = []
        facts_added = 0

        # 1. Inspect package.json
        pkg_json = self.workspace_path / "package.json"
        if pkg_json.is_file():
            try:
                data = json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
                if data.get("name"):
                    project_name = str(data["name"])
                all_deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                for dep in list(all_deps.keys())[:30]:
                    dependencies.append(dep)
                    self.add_fact(project_name, "uses", dep, confidence=1.0, subject_type="project", object_type="library")
                    facts_added += 1
                if data.get("main"):
                    main_f = str(data["main"])
                    entrypoints.append(main_f)
                    self.add_fact(project_name, "has_entrypoint", main_f, confidence=1.0, subject_type="project", object_type="file")
                    facts_added += 1
                languages.add("JavaScript/TypeScript")
            except Exception:
                pass

        # 2. Inspect Python configs (pyproject.toml, requirements.txt, setup.py)
        req_txt = self.workspace_path / "requirements.txt"
        if req_txt.is_file():
            languages.add("Python")
            try:
                for line in req_txt.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = line.strip().split("#")[0].split("==")[0].split(">=")[0].split("<=")[0].strip()
                    if line and not line.startswith("-"):
                        dependencies.append(line)
                        self.add_fact(project_name, "uses", line, confidence=1.0, subject_type="project", object_type="library")
                        facts_added += 1
            except Exception:
                pass

        pyproject = self.workspace_path / "pyproject.toml"
        if pyproject.is_file():
            languages.add("Python")
            try:
                content = pyproject.read_text(encoding="utf-8", errors="ignore")
                for line in content.splitlines():
                    if "name =" in line:
                        name_match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', line)
                        if name_match:
                            project_name = name_match.group(1)
                            break
            except Exception:
                pass

        # 3. Inspect Rust (Cargo.toml) / Go (go.mod)
        cargo_toml = self.workspace_path / "Cargo.toml"
        if cargo_toml.is_file():
            languages.add("Rust")
            try:
                content = cargo_toml.read_text(encoding="utf-8", errors="ignore")
                for line in content.splitlines():
                    if "name =" in line:
                        name_match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', line)
                        if name_match:
                            project_name = name_match.group(1)
                            break
            except Exception:
                pass

        go_mod = self.workspace_path / "go.mod"
        if go_mod.is_file():
            languages.add("Go")

        # 4. Resolve main project entity
        proj_ent = self.resolve_entity(project_name, entity_type="project", aliases=[self.workspace_path.name, "project", "workspace", "codebase", "app"])

        for lang in languages:
            self.add_fact(project_name, "primary_language", lang, confidence=1.0, subject_type="project", object_type="language")
            facts_added += 1

        # 5. Readme Parsing
        readme_file = None
        for r_name in ("README.md", "README.txt", "readme.md", "README.rst"):
            cand = self.workspace_path / r_name
            if cand.is_file():
                readme_file = cand
                break

        if readme_file:
            try:
                r_text = readme_file.read_text(encoding="utf-8", errors="ignore")
                triples = self.extract_triples_rule_based(r_text)
                for item in triples:
                    self.add_fact(
                        subject=item["subject"],
                        relation=item["relation"],
                        object_=item["object"],
                        confidence=item.get("confidence", 0.9),
                        subject_type=item.get("subject_type", "concept"),
                        object_type=item.get("object_type", "concept"),
                    )
                    facts_added += 1
            except Exception:
                pass

        # 6. File Structure & Key Entrypoint Discovery
        try:
            files = list(iter_workspace_files(self.workspace_path))
            file_exts: dict[str, int] = {}
            for f in files:
                rel = str(f.relative_to(self.workspace_path)).replace("\\", "/")
                ext = f.suffix.lower()
                file_exts[ext] = file_exts.get(ext, 0) + 1

                # Check for standard entrypoints
                if rel.lower() in ("main.py", "app.py", "web_app.py", "server.py", "index.js", "index.ts", "server.ts", "main.go", "main.rs", "src/index.js", "src/main.py", "src/main.rs"):
                    if rel not in entrypoints:
                        entrypoints.append(rel)
                        self.add_fact(project_name, "has_entrypoint", rel, confidence=1.0, subject_type="project", object_type="file")
                        facts_added += 1

                # Extract Python class/function definitions for top files
                if ext == ".py" and len(files) <= 100:
                    try:
                        code = f.read_text(encoding="utf-8", errors="ignore")
                        for match in re.finditer(r"^(?:class|def)\s+([A-Za-z0-9_]+)", code, re.M):
                            sym = match.group(1)
                            if not sym.startswith("_"):
                                self.add_fact(rel, "defines", sym, confidence=0.85, subject_type="file", object_type="symbol")
                                facts_added += 1
                    except Exception:
                        pass
        except Exception:
            pass

        return {
            "ok": True,
            "project_name": project_name,
            "languages": sorted(list(languages)),
            "dependencies_count": len(dependencies),
            "entrypoints": entrypoints,
            "facts_added": facts_added,
            "stats": self.backend.get_stats(),
        }

