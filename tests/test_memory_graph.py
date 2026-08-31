import json
import time
import pytest
from pathlib import Path
from memory_graph import GraphMemoryStore, Entity, Fact, Episode, SQLiteGraphBackend
import web_app


def test_sqlite_graph_backend_crud(tmp_path):
    db_path = tmp_path / "test_graph.db"
    backend = SQLiteGraphBackend(db_path)

    # 1. Add Entity
    e1 = Entity(id="ent-1", name="Reza", type="person", aliases=["Mohammadreza"], created_at=time.time(), updated_at=time.time())
    e2 = Entity(id="ent-2", name="CoderAI", type="project", aliases=["Ollama Workspace"], created_at=time.time(), updated_at=time.time())
    backend.add_entity(e1)
    backend.add_entity(e2)

    # Verify retrieval
    found = backend.find_entity_by_name_or_alias("mohammadreza")
    assert found is not None
    assert found.id == "ent-1"

    # 2. Add Fact
    f1 = Fact(
        id="fact-1",
        from_entity_id="ent-1",
        to_entity_id="ent-2",
        from_name="Reza",
        to_name="CoderAI",
        relation="works_on",
        fact_text="(Reza) --[works_on]--> (CoderAI)",
        confidence=0.95,
        valid_from=time.time(),
    )
    backend.add_fact(f1)

    # Expand graph from seed
    expanded = backend.expand_graph(["ent-1"], hops=2)
    assert len(expanded) == 1
    assert expanded[0].relation == "works_on"
    assert expanded[0].from_name == "Reza"
    assert expanded[0].to_name == "CoderAI"

    # Invalidate fact
    backend.invalidate_fact("ent-1", "ent-2", "works_on", time.time())
    expanded_after = backend.expand_graph(["ent-1"], hops=2)
    assert len(expanded_after) == 0

    stats = backend.get_stats()
    assert stats["entities"] == 2
    assert stats["total_facts"] == 1
    assert stats["active_facts"] == 0


def test_graph_memory_store_resolution_and_retrieval(tmp_path):
    store = GraphMemoryStore(tmp_path)

    # Add facts
    store.add_fact("Alice", "maintains", "FastAPI Service", confidence=0.9, subject_type="person", object_type="project")
    store.add_fact("FastAPI Service", "uses", "Pydantic V2", confidence=0.85, subject_type="project", object_type="library")

    # Multi-hop retrieval
    ctx = store.retrieve_context("Tell me about Alice and her project", token_budget=300)
    assert "[Knowledge graph context]" in ctx
    assert "Alice" in ctx
    assert "FastAPI Service" in ctx

    # Search
    results = store.search("Alice")
    assert len(results["entities"]) >= 1
    assert len(results["facts"]) >= 1

    # Forget entity
    deleted = store.forget_entity("Alice")
    assert deleted is True
    stats = store.get_stats()
    assert stats["active_facts"] == 1  # Alice's fact cascaded away, FastAPI Service -> Pydantic remains


def test_graph_memory_rule_based_extraction(tmp_path):
    store = GraphMemoryStore(tmp_path)
    text = """
    Our backend uses PostgreSQL and Python.
    The team prefers React over Angular.
    Reza works on CoderAI.
    """
    triples = store.extract_triples_rule_based(text)
    assert len(triples) >= 2
    relations = [t["relation"] for t in triples]
    assert "uses" in relations or "works_on" in relations or "prefers_over" in relations


def test_auto_project_indexing_and_conversion(tmp_path):
    # Setup a mock project directory structure
    proj_dir = tmp_path / "my_demo_app"
    proj_dir.mkdir()
    
    # 1. package.json
    (proj_dir / "package.json").write_text(json.dumps({
        "name": "demo-ecommerce",
        "main": "server.js",
        "dependencies": {
            "express": "^4.18.2",
            "react": "^18.2.0",
            "tailwindcss": "^3.0.0"
        }
    }), encoding="utf-8")

    # 2. requirements.txt
    (proj_dir / "requirements.txt").write_text("fastapi>=0.100.0\nuvicorn\npydantic==2.5.0\n", encoding="utf-8")

    # 3. README.md
    (proj_dir / "README.md").write_text("# Demo Ecommerce\nThis project uses Redis for caching.\nReza maintains Demo Ecommerce.\n", encoding="utf-8")

    # 4. Source files
    src_dir = proj_dir / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text("class AuthService:\n    pass\n\ndef login_user():\n    pass\n", encoding="utf-8")

    # Run auto-indexing on the project folder
    store = GraphMemoryStore(proj_dir)
    res = store.index_project_workspace()

    assert res["ok"] is True
    assert res["facts_added"] >= 5
    assert "demo-ecommerce" in res["project_name"]

    # Verify facts were created in the knowledge graph
    stats = store.get_stats()
    assert stats["entities"] >= 4
    assert stats["active_facts"] >= 5

    # Verify context retrieval finds the indexed dependencies
    ctx = store.retrieve_context("What technologies and libraries does the project use?", token_budget=500)
    assert "[Knowledge graph context]" in ctx
    assert "express" in ctx or "fastapi" in ctx or "react" in ctx
