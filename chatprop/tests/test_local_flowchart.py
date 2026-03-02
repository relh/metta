from metta.chatprop.local.flowchart import render_mermaid_flowchart


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
