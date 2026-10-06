"""Deterministic, evidence-backed concept extraction for published reports.

The extractor intentionally runs after report validation and publication.  It does
not add fields to the OpenAI response schema, so knowledge-map enrichment cannot
make daily report generation fail.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .json_store import load_json


ALLOWED_TYPES = {
    "concept",
    "mechanism",
    "method",
    "entity",
    "institution",
    "event",
    "technology",
    "problem",
    "outcome",
    "domain",
    "theme",
    "work",
}
SHARED_EXACT_TYPES = {"concept", "mechanism", "method", "technology", "problem", "outcome"}
MARKER_RE = re.compile(r"^\s*(?:<[^>]+>|\d{1,2}(?:-\d+)?[.)/]?)\s*")
SPACE_RE = re.compile(r"\s+")
PAREN_RE = re.compile(r"^(.*?)\s*[（(]([^()（）]{2,80})[）)]\s*$")


def _stable_id(prefix: str, *parts: str) -> str:
    raw = "\x1f".join(parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _clean_text(value: Any) -> str:
    text = str(value or "").replace("\x00", " ").replace("\ufffc", " ")
    return SPACE_RE.sub(" ", text).strip(" \t\r\n-–—:;,.·")


def _clean_label(value: Any) -> tuple[str, list[str]]:
    label = MARKER_RE.sub("", _clean_text(value))
    aliases: list[str] = []
    match = PAREN_RE.match(label)
    if match and _clean_text(match.group(1)):
        label = _clean_text(match.group(1))
        aliases.append(_clean_text(match.group(2)))
    return label, aliases


def _lookup_key(value: str) -> str:
    return SPACE_RE.sub(" ", value).strip().casefold()


def _alias_map(config: dict[str, Any]) -> dict[str, str]:
    aliases = config.get("aliases", {})
    if not isinstance(aliases, dict):
        raise ValueError("concept aliases는 object여야 합니다.")
    return {_lookup_key(str(key)): _clean_text(value) for key, value in aliases.items()}


def normalize_label(value: Any, config: dict[str, Any]) -> tuple[str, list[str]]:
    label, aliases = _clean_label(value)
    canonical = _alias_map(config).get(_lookup_key(label), label)
    aliases = [alias for alias in aliases if alias and _lookup_key(alias) != _lookup_key(canonical)]
    if canonical != label and label:
        aliases.append(label)
    return canonical, sorted(set(aliases), key=str.casefold)


def _classify_term(label: str, description: str = "") -> str:
    text = f"{label} {description}".casefold()
    if any(token in text for token in ("정리", "법칙", "이론", "모형", "모델", "방법론", "분석법")):
        return "method"
    if any(token in text for token in ("기술", "알고리즘", "플랫폼", "시스템", "장치", "세포", "네트워크")):
        return "technology"
    if any(token in text for token in ("오염", "편향", "불평등", "위기", "위험", "장애", "갈등")):
        return "problem"
    if any(token in text for token in ("표준화", "순환", "주기", "반응", "작동", "동기화", "회피", "심리", "변동성")):
        return "mechanism"
    if any(token in text for token in ("효율", "개선", "회복", "안정", "성과", "영향")):
        return "outcome"
    if any(token in text for token in ("제도", "위원회", "정부", "협회", "시장", "법원", "학교")):
        return "institution"
    return "concept"


def _evidence(reference: str, matched_text: str) -> dict[str, str]:
    return {"reference": reference, "matched_text": _clean_text(matched_text)[:120]}


def _entity_label(value: Any) -> str:
    """Keep the named person or organization, not a trailing job description."""

    return re.split(r"\s*[,，]\s*", _clean_text(value), maxsplit=1)[0]


def _add_tag(
    tags: dict[tuple[str, str], dict[str, Any]],
    *,
    label: Any,
    concept_type: str,
    weight: float,
    reference: str,
    matched_text: Any | None,
    config: dict[str, Any],
) -> None:
    canonical, aliases = normalize_label(label, config)
    stop_labels = {_lookup_key(str(item)) for item in config.get("stop_labels", [])}
    if (
        not canonical
        or len(canonical) < 2
        or len(canonical) > 80
        or _lookup_key(canonical) in stop_labels
    ):
        return
    if concept_type not in ALLOWED_TYPES:
        raise ValueError(f"지원하지 않는 concept type입니다: {concept_type}")
    key = (_lookup_key(canonical), concept_type)
    item = tags.setdefault(
        key,
        {
            "tag_id": _stable_id("tag", concept_type, _lookup_key(canonical)),
            "label": canonical,
            "normalized_label": canonical,
            "type": concept_type,
            "weight": round(float(weight), 3),
            "aliases": [],
            "evidence": [],
        },
    )
    item["weight"] = max(item["weight"], round(float(weight), 3))
    item["aliases"] = sorted(set(item["aliases"] + aliases), key=str.casefold)
    proof = _evidence(reference, str(matched_text if matched_text is not None else label))
    if proof not in item["evidence"]:
        item["evidence"].append(proof)


def _iter_mapping_items(value: Any) -> Iterable[tuple[int, dict[str, Any]]]:
    if isinstance(value, list):
        for index, item in enumerate(value):
            if isinstance(item, dict):
                yield index, item


def extract_report_tags(
    report_id: str,
    catalog_item: dict[str, Any],
    report: dict[str, Any],
    config: dict[str, Any],
    manual: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract a bounded, deterministic tag set from one report."""

    tags: dict[tuple[str, str], dict[str, Any]] = {}
    category = report.get("category", {}) if isinstance(report.get("category"), dict) else {}
    category_values = [
        catalog_item.get("mid_category") or category.get("middle"),
        catalog_item.get("sub_category") or category.get("sub"),
        catalog_item.get("detail_category") or category.get("detail"),
    ]
    for index, value in enumerate(category_values):
        _add_tag(
            tags,
            label=value,
            concept_type="domain",
            weight=0.94 - index * 0.01,
            reference=("category.middle", "category.sub", "category.detail")[index],
            matched_text=value,
            config=config,
        )

    for index, keyword in enumerate(report.get("keywords", [])):
        _add_tag(
            tags,
            label=keyword,
            concept_type=_classify_term(_clean_text(keyword)),
            weight=1.0,
            reference=f"keywords[{index}]",
            matched_text=keyword,
            config=config,
        )

    term_box = report.get("term_box", {})
    term_items = term_box.get("items", []) if isinstance(term_box, dict) else []
    for index, item in _iter_mapping_items(term_items):
        term = item.get("term", "")
        description = item.get("description", "")
        _add_tag(
            tags,
            label=term,
            concept_type=_classify_term(_clean_text(term), _clean_text(description)),
            weight=0.98,
            reference=f"term_box.items[{index}].term",
            matched_text=term,
            config=config,
        )

    flow = report.get("flow_diagram", {})
    steps = flow.get("steps", []) if isinstance(flow, dict) else []
    for index, step in enumerate(steps):
        _add_tag(
            tags,
            label=step,
            concept_type="mechanism",
            weight=0.82,
            reference=f"flow_diagram.steps[{index}]",
            matched_text=step,
            config=config,
        )

    for index, section in _iter_mapping_items(report.get("sections", [])):
        title = section.get("title", "")
        _add_tag(
            tags,
            label=title,
            concept_type="theme",
            weight=0.78,
            reference=f"sections[{index}].title",
            matched_text=title,
            config=config,
        )

    for index, table in _iter_mapping_items(report.get("tables", [])):
        title = table.get("title", "")
        _add_tag(
            tags,
            label=title,
            concept_type="theme",
            weight=0.68,
            reference=f"tables[{index}].title",
            matched_text=title,
            config=config,
        )

    quotation = report.get("quotation", {})
    if isinstance(quotation, dict):
        _add_tag(
            tags,
            label=_entity_label(quotation.get("attribution", "")),
            concept_type="entity",
            weight=0.84,
            reference="quotation.attribution",
            matched_text=quotation.get("attribution", ""),
            config=config,
        )
        _add_tag(
            tags,
            label=quotation.get("source_title", ""),
            concept_type="work",
            weight=0.72,
            reference="quotation.source_title",
            matched_text=quotation.get("source_title", ""),
            config=config,
        )

    for index, item in _iter_mapping_items(report.get("further_reading", [])):
        title = item.get("title") or item.get("name")
        _add_tag(
            tags,
            label=title,
            concept_type="work",
            weight=0.58,
            reference=f"further_reading[{index}].title",
            matched_text=title,
            config=config,
        )

    manual = manual or {}
    excluded = {
        _lookup_key(normalize_label(item, config)[0])
        for item in manual.get("exclude", [])
    }
    for item in manual.get("add", []):
        if not isinstance(item, dict) or not item.get("evidence"):
            raise ValueError(f"{report_id}의 수동 concept에는 evidence가 필요합니다.")
        evidence_items = item["evidence"] if isinstance(item["evidence"], list) else [item["evidence"]]
        for proof in evidence_items:
            if isinstance(proof, dict):
                reference = str(proof.get("reference", "manual"))
                matched_text = proof.get("matched_text", item.get("label", ""))
            else:
                reference = str(proof)
                matched_text = item.get("label", "")
            _add_tag(
                tags,
                label=item.get("label", ""),
                concept_type=str(item.get("type", "concept")),
                weight=float(item.get("weight", 1.0)),
                reference=reference,
                matched_text=matched_text,
                config=config,
            )

    # A term can occur as a keyword, taxonomy value and glossary item.  Keep one
    # visible tag per normalized label, preferring the strongest source, while
    # retaining all evidence and aliases from the other occurrences.
    collapsed: dict[str, dict[str, Any]] = {}
    for (normalized, _), item in tags.items():
        if normalized in excluded:
            continue
        current = collapsed.get(normalized)
        if current is None or item["weight"] > current["weight"]:
            replacement = dict(item)
            if current is not None:
                replacement["aliases"] = sorted(
                    set(replacement["aliases"] + current["aliases"]),
                    key=str.casefold,
                )
                replacement["evidence"] = replacement["evidence"] + [
                    proof for proof in current["evidence"] if proof not in replacement["evidence"]
                ]
            collapsed[normalized] = replacement
        else:
            current["aliases"] = sorted(
                set(current["aliases"] + item["aliases"]),
                key=str.casefold,
            )
            current["evidence"] += [
                proof for proof in item["evidence"] if proof not in current["evidence"]
            ]
    selected = list(collapsed.values())
    selected.sort(key=lambda item: (-item["weight"], item["type"], item["label"].casefold()))
    max_tags = int(config.get("max_tags_per_report", 40))
    selected = selected[:max_tags]
    return {
        "report_id": report_id,
        "date": catalog_item.get("date", ""),
        "title": catalog_item.get("title", ""),
        "main_category": catalog_item.get("main_category", ""),
        "tags": selected,
    }


