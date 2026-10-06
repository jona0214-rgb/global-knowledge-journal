"""Read-only consistency audit for operational and published project data."""

from __future__ import annotations

from pathlib import Path

from build_knowledge_graph import ROOT_DIR, build_public_bundle
from report_pipeline.json_store import load_json


def main() -> None:
    errors: list[str] = []
    warnings: list[str] = []

    taxonomy, reports, concepts, graph = build_public_bundle()
    report_ids = [report["report_id"] for report in reports]
    dates = [str(report.get("date", "")) for report in reports]
    if len(report_ids) != len(set(report_ids)):
        errors.append("공개 리포트 report_id가 중복되었습니다.")
    if len(dates) != len(set(dates)):
        errors.append("공개 리포트 날짜가 중복되었습니다.")

    for report in reports:
        for key in ("html_path", "pdf_path"):
            relative_path = str(report.get(key, ""))
            if not relative_path or not (ROOT_DIR / relative_path).exists():
                errors.append(
                    f"{report.get('report_id')}의 {key} 파일이 없습니다: {relative_path}"
                )

    manifest = load_json(ROOT_DIR / "data" / "manifest.json", {})
    manifest_reports = manifest.get("reports", []) if isinstance(manifest, dict) else []
    manifest_dates = {
        str(item.get("date", ""))
        for item in manifest_reports
        if isinstance(item, dict) and item.get("status") == "published_api"
    }
    if set(dates) != manifest_dates:
        warnings.append("data/manifest.json과 공개 카탈로그의 발행 날짜가 다릅니다.")

    generated_sets = {
        path.stem.removesuffix("_Report")
        for path in (ROOT_DIR / "outputs").glob("*_Report.json")
    }
    catalog_sets = {
        Path(str(report.get("html_path", ""))).stem.removesuffix("_Report")
        for report in reports
    }
    orphan_count = len(generated_sets - catalog_sets)
    if orphan_count:
        warnings.append(f"공개 카탈로그에 없는 outputs JSON이 {orphan_count}개 있습니다.")

    concept_report_ids = {
        str(item.get("report_id", ""))
        for item in concepts.get("reports", [])
        if isinstance(item, dict)
    }
    if concept_report_ids != set(report_ids):
        errors.append("세부 개념 인덱스와 공개 카탈로그의 report_id가 다릅니다.")
    if concepts.get("stats", {}).get("min_tags_per_report", 0) < 25:
        warnings.append("25개 미만의 세부 태그를 가진 리포트가 있습니다.")

    print(
        "프로젝트 감사 완료: "
        f"taxonomy {len(taxonomy['category_order'])}개, "
        f"리포트 {len(reports)}개, "
        f"세부 태그 {concepts['stats']['tags']}개, "
        f"공유 개념 {concepts['stats']['shared_concepts']}개, "
        f"그래프 노드 {graph['stats']['nodes']}개"
    )
    for warning in warnings:
        print(f"WARNING: {warning}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
