"""Canonical taxonomy loading, validation, migration, and public export."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .json_store import load_json


def load_taxonomy(path: Path) -> dict[str, Any]:
    taxonomy = load_json(path, {})
    validate_taxonomy(taxonomy)
    return taxonomy


def load_aliases(path: Path) -> dict[str, Any]:
    aliases = load_json(path, {})
    if aliases.get("schema_version") != "1.0":
        raise ValueError("taxonomy alias schema_version은 1.0이어야 합니다.")
    for key in ("legacy_main_category_map", "legacy_middle_category_map"):
        if not isinstance(aliases.get(key), dict):
            raise ValueError(f"taxonomy alias의 {key}는 object여야 합니다.")
    return aliases


def validate_taxonomy(taxonomy: dict[str, Any]) -> None:
    category_order = taxonomy.get("category_order")
    categories = taxonomy.get("categories")
    if taxonomy.get("taxonomy_version") != "2.0":
        raise ValueError("taxonomy_version은 2.0이어야 합니다.")
    if not isinstance(category_order, list) or len(category_order) != 10:
        raise ValueError("taxonomy에는 대분류가 정확히 10개 있어야 합니다.")
    if len(set(category_order)) != len(category_order):
        raise ValueError("taxonomy category_order에 중복이 있습니다.")
    if not isinstance(categories, list):
        raise ValueError("taxonomy categories는 list여야 합니다.")
    category_names = {
        str(category.get("name", "")).strip()
        for category in categories
        if isinstance(category, dict)
    }
    if category_names != set(category_order):
        raise ValueError("taxonomy category_order와 categories가 일치하지 않습니다.")


def canonical_main_category(
    item: dict[str, Any],
    taxonomy: dict[str, Any],
    aliases: dict[str, Any],
) -> str:
    category = item.get("category")
    category = category if isinstance(category, dict) else {}
    raw_main = str(
        item.get("main_category")
        or category.get("main", "")
    ).strip()
    if raw_main in taxonomy["category_order"]:
        return raw_main

    raw_middle = str(
        item.get("mid_category")
        or category.get("middle", "")
    ).strip()
    middle_map = aliases["legacy_middle_category_map"]
    main_map = aliases["legacy_main_category_map"]
    return str(middle_map.get(raw_middle) or main_map.get(raw_main) or "미분류")


def public_taxonomy_payload(
    taxonomy: dict[str, Any], aliases: dict[str, Any]
) -> dict[str, Any]:
    descriptions = {
        category["name"]: category.get("description", "")
        for category in taxonomy["categories"]
    }
    return {
        "schema_version": "1.0",
        "taxonomy_version": taxonomy["taxonomy_version"],
        "category_order": list(taxonomy["category_order"]),
        "categories": [
            {"name": name, "description": descriptions.get(name, "")}
            for name in taxonomy["category_order"]
        ],
        "aliases": {
            "main": dict(aliases["legacy_main_category_map"]),
            "middle": dict(aliases["legacy_middle_category_map"]),
        },
    }
