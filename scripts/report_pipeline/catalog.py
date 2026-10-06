"""Pure helpers for versioned public report catalog data."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any


def public_asset_path(root_dir: Path, value: Any) -> str:
    text = str(value or "").replace("\\", "/")
    if "outputs/" in text:
        return "outputs/" + text.split("outputs/", 1)[1]
    try:
        return Path(value).resolve().relative_to(root_dir.resolve()).as_posix()
    except (TypeError, ValueError):
        return Path(text).name


def _identifier_fragment(value: str) -> str:
    fragment = re.sub(r"[^0-9a-z]+", "-", value.lower()).strip("-")
    if fragment:
        return fragment[:48]
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def build_report_id(item: dict[str, Any]) -> str:
    existing = str(item.get("report_id", "")).strip()
    if existing:
        return existing
    date = re.sub(r"[^0-9]", "", str(item.get("date", ""))) or "undated"
    path_hint = str(item.get("html_path") or item.get("html_url") or "")
    path_stem = Path(path_hint).stem
    path_stem = re.sub(r"^\d{8}_", "", path_stem)
    path_stem = re.sub(r"_Report$", "", path_stem, flags=re.IGNORECASE)
    title_hint = str(item.get("title_slug") or path_stem or item.get("title", "report"))
    return f"rpt-{date}-{_identifier_fragment(title_hint)}"


def normalize_catalog_item(root_dir: Path, item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    for key in ("html_path", "pdf_path", "html_url", "pdf_url"):
        value = normalized.get(key)
        if value and value != "...":
            normalized[key] = public_asset_path(root_dir, value)
    if normalized.get("html_path") and not normalized.get("html_url"):
        normalized["html_url"] = normalized["html_path"]
    if normalized.get("pdf_path") and not normalized.get("pdf_url"):
        normalized["pdf_url"] = normalized["pdf_path"]
    normalized["report_id"] = build_report_id(normalized)
    return normalized


def build_catalog_item(
    root_dir: Path,
    report: dict[str, Any],
    html_path: Path,
    pdf_path: Path,
) -> dict[str, Any]:
    item = {
        "date": report["date"],
        "title": report["title"],
        "subtitle": report.get("subtitle", ""),
        "main_category": report["category"]["main"],
        "mid_category": report["category"]["middle"],
        "sub_category": report["category"]["sub"],
        "detail_category": report["category"]["detail"],
        "taxonomy_version": report.get("taxonomy_version", "2.0"),
        "html_path": public_asset_path(root_dir, html_path),
        "pdf_path": public_asset_path(root_dir, pdf_path),
        "status": report.get("status", "published_mock"),
    }
    item["html_url"] = item["html_path"]
    item["pdf_url"] = item["pdf_path"]
    item["report_id"] = build_report_id(item)
    return item


def merge_catalog(
    root_dir: Path,
    existing: list[dict[str, Any]],
    new_item: dict[str, Any],
) -> list[dict[str, Any]]:
    normalized = [
        normalize_catalog_item(root_dir, item)
        for item in existing
        if isinstance(item, dict) and item.get("date") != new_item["date"]
    ]
    normalized.append(normalize_catalog_item(root_dir, new_item))
    normalized.sort(key=lambda item: str(item.get("date", "")), reverse=True)
    return normalized
