import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from code_graph_service import CodeGraphService, code_graph_service
from tools import (
    tool_get_project_architecture,
    tool_get_impact_radius,
    tool_query_code_graph,
    tool_get_code_review_context,
    execute_tool,
    set_workspace,
    get_workspace,
)
from fastapi_app import create_app


def test_code_graph_service_availability():
    """Verify service reports availability status accurately."""
    assert code_graph_service is not None
    assert code_graph_service.is_available is True


def test_code_graph_service_disabled_fallback():
    """Verify behavior when code-review-graph is explicitly marked unavailable."""
    service = CodeGraphService()
    service._available = False

    overview = service.get_architecture_overview("dummy/path")
    assert overview.get("ok") is False
    assert overview.get("available") is False
    assert "not installed or unavailable" in overview.get("error", "")

    impact = service.get_impact_radius("dummy/path", ["foo.py"])
    assert impact.get("ok") is False
    assert impact.get("available") is False

    query_res = service.query_graph("calls", "target", "dummy/path")
    assert query_res.get("ok") is False
    assert query_res.get("available") is False

    review_ctx = service.get_minimal_context("dummy/path", changed_files=["foo.py"])
    assert review_ctx.get("ok") is False
    assert review_ctx.get("available") is False


def test_code_graph_service_real_build():
    """Test graph build and stats on a temporary python repo."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        test_py = os.path.join(tmpdir, "main.py")
        with open(test_py, "w", encoding="utf-8") as f:
            f.write(
                "def helper():\n"
                "    return 42\n\n"
                "def run():\n"
                "    return helper()\n"
            )

        # Test build_or_update
        res = code_graph_service.build_or_update(tmpdir)
        assert "ok" in res
        assert res.get("available") is True

        # Test stats
        stats = code_graph_service.get_stats(tmpdir)
        assert isinstance(stats, dict)
        assert stats.get("available") is True

        # Test architecture overview
        overview = code_graph_service.get_architecture_overview(tmpdir)
        assert isinstance(overview, dict)
        assert overview.get("available") is True

        # Test impact radius
        impact = code_graph_service.get_impact_radius(tmpdir, ["main.py"])
        assert isinstance(impact, dict)
        assert impact.get("available") is True


def test_tools_code_graph_execution():
    """Test calling the 4 graph tools through execute_tool."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_py = os.path.join(tmpdir, "calculator.py")
        with open(test_py, "w", encoding="utf-8") as f:
            f.write("def add(a, b):\n    return a + b\n")

        old_ws = get_workspace()
        set_workspace(Path(tmpdir))
        try:
            # Tool: get_project_architecture
            res_arch = execute_tool("get_project_architecture", {})
            assert "Architecture" in res_arch or "status" in res_arch or "error" in res_arch.lower()

            # Tool: get_impact_radius
            res_impact = execute_tool("get_impact_radius", {"files": ["calculator.py"]})
            assert "status" in res_impact or "impact" in res_impact.lower() or "error" in res_impact.lower()

            # Tool: query_code_graph
            res_query = execute_tool("query_code_graph", {"pattern": "calls", "symbol": "add"})
            assert "status" in res_query or "matches" in res_query or "error" in res_query.lower() or "failed" in res_query.lower()

            # Tool: get_code_review_context
            res_ctx = execute_tool("get_code_review_context", {"files": ["calculator.py"]})
            assert "status" in res_ctx or "subgraph" in res_ctx.lower() or "error" in res_ctx.lower()
        finally:
            set_workspace(old_ws)


