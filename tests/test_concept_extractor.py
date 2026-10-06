import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from build_knowledge_graph import build_public_bundle  # noqa: E402
from report_pipeline.concept_extractor import (  # noqa: E402
    extract_report_tags,
    validate_report_concepts,
)


class ConceptExtractorTests(unittest.TestCase):
    def test_current_reports_have_bounded_evidence_backed_tags(self):
        _, reports, concepts, _ = build_public_bundle()

        self.assertEqual(len(reports), len(concepts["reports"]))
        self.assertGreaterEqual(concepts["stats"]["min_tags_per_report"], 25)
        self.assertLessEqual(concepts["stats"]["max_tags_per_report"], 40)
        for report in concepts["reports"]:
            self.assertGreaterEqual(len(report["tags"]), 25, report["report_id"])
            self.assertLessEqual(len(report["tags"]), 40, report["report_id"])
            self.assertTrue(all(tag["evidence"] for tag in report["tags"]))

        validate_report_concepts(concepts)

    def test_shared_concepts_cross_category_boundaries(self):
        _, _, concepts, _ = build_public_bundle()

        self.assertGreaterEqual(len(concepts["shared_concepts"]), 5)
        for concept in concepts["shared_concepts"]:
            self.assertGreaterEqual(concept["report_count"], 2)
            self.assertGreaterEqual(len(concept["main_categories"]), 2)
            self.assertTrue(all(item["evidence"] for item in concept["reports"]))

    def test_manual_tag_requires_evidence(self):
        report = {
            "keywords": ["확률"],
            "category": {
                "middle": "수학",
                "sub": "확률론",
                "detail": "확률적 판단",
            },
            "term_box": {"items": []},
            "sections": [],
            "tables": [],
            "further_reading": [],
        }
        catalog = {
            "date": "2026-01-01",
            "title": "확률",
            "main_category": "과학·수학",
        }
        config = {
            "schema_version": "1.0",
            "max_tags_per_report": 40,
            "aliases": {},
            "stop_labels": [],
        }

        with self.assertRaisesRegex(ValueError, "evidence"):
            extract_report_tags(
                "rpt-test",
                catalog,
                report,
                config,
                {"add": [{"label": "베이즈 정리", "type": "method"}]},
            )


if __name__ == "__main__":
    unittest.main()
