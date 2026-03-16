from metta.chatprop.local.flowchart import render_mermaid_flowchart
from metta.chatprop.local.flowchart_core import build_flowchart_payload


def test_render_mermaid_flowchart_keeps_weighted_edges_and_nodes() -> None:
    graph = {
        "graph_scope": "all_feature_chunks",
        "revision_prevention_scope": "merged_feature_chunks_only",
        "nodes": [
            {"id": "implicit_fn:fix", "label": "fix(x)", "kind": "implicit", "count": 10, "argument_samples": ["ci"]},
            {"id": "implicit_fn:test", "label": "test(x)", "kind": "implicit", "count": 8},
            {"id": "explicit:pr.fix-ci", "label": "pr.fix-ci", "kind": "explicit", "count": 4},
        ],
        "edges": [
            {"source": "implicit_fn:fix", "target": "implicit_fn:test", "phase": "planning", "count": 7},
            {"source": "implicit_fn:test", "target": "explicit:pr.fix-ci", "phase": "explicit_ref", "count": 3},
        ],
    }

    payload = render_mermaid_flowchart(graph, max_nodes=10, max_edges=10)
    mermaid = payload["mermaid"]
    selected = payload["selected_graph"]

    assert selected["node_count"] == 3
    assert selected["edge_count"] == 2
    assert "7 planning" in mermaid
    assert "3 explicit_ref" in mermaid
    assert "fix(x)" in mermaid
    assert "arg=ci" in mermaid


def test_build_flowchart_payload_includes_catalog_metadata_and_options() -> None:
    graph = {
        "nodes": [
            {"id": "implicit_fn:fix", "label": "fix(x)", "kind": "implicit", "count": 10},
            {"id": "implicit_fn:test", "label": "test(x)", "kind": "implicit", "count": 8},
        ],
        "edges": [
            {"source": "implicit_fn:fix", "target": "implicit_fn:test", "phase": "flow", "count": 7},
        ],
    }

    payload = build_flowchart_payload(
        graph,
        min_node_count=2,
        min_edge_count=3,
        max_nodes=5,
        max_edges=6,
        catalog_generated_at="2026-03-01T00:00:00Z",
        session_count=12,
        branch_count=4,
        options={
            "min_node_count": 2,
            "min_edge_count": 3,
            "max_nodes": 5,
            "max_edges": 6,
        },
    )

    assert payload["catalog_generated_at"] == "2026-03-01T00:00:00Z"
    assert payload["session_count"] == 12
    assert payload["branch_count"] == 4
    assert payload["options"] == {
        "min_node_count": 2,
        "min_edge_count": 3,
        "max_nodes": 5,
        "max_edges": 6,
    }
    assert payload["selected_graph"]["node_count"] == 2
    assert payload["selected_graph"]["edge_count"] == 1
