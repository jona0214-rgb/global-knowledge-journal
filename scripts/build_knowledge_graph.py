"""Build or validate the versioned public data used by the future knowledge map."""

from __future__ import annotations

import argparse
from pathlib import Path

from report_pipeline.catalog import normalize_catalog_item
from report_pipeline.concept_extractor import build_report_concepts
from report_pipeline.json_store import load_json, save_json_atomic
from report_pipeline.knowledge_graph import build_knowledge_graph
from report_pipeline.taxonomy import (
    canonical_main_category,
    load_aliases,
    load_taxonomy,
    public_taxonomy_payload,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
REPORTS_PATH = ROOT_DIR / "public" / "reports.json"
TAXONOMY_PATH = ROOT_DIR / "config" / "topic_taxonomy_v2.json"
ALIASES_PATH = ROOT_DIR / "config" / "taxonomy_aliases.json"
OVERRIDES_PATH = ROOT_DIR / "data" / "knowledge_edge_overrides.json"
CONCEPT_CONFIG_PATH = ROOT_DIR / "config" / "concept_aliases.json"
ANNOTATIONS_PATH = ROOT_DIR / "data" / "knowledge_annotations.json"
MANIFEST_PATH = ROOT_DIR / "data" / "manifest.json"
PUBLIC_API_DIR = ROOT_DIR / "public" / "api" / "v1"


def build_public_bundle() -> tuple[dict, list[dict], dict, dict]:
    taxonomy = load_taxonomy(TAXONOMY_PATH)
    aliases = load_aliases(ALIASES_PATH)
    source_reports = load_json(REPORTS_PATH, [])
    if not isinstance(source_reports, list):
        raise ValueError("public/reports.json은 list여야 합니다.")

    reports = []
    for source in source_reports:
        if not isinstance(source, dict) or source.get("status") != "published_api":
            continue
        report = normalize_catalog_item(ROOT_DIR, source)
        report["main_category"] = canonical_main_category(report, taxonomy, aliases)
        reports.append(report)
    reports.sort(key=lambda item: str(item.get("date", "")), reverse=True)

    public_taxonomy = public_taxonomy_payload(taxonomy, aliases)
    overrides = load_json(OVERRIDES_PATH, {"schema_version": "1.0", "edges": []})
    if overrides.get("schema_version") != "1.0":
        raise ValueError("knowledge edge override schema_version은 1.0이어야 합니다.")
    manifest = load_json(MANIFEST_PATH, {})
    generated_at = str(manifest.get("last_updated", "")).strip()
    if not generated_at:
        latest_date = str(reports[0].get("date", "1970-01-01")) if reports else "1970-01-01"
        generated_at = f"{latest_date}T00:00:00Z"

    concept_config = load_json(CONCEPT_CONFIG_PATH, {})
    manual_annotations = load_json(
        ANNOTATIONS_PATH,
        {"schema_version": "1.0", "reports": {}},
    )
    concepts = build_report_concepts(
        ROOT_DIR,
        reports,
        concept_config,
        manual_annotations,
        generated_at,
    )

    # 소스 데이터가 바뀌지 않은 재시도는 동일한 산출물을 만들어야 한다.
    # 실행 시각을 쓰면 예약 재시도 때마다 의미 없는 커밋이 생기므로 manifest 시각을 사용한다.
    graph = build_knowledge_graph(
        reports,
        taxonomy,
        aliases,
        overrides,
        concept_annotations=concepts,
        generated_at=generated_at,
    )
    return public_taxonomy, reports, concepts, graph


def build_public_data() -> tuple[dict, list[dict], dict]:
    """Backward-compatible three-item result used by audits and older callers."""

    taxonomy, reports, _, graph = build_public_bundle()
    return taxonomy, reports, graph


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="데이터를 검증하되 public/api/v1 파일은 쓰지 않습니다.",
    )
    args = parser.parse_args()

    taxonomy, reports, concepts, graph = build_public_bundle()
    if not args.check:
        save_json_atomic(PUBLIC_API_DIR / "taxonomy.json", taxonomy)
        save_json_atomic(PUBLIC_API_DIR / "reports.json", reports)
        save_json_atomic(PUBLIC_API_DIR / "report-concepts.json", concepts)
        save_json_atomic(PUBLIC_API_DIR / "knowledge-graph.json", graph)

    print(
        "지식 그래프 데이터 검증 완료: "
        f"대분류 {graph['stats']['categories']}개, "
        f"리포트 {graph['stats']['reports']}개, "
        f"세부 태그 {concepts['stats']['tags']}개, "
        f"공유 개념 {concepts['stats']['shared_concepts']}개, "
        f"노드 {graph['stats']['nodes']}개, "
        f"연결 {graph['stats']['edges']}개"
    )


if __name__ == "__main__":
    main()
