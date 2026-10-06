"""Deterministic hierarchy graph builder for published reports.

Semantic cross-report edges are deliberately supplied through a versioned override
file until an explainable scoring pipeline is introduced. This keeps the first
graph index reproducible and prevents unreviewed model output from becoming public.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from .catalog import build_report_id
from .taxonomy import canonical_main_category


def _node_id(kind: str, *parts: str) -> str:
    raw = "\x1f".join(str(part).strip() for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{kind}:{digest}"


def _edge_id(source: str, target: str, relation_type: str) -> str:
    return _node_id("edge", source, target, relation_type)


def build_knowledge_graph(
    reports: list[dict[str, Any]],
    taxonomy: dict[str, Any],
    aliases: dict[str, Any],
    overrides: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}
    report_node_ids: dict[str, str] = {}

    def add_node(node: dict[str, Any]) -> None:
        nodes.setdefault(node["id"], node)

    def add_edge(source: str, target: str, relation_type: str, **extra: Any) -> None:
        edge_id = _edge_id(source, target, relation_type)
        edges.setdefault(
            edge_id,
            {
                "id": edge_id,
                "source": source,
                "target": target,
                "kind": "hierarchy" if relation_type == "contains" else "semantic",
                "relation_type": relation_type,
                **extra,
            },
        )

    category_ids: dict[str, str] = {}
    for order, category in enumerate(taxonomy["category_order"]):
        category_id = _node_id("category", category)
        category_ids[category] = category_id
        add_node(
            {
                "id": category_id,
                "type": "category",
                "label": category,
                "level": 0,
                "order": order,
            }
        )

    published = [
        report
        for report in reports
        if isinstance(report, dict) and report.get("status") == "published_api"
    ]
    published.sort(key=lambda item: (str(item.get("date", "")), str(item.get("title", ""))))

    for report in published:
        main = canonical_main_category(report, taxonomy, aliases)
        if main not in category_ids:
            raise ValueError(f"리포트의 대분류를 정규화할 수 없습니다: {report.get('title', '')}")
        middle = str(report.get("mid_category", "")).strip() or "미분류"
        sub = str(report.get("sub_category", "")).strip() or "미분류"
        detail = str(report.get("detail_category", "")).strip() or "미분류"

        category_id = category_ids[main]
        middle_id = _node_id("middle", main, middle)
        sub_id = _node_id("sub", main, middle, sub)
        detail_id = _node_id("detail", main, middle, sub, detail)
        report_id = build_report_id(report)
        report_node_id = f"report:{report_id}"

        add_node({"id": middle_id, "type": "middle", "label": middle, "level": 1, "main_category": main})
        add_node({"id": sub_id, "type": "sub", "label": sub, "level": 2, "main_category": main})
        add_node({"id": detail_id, "type": "detail", "label": detail, "level": 3, "main_category": main})
        add_node(
            {
                "id": report_node_id,
                "type": "report",
                "label": report.get("title", "제목 없음"),
                "level": 4,
                "report_id": report_id,
                "date": report.get("date", ""),
                "main_category": main,
                "category_path": [main, middle, sub, detail],
                "html_url": report.get("html_url") or report.get("html_path", ""),
                "pdf_url": report.get("pdf_url") or report.get("pdf_path", ""),
            }
        )
        report_node_ids[report_id] = report_node_id
        add_edge(category_id, middle_id, "contains")
        add_edge(middle_id, sub_id, "contains")
        add_edge(sub_id, detail_id, "contains")
        add_edge(detail_id, report_node_id, "contains")

    overrides = overrides or {"edges": []}
    for relation in overrides.get("edges", []):
        source_id = report_node_ids.get(str(relation.get("source_report_id", "")))
        target_id = report_node_ids.get(str(relation.get("target_report_id", "")))
        if not source_id or not target_id:
            raise ValueError("수동 지식 연결이 존재하지 않는 report_id를 참조합니다.")
        if source_id == target_id:
            raise ValueError("수동 지식 연결은 자기 자신을 참조할 수 없습니다.")
        relation_type = str(relation.get("relation_type", "related")).strip()
        explanation = str(relation.get("explanation", "")).strip()
        evidence = relation.get("evidence", [])
        if not explanation or not isinstance(evidence, list) or not evidence:
            raise ValueError("의미 연결에는 explanation과 evidence가 필요합니다.")
        add_edge(
            source_id,
            target_id,
            relation_type,
            score=float(relation.get("score", 1.0)),
            explanation=explanation,
            evidence=evidence,
            curated=True,
        )

    graph = {
        "schema_version": "1.0",
        "taxonomy_version": taxonomy["taxonomy_version"],
        "algorithm_version": "hierarchy-v1",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "stats": {
            "categories": len(category_ids),
            "reports": len(published),
            "nodes": len(nodes),
            "edges": len(edges),
            "semantic_edges": sum(1 for edge in edges.values() if edge["kind"] == "semantic"),
        },
        "nodes": sorted(nodes.values(), key=lambda node: node["id"]),
        "edges": sorted(edges.values(), key=lambda edge: edge["id"]),
    }
    validate_knowledge_graph(graph)
    return graph


def validate_knowledge_graph(graph: dict[str, Any]) -> None:
    if graph.get("schema_version") != "1.0":
        raise ValueError("knowledge graph schema_version은 1.0이어야 합니다.")
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("knowledge graph nodes와 edges는 list여야 합니다.")
    node_ids = [node.get("id") for node in nodes if isinstance(node, dict)]
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("knowledge graph node id가 중복되었습니다.")
    node_id_set = set(node_ids)
    edge_ids: set[str] = set()
    for edge in edges:
        if edge.get("id") in edge_ids:
            raise ValueError("knowledge graph edge id가 중복되었습니다.")
        edge_ids.add(edge.get("id"))
        if edge.get("source") not in node_id_set or edge.get("target") not in node_id_set:
            raise ValueError("knowledge graph edge가 존재하지 않는 node를 참조합니다.")
        if edge.get("source") == edge.get("target"):
            raise ValueError("knowledge graph에는 자기 연결을 허용하지 않습니다.")
