import copy
import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from build_knowledge_graph import build_public_data  # noqa: E402
from report_pipeline.knowledge_graph import (  # noqa: E402
    build_knowledge_graph,
    validate_knowledge_graph,
)
from report_pipeline.taxonomy import load_aliases, load_taxonomy  # noqa: E402


class KnowledgeGraphTests(unittest.TestCase):
    def setUp(self):
        self.taxonomy = load_taxonomy(ROOT_DIR / "config" / "topic_taxonomy_v2.json")
        self.aliases = load_aliases(ROOT_DIR / "config" / "taxonomy_aliases.json")

    def test_current_catalog_builds_valid_hierarchy_graph(self):
        public_taxonomy, reports, graph = build_public_data()

        self.assertEqual(10, len(public_taxonomy["category_order"]))
        self.assertEqual(len(reports), graph["stats"]["reports"])
        self.assertEqual(10, graph["stats"]["categories"])
        self.assertEqual(0, graph["stats"]["semantic_edges"])
        validate_knowledge_graph(graph)

    def test_public_graph_build_is_deterministic(self):
        first = build_public_data()[2]
        second = build_public_data()[2]

        self.assertEqual(first, second)

    def test_legacy_categories_are_normalized(self):
        report = {
            "date": "2026-08-19",
            "title": "도서관 분류의 정치학",
            "main_category": "언어·문자",
            "mid_category": "지식분류",
            "sub_category": "도서 분류 체계",
            "detail_category": "분류 기호와 지식의 위계",
            "html_path": "outputs/example.html",
            "pdf_path": "outputs/example.pdf",
            "status": "published_api",
        }

        graph = build_knowledge_graph([report], self.taxonomy, self.aliases)
        report_node = next(node for node in graph["nodes"] if node["type"] == "report")

        self.assertEqual("언어·미디어·지식", report_node["main_category"])

    def test_semantic_edge_requires_evidence(self):
        reports = [
            {
                "report_id": "rpt-a",
                "date": "2026-01-01",
                "title": "A",
                "main_category": "인문·철학",
                "mid_category": "철학",
                "sub_category": "개념",
                "detail_category": "A",
                "status": "published_api",
            },
            {
                "report_id": "rpt-b",
                "date": "2026-01-02",
                "title": "B",
                "main_category": "과학·수학",
                "mid_category": "과학",
                "sub_category": "개념",
                "detail_category": "B",
                "status": "published_api",
            },
        ]
        overrides = {
            "schema_version": "1.0",
            "edges": [
                {
                    "source_report_id": "rpt-a",
                    "target_report_id": "rpt-b",
                    "relation_type": "contrast",
                    "score": 0.8,
                    "explanation": "검증되지 않은 연결",
                    "evidence": [],
                }
            ],
        }

        with self.assertRaisesRegex(ValueError, "evidence"):
            build_knowledge_graph(
                copy.deepcopy(reports),
                self.taxonomy,
                self.aliases,
                overrides,
            )


if __name__ == "__main__":
    unittest.main()