def _iter_report_text(report: dict[str, Any]) -> Iterable[tuple[str, str]]:
    for key in ("title", "subtitle", "abstract"):
        value = _clean_text(report.get(key))
        if value:
            yield key, value
    for index, keyword in enumerate(report.get("keywords", [])):
        yield f"keywords[{index}]", _clean_text(keyword)
    term_box = report.get("term_box", {})
    for index, item in _iter_mapping_items(term_box.get("items", []) if isinstance(term_box, dict) else []):
        yield f"term_box.items[{index}].term", _clean_text(item.get("term"))
        yield f"term_box.items[{index}].description", _clean_text(item.get("description"))
    for index, section in _iter_mapping_items(report.get("sections", [])):
        yield f"sections[{index}].title", _clean_text(section.get("title"))
        for body_index, paragraph in enumerate(section.get("body", [])):
            yield f"sections[{index}].body[{body_index}]", _clean_text(paragraph)


def _pattern_evidence(report: dict[str, Any], patterns: list[str]) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    for reference, text in _iter_report_text(report):
        for pattern in patterns:
            if pattern.casefold() in text.casefold():
                proof = _evidence(reference, pattern)
                if proof not in evidence:
                    evidence.append(proof)
                break
        if len(evidence) >= 4:
            break
    return evidence


