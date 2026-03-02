"""Export weighted skill-flow charts from chatprop workflow graph data."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from metta.chatprop.config import ChatpropConfig
from metta.chatprop.local.backend.server import build_catalog_snapshot
from metta.chatprop.local.flowchart_core import render_mermaid_flowchart, write_flowchart_outputs

__all__ = ["build_flowchart_artifacts", "render_mermaid_flowchart", "write_flowchart_outputs"]


def build_flowchart_artifacts(
    *,
    config: ChatpropConfig | None = None,
    refresh: bool = False,
    min_node_count: int = 1,
    min_edge_count: int = 1,
    max_nodes: int = 100,
    max_edges: int = 250,
) -> dict[str, Any]:
    catalog = build_catalog_snapshot(config=config, refresh=refresh)
    graph = catalog.get("workflow_graph", {})
    if not isinstance(graph, dict):
        graph = {}
    rendered = render_mermaid_flowchart(
        graph,
        min_node_count=min_node_count,
        min_edge_count=min_edge_count,
        max_nodes=max_nodes,
        max_edges=max_edges,
    )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "catalog_generated_at": catalog.get("generated_at"),
        "session_count": catalog.get("session_count", 0),
        "branch_count": catalog.get("branch_count", 0),
        "workflow_graph": graph,
        "selected_graph": rendered["selected_graph"],
        "mermaid": rendered["mermaid"],
    }
