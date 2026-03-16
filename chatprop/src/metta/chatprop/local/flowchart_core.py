"""Shared flowchart rendering and export helpers for chatprop."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _escape_mermaid(value: str) -> str:
    return value.replace('"', "'")


def _compact_label(node: dict[str, Any]) -> str:
    label = node.get("label") if isinstance(node.get("label"), str) else str(node.get("id", "unknown"))
    count = int(node.get("count", 0))
    args = node.get("argument_samples")
    if isinstance(args, list) and args:
        first = args[0]
        if isinstance(first, str) and first:
            return f"{label}<br/>arg={_escape_mermaid(first)}<br/>count={count}"
    return f"{label}<br/>count={count}"


def _select_nodes(graph: dict[str, Any], *, min_node_count: int, max_nodes: int) -> list[dict[str, Any]]:
    nodes_raw = graph.get("nodes")
    if not isinstance(nodes_raw, list):
        return []
    nodes = [node for node in nodes_raw if isinstance(node, dict)]
    nodes.sort(key=lambda node: (-int(node.get("count", 0)), str(node.get("id", ""))))
    filtered = [node for node in nodes if int(node.get("count", 0)) >= min_node_count]
    return filtered[:max_nodes]


def _select_edges(
    graph: dict[str, Any],
    *,
    allowed_node_ids: set[str],
    min_edge_count: int,
    max_edges: int,
) -> list[dict[str, Any]]:
    edges_raw = graph.get("edges")
    if not isinstance(edges_raw, list):
        return []
    edges = [edge for edge in edges_raw if isinstance(edge, dict)]
    edges.sort(key=lambda edge: (-int(edge.get("count", 0)), str(edge.get("phase", ""))))
    selected: list[dict[str, Any]] = []
    for edge in edges:
        count = int(edge.get("count", 0))
        source = edge.get("source")
        target = edge.get("target")
        if count < min_edge_count:
            continue
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        if source not in allowed_node_ids or target not in allowed_node_ids:
            continue
        selected.append(edge)
        if len(selected) >= max_edges:
            break
    return selected


def _node_class(node: dict[str, Any]) -> str:
    kind = node.get("kind")
    if kind == "explicit":
        return "explicit"
    return "implicit"


def render_mermaid_flowchart(
    graph: dict[str, Any],
    *,
    min_node_count: int = 1,
    min_edge_count: int = 1,
    max_nodes: int = 100,
    max_edges: int = 250,
) -> dict[str, Any]:
    selected_nodes = _select_nodes(graph, min_node_count=min_node_count, max_nodes=max_nodes)
    node_ids = [node.get("id") for node in selected_nodes if isinstance(node.get("id"), str)]
    id_set = set(node_ids)
    selected_edges = _select_edges(
        graph,
        allowed_node_ids=id_set,
        min_edge_count=min_edge_count,
        max_edges=max_edges,
    )
    used_node_ids = {
        value for edge in selected_edges for value in (edge.get("source"), edge.get("target")) if isinstance(value, str)
    }
    if used_node_ids:
        selected_nodes = [node for node in selected_nodes if node.get("id") in used_node_ids]
        node_ids = [node.get("id") for node in selected_nodes if isinstance(node.get("id"), str)]

    node_alias: dict[str, str] = {node_id: f"n{index}" for index, node_id in enumerate(node_ids)}
    lines = ["graph LR"]
    lines.append("classDef implicit fill:#123728,stroke:#2ca36b,color:#d5f5e3;")
    lines.append("classDef explicit fill:#1f2d42,stroke:#60a5fa,color:#dbeafe;")

    for node in selected_nodes:
        node_id = node.get("id")
        if not isinstance(node_id, str):
            continue
        alias = node_alias[node_id]
        label = _escape_mermaid(_compact_label(node))
        lines.append(f'{alias}["{label}"]')

    for edge in selected_edges:
        source = edge.get("source")
        target = edge.get("target")
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        if source not in node_alias or target not in node_alias:
            continue
        phase = edge.get("phase") if isinstance(edge.get("phase"), str) else "flow"
        count = int(edge.get("count", 0))
        label = _escape_mermaid(f"{count} {phase}")
        lines.append(f'{node_alias[source]} -- "{label}" --> {node_alias[target]}')

    for node in selected_nodes:
        node_id = node.get("id")
        if not isinstance(node_id, str):
            continue
        if node_id not in node_alias:
            continue
        lines.append(f"class {node_alias[node_id]} {_node_class(node)};")

    selected_graph = {
        "nodes": selected_nodes,
        "edges": selected_edges,
        "node_count": len(selected_nodes),
        "edge_count": len(selected_edges),
        "graph_scope": graph.get("graph_scope"),
        "revision_prevention_scope": graph.get("revision_prevention_scope"),
    }
    return {
        "mermaid": "\n".join(lines) + "\n",
        "selected_graph": selected_graph,
    }


def build_flowchart_payload(
    graph: dict[str, Any],
    *,
    min_node_count: int = 1,
    min_edge_count: int = 1,
    max_nodes: int = 100,
    max_edges: int = 250,
    catalog_generated_at: str | None = None,
    session_count: int | None = None,
    branch_count: int | None = None,
    options: dict[str, int] | None = None,
) -> dict[str, Any]:
    rendered = render_mermaid_flowchart(
        graph,
        min_node_count=min_node_count,
        min_edge_count=min_edge_count,
        max_nodes=max_nodes,
        max_edges=max_edges,
    )
    payload: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "workflow_graph": graph,
        "selected_graph": rendered["selected_graph"],
        "mermaid": rendered["mermaid"],
    }
    if options is not None:
        payload["options"] = options
    if catalog_generated_at:
        payload["catalog_generated_at"] = catalog_generated_at
    if session_count is not None:
        payload["session_count"] = session_count
    if branch_count is not None:
        payload["branch_count"] = branch_count
    return payload


def write_flowchart_outputs(
    *,
    payload: dict[str, Any],
    mermaid_path: Path,
    json_path: Path | None = None,
) -> None:
    mermaid_path.parent.mkdir(parents=True, exist_ok=True)
    mermaid_path.write_text(str(payload.get("mermaid", "")), encoding="utf-8")
    if json_path is None:
        return
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
