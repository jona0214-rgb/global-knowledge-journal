import copy
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "scripts"))

# 주제 선택 테스트는 렌더러를 사용하지 않는다. 최소 테스트 환경에서도
# 모듈을 불러올 수 있도록 선택적 렌더링 의존성만 대체한다.
try:
    import jinja2  # noqa: F401
except ModuleNotFoundError:
    jinja2_stub = types.ModuleType("jinja2")
    jinja2_stub.Environment = object
    jinja2_stub.FileSystemLoader = object
    sys.modules["jinja2"] = jinja2_stub

try:
    import playwright.sync_api  # noqa: F401
except ModuleNotFoundError:
    playwright_stub = types.ModuleType("playwright")
    playwright_sync_stub = types.ModuleType("playwright.sync_api")
    playwright_sync_stub.sync_playwright = lambda: None
    sys.modules["playwright"] = playwright_stub
    sys.modules["playwright.sync_api"] = playwright_sync_stub

import run_daily_report as report_runner


class TopicRotationTests(unittest.TestCase):
    def setUp(self):
        self.taxonomy = report_runner.load_topic_taxonomy()
        self.topic_db = report_runner.load_json(
            report_runner.TOPIC_DB_PATH,
            default={},
        )

    def test_taxonomy_has_ten_unique_categories_and_fifty_seed_topics(self):
        category_order = self.taxonomy["category_order"]
        self.assertEqual(10, len(category_order))
        self.assertEqual(10, len(set(category_order)))
        seed_count = sum(
            len(category["seed_topics"])
            for category in self.taxonomy["categories"]
        )
        self.assertEqual(50, seed_count)

    def test_current_history_moves_from_history_to_art(self):
        topic = report_runner.select_topic(copy.deepcopy(self.topic_db))
        self.assertEqual("예술·디자인", topic["main_category"])
        self.assertTrue(topic["mid_category"])
        self.assertTrue(topic["sub_category"])
        self.assertTrue(topic["detail_category"])

    @patch.object(report_runner, "save_json", lambda *args, **kwargs: None)
    def test_successful_publications_complete_one_round_robin_cycle(self):
        topic_db = {
            "recent_reports": [],
            "category_rotation": {"next_main_category": "인문·철학"},
        }
        selected_categories = []

        for day in range(10):
            topic = report_runner.select_topic(topic_db)
            selected_categories.append(topic["main_category"])
            report = {
                "date": f"2026-09-{day + 1:02d}",
                "title": topic["topic"],
                "category": {
                    "main": topic["main_category"],
                    "middle": topic["mid_category"],
                    "sub": topic["sub_category"],
                    "detail": topic["detail_category"],
                },
                "keywords": ["test"],
                "status": "published_api",
            }
            report_runner.update_topic_db(
                topic_db,
                report,
                Path("outputs/test.html"),
                Path("outputs/test.pdf"),
            )

        self.assertEqual(self.taxonomy["category_order"], selected_categories)
        self.assertEqual(
            self.taxonomy["category_order"][0],
            topic_db["category_rotation"]["next_main_category"],
        )
        self.assertEqual(1, topic_db["category_rotation"]["completed_cycles"])

    def test_exhausted_category_accepts_only_valid_new_candidate(self):
        topic_db = copy.deepcopy(self.topic_db)
        report_runner.merge_taxonomy_candidates(topic_db, self.taxonomy)
        topic_db["category_rotation"] = {
            "next_main_category": "예술·디자인"
        }
        for candidate in topic_db["candidate_pool"]:
            if candidate.get("main_category") == "예술·디자인":
                candidate["status"] = "used"

        with self.assertRaises(report_runner.TopicPoolExhaustedError):
            report_runner.select_topic(topic_db)

        added = report_runner.add_generated_topic_candidates(
            topic_db,
            "예술·디자인",
            [
                {
                    "topic": "무대의 침묵: 여백은 어떻게 공연의 긴장을 만드는가",
                    "mid_category": "공연미학",
                    "sub_category": "침묵과 시간",
                    "detail_category": "무대 여백의 긴장",
                    "priority": 0.8,
                }
            ],
        )

        self.assertEqual(1, added)
        selected = report_runner.select_topic(topic_db)
        self.assertEqual("예술·디자인", selected["main_category"])


if __name__ == "__main__":
    unittest.main()