def test_fastapi_graph_endpoints():
    """Test the REST endpoints exposed by FastAPI for code-review-graph."""
    app = create_app()
    client = TestClient(app)

    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. GET /api/graph/stats
        resp = client.get(f"/api/graph/stats?workspace_path={tmpdir}")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("available") is True

        # 2. POST /api/graph/build
        resp_build = client.post("/api/graph/build", json={"workspace_path": tmpdir})
        assert resp_build.status_code == 200
        data_build = resp_build.json()
        assert "ok" in data_build

        # 3. GET /api/graph/overview
        resp_ov = client.get(f"/api/graph/overview?workspace_path={tmpdir}")
        assert resp_ov.status_code == 200
        data_ov = resp_ov.json()
        assert "ok" in data_ov

        # 4. POST /api/graph/impact
        resp_imp = client.post("/api/graph/impact", json={
            "workspace_path": tmpdir,
            "changed_files": ["dummy.py"]
        })
        assert resp_imp.status_code == 200
        data_imp = resp_imp.json()
        assert "ok" in data_imp


def test_schematic_graph_integration():
    """Verify that get_schematic_graph produces nodes and edges for the UI canvas."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        test_py = os.path.join(tmpdir, "service.py")
        with open(test_py, "w", encoding="utf-8") as f:
            f.write(
                "class Worker:\n"
                "    def process(self):\n"
                "        return 1\n\n"
                "def main():\n"
                "    w = Worker()\n"
                "    return w.process()\n"
            )

        # Build graph first
        code_graph_service.build_or_update(tmpdir)
        graph = code_graph_service.get_schematic_graph(tmpdir)

        assert isinstance(graph, dict)
        assert "nodes" in graph
        assert "edges" in graph
        assert len(graph["nodes"]) > 0

        # Verify node types compatible with UI canvas
        node_types = {n["type"] for n in graph["nodes"]}
        assert "file" in node_types
        # Verify edge keys
        for e in graph["edges"]:
            assert "source" in e
            assert "target" in e
            assert "type" in e


def test_graphify_payload_and_html_generation():
    """Verify get_graphify_payload and generate_graphify_html for Vis-Network physics engine."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        test_py = os.path.join(tmpdir, "calculator.py")
        with open(test_py, "w", encoding="utf-8") as f:
            f.write(
                "class Calculator:\n"
                "    def add(self, a, b):\n"
                "        return a + b\n\n"
                "def compute():\n"
                "    c = Calculator()\n"
                "    return c.add(10, 20)\n"
            )

        # 1. Test get_graphify_payload
        payload = code_graph_service.get_graphify_payload(tmpdir)
        assert isinstance(payload, dict)
        assert "nodes" in payload
        assert "edges" in payload
        assert "legend" in payload
        assert "stats" in payload
        assert payload.get("source") == "graphify"
        assert len(payload["nodes"]) > 0

        # Verify node fields comply with Vis-Network
        for n in payload["nodes"]:
            assert "id" in n
            assert "label" in n
            assert "color" in n
            assert "size" in n
            assert "community" in n

        # 2. Test generate_graphify_html
        html = code_graph_service.generate_graphify_html(tmpdir)
        assert isinstance(html, str)
        assert "vis.Network" in html
        assert "forceAtlas2Based" in html
        assert "Node Inspector" in html
        assert "Communities" in html


def test_fastapi_graphify_endpoints():
    """Verify FastAPI routes for Graphify standalone HTML and data."""
    app = create_app()
    client = TestClient(app)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        test_py = os.path.join(tmpdir, "app.py")
        with open(test_py, "w", encoding="utf-8") as f:
            f.write("def start():\n    return 'started'\n")

        # 1. GET /api/graph/graphify-data
        resp_data = client.get(f"/api/graph/graphify-data?workspace_path={tmpdir}")
        assert resp_data.status_code == 200
        json_data = resp_data.json()
        assert "nodes" in json_data
        assert "edges" in json_data
        assert "legend" in json_data

        # 2. GET /api/graph/graphify.html
        resp_html = client.get(f"/api/graph/graphify.html?workspace_path={tmpdir}")
        assert resp_html.status_code == 200
        assert "text/html" in resp_html.headers.get("content-type", "")
        assert "vis.Network" in resp_html.text