def _shared_concepts(
    annotations: list[dict[str, Any]],
    report_documents: dict[str, dict[str, Any]],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    report_by_id = {item["report_id"]: item for item in annotations}
    concept_members: dict[tuple[str, str], dict[str, Any]] = {}

    exact: dict[tuple[str, str], list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for annotation in annotations:
        for tag in annotation["tags"]:
            if tag["type"] in SHARED_EXACT_TYPES and tag["weight"] >= 0.9:
                exact[(_lookup_key(tag["normalized_label"]), tag["type"])].append((annotation, tag))
    for (normalized, concept_type), members in exact.items():
        report_ids = sorted({annotation["report_id"] for annotation, _ in members})
        categories = sorted({annotation["main_category"] for annotation, _ in members})
        if len(report_ids) < 2 or len(categories) < 2:
            continue
        label = members[0][1]["normalized_label"]
        concept_members[(normalized, concept_type)] = {
            "label": label,
            "type": concept_type,
            "provenance": "exact-normalized-tag",
            "members": {
                report_id: next(
                    tag["evidence"]
                    for annotation, tag in members
                    if annotation["report_id"] == report_id
                )
                for report_id in report_ids
            },
        }

    for rule in config.get("hub_rules", []):
        if not isinstance(rule, dict):
            continue
        label = _clean_text(rule.get("label"))
        concept_type = str(rule.get("type", "concept"))
        patterns = [_clean_text(item) for item in rule.get("patterns", []) if _clean_text(item)]
        if not label or concept_type not in ALLOWED_TYPES or not patterns:
            raise ValueError("concept hub rule의 label, type, patterns를 확인하세요.")
        ranked_members: list[tuple[int, str, list[dict[str, str]]]] = []
        for report_id, document in report_documents.items():
            evidence = _pattern_evidence(document, patterns)
            if evidence:
                # A match in a title, keyword or term box is stronger than a
                # passing mention in a body paragraph.  This ranking prevents
                # broad hubs from turning the graph into an unreadable hairball.
                relevance = sum(
                    3 if ".body[" not in proof["reference"] else 1
                    for proof in evidence
                )
                ranked_members.append((relevance, report_id, evidence))
        ranked_members.sort(key=lambda item: (-item[0], item[1]))
        max_reports = max(2, int(rule.get("max_reports", 12)))
        members = {
            report_id: evidence
            for _, report_id, evidence in ranked_members[:max_reports]
        }
        categories = {report_by_id[report_id]["main_category"] for report_id in members}
        if len(members) < 2 or len(categories) < 2:
            continue
        concept_members[(_lookup_key(label), concept_type)] = {
            "label": label,
            "type": concept_type,
            "provenance": "curated-pattern-rule",
            "members": members,
        }

    concepts: list[dict[str, Any]] = []
    for (normalized, concept_type), item in concept_members.items():
        report_ids = sorted(item["members"])
        main_categories = sorted({report_by_id[report_id]["main_category"] for report_id in report_ids})
        concepts.append(
            {
                "concept_id": _stable_id("con", concept_type, normalized),
                "label": item["label"],
                "normalized_label": item["label"],
                "type": concept_type,
                "provenance": item["provenance"],
                "report_count": len(report_ids),
                "main_categories": main_categories,
                "reports": [
                    {
                        "report_id": report_id,
                        "evidence": item["members"][report_id],
                    }
                    for report_id in report_ids
                ],
            }
        )
    concepts.sort(key=lambda item: (-item["report_count"], item["label"].casefold()))
    return concepts


def build_report_concepts(
    root_dir: Path,
    reports: list[dict[str, Any]],
    config: dict[str, Any],
    manual_annotations: dict[str, Any] | None,
    generated_at: str,
) -> dict[str, Any]:
    if config.get("schema_version") != "1.0":
        raise ValueError("concept aliases schema_version은 1.0이어야 합니다.")
    manual_annotations = manual_annotations or {"schema_version": "1.0", "reports": {}}
    if manual_annotations.get("schema_version") != "1.0":
        raise ValueError("knowledge annotations schema_version은 1.0이어야 합니다.")
    manual_reports = manual_annotations.get("reports", {})
    if not isinstance(manual_reports, dict):
        raise ValueError("knowledge annotations reports는 object여야 합니다.")

    annotations: list[dict[str, Any]] = []
    report_documents: dict[str, dict[str, Any]] = {}
    for catalog_item in sorted(reports, key=lambda item: item["report_id"]):
        json_path = Path(str(catalog_item.get("html_path", ""))).with_suffix(".json")
        document = load_json(root_dir / json_path, None)
        if not isinstance(document, dict):
            raise ValueError(f"개념 추출용 리포트 JSON이 없습니다: {json_path.as_posix()}")
        report_id = catalog_item["report_id"]
        report_documents[report_id] = document
        annotations.append(
            extract_report_tags(
                report_id,
                catalog_item,
                document,
                config,
                manual_reports.get(report_id),
            )
        )

    concepts = _shared_concepts(annotations, report_documents, config)
    payload = {
        "schema_version": "1.0",
        "algorithm_version": "structured-evidence-v1",
        "generated_at": generated_at,
        "stats": {
            "reports": len(annotations),
            "tags": sum(len(item["tags"]) for item in annotations),
            "shared_concepts": len(concepts),
            "min_tags_per_report": min((len(item["tags"]) for item in annotations), default=0),
            "max_tags_per_report": max((len(item["tags"]) for item in annotations), default=0),
        },
        "reports": annotations,
        "shared_concepts": concepts,
    }
    validate_report_concepts(payload)
    return payload


def validate_report_concepts(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != "1.0":
        raise ValueError("report concepts schema_version은 1.0이어야 합니다.")
    reports = payload.get("reports")
    concepts = payload.get("shared_concepts")
    if not isinstance(reports, list) or not isinstance(concepts, list):
        raise ValueError("report concepts reports와 shared_concepts는 list여야 합니다.")
    report_ids = {item.get("report_id") for item in reports if isinstance(item, dict)}
    if len(report_ids) != len(reports):
        raise ValueError("report concepts report_id가 없거나 중복되었습니다.")
    for report in reports:
        tags = report.get("tags")
        if not isinstance(tags, list):
            raise ValueError("report concept tags는 list여야 합니다.")
        for tag in tags:
            if tag.get("type") not in ALLOWED_TYPES or not tag.get("evidence"):
                raise ValueError("모든 report concept tag에는 유효한 type과 evidence가 필요합니다.")
    for concept in concepts:
        members = concept.get("reports", [])
        categories = concept.get("main_categories", [])
        if len(members) < 2 or len(categories) < 2:
            raise ValueError("공유 concept는 두 리포트와 두 대분류 이상에 걸쳐야 합니다.")
        if any(member.get("report_id") not in report_ids or not member.get("evidence") for member in members):
            raise ValueError("공유 concept의 모든 연결에는 유효한 report_id와 evidence가 필요합니다.")
