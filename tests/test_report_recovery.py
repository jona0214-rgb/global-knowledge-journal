import copy
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "scripts"))

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

try:
    import dotenv  # noqa: F401
except ModuleNotFoundError:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *args, **kwargs: None
    sys.modules["dotenv"] = dotenv_stub

try:
    import openai  # noqa: F401
except ModuleNotFoundError:
    openai_stub = types.ModuleType("openai")

    class StubOpenAIError(Exception):
        pass

    openai_stub.APIConnectionError = StubOpenAIError
    openai_stub.APITimeoutError = StubOpenAIError
    openai_stub.InternalServerError = StubOpenAIError
    openai_stub.RateLimitError = StubOpenAIError
    openai_stub.OpenAI = object
    sys.modules["openai"] = openai_stub

import generate_report as report_generator
import run_daily_report as report_runner
import verify_published_site as publish_verifier


class ReportRecoveryTests(unittest.TestCase):
    def test_resolve_report_date_accepts_past_date(self):
        with patch.object(report_runner, "get_today_kst", return_value="2026-08-27"):
            self.assertEqual(
                "2026-08-26",
                report_runner.resolve_report_date("2026-08-26"),
            )

    def test_resolve_report_date_rejects_invalid_and_future_dates(self):
        with patch.object(report_runner, "get_today_kst", return_value="2026-08-27"):
            with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
                report_runner.resolve_report_date("2026/08/26")
            with self.assertRaisesRegex(ValueError, "미래 날짜"):
                report_runner.resolve_report_date("2026-08-28")

    def test_source_url_normalization_ignores_tracking_and_trailing_slash(self):
        source_url = "https://Example.com/article/?b=2&a=1"
        quotation_url = (
            "https://example.com/article?a=1&b=2&utm_source=newsletter#quote"
        )
        self.assertEqual(
            report_runner.normalize_source_url_for_comparison(source_url),
            report_runner.normalize_source_url_for_comparison(quotation_url),
        )

    def test_validation_reuses_exact_source_url_after_normalized_match(self):
        latest = report_runner.load_json(report_runner.LATEST_JSON_PATH, default={})
        report_path = ROOT_DIR / latest["html_path"].replace(".html", ".json")
        report = copy.deepcopy(report_runner.load_json(report_path, default={}))
        exact_source_url = report["sources"][0]["url"]
        separator = "&" if "?" in exact_source_url else "?"
        report["quotation"]["source_url"] = (
            exact_source_url + separator + "utm_source=recovery-test"
        )

        report_runner.validate_report_structure(report)

        self.assertEqual(exact_source_url, report["quotation"]["source_url"])

    def test_backfill_keeps_newest_catalog_item_as_latest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            reports_path = temp_path / "reports.json"
            latest_path = temp_path / "latest.json"
            manifest_path = temp_path / "manifest.json"
            existing = {
                "date": "2026-08-27",
                "title": "newer",
                "status": "published_api",
            }
            reports_path.write_text(
                json.dumps([existing], ensure_ascii=False),
                encoding="utf-8",
            )
            backfill_report = {
                "date": "2026-08-26",
                "title": "backfill",
                "subtitle": "missing date",
                "category": {
                    "main": "생명·건강",
                    "middle": "생명과학",
                    "sub": "회복",
                    "detail": "자동 복구",
                },
                "status": "published_api",
            }

            with (
                patch.object(report_runner, "REPORTS_JSON_PATH", reports_path),
                patch.object(report_runner, "LATEST_JSON_PATH", latest_path),
                patch.object(report_runner, "MANIFEST_PATH", manifest_path),
            ):
                report_runner.update_public_catalog(
                    backfill_report,
                    Path("outputs/backfill.html"),
                    Path("outputs/backfill.pdf"),
                )

            latest = json.loads(latest_path.read_text(encoding="utf-8"))
            reports = json.loads(reports_path.read_text(encoding="utf-8"))
            self.assertEqual("2026-08-27", latest["date"])
            self.assertEqual(
                ["2026-08-27", "2026-08-26"],
                [item["date"] for item in reports],
            )

    def test_validation_failure_never_calls_publish(self):
        topic = {
            "topic": "복구 검증 테스트",
            "main_category": "기술·공학",
            "mid_category": "자동화",
            "sub_category": "검증",
            "detail_category": "안전 발행",
        }
        generated_report = {
            "title": topic["topic"],
            "category": {},
            "sections": [],
        }

        with (
            patch.object(report_runner, "load_json", return_value={}),
            patch.object(report_runner, "select_topic", return_value=topic),
            patch.object(
                report_generator,
                "generate_report",
                return_value=generated_report,
            ),
            patch.object(
                report_runner,
                "validate_report_structure",
                side_effect=ValueError("필수 섹션이 누락되었습니다: 01"),
            ),
            patch.object(report_runner, "save_render_publish_report") as publish_mock,
            patch.dict(
                os.environ,
                {
                    "REPORT_SKIP_EXISTING_DATE": "0",
                    "REPORT_VALIDATION_RETRIES": "0",
                    "REPORT_DATE": "",
                },
            ),
        ):
            with self.assertRaisesRegex(ValueError, "필수 섹션이 누락"):
                report_runner.run_api()

        publish_mock.assert_not_called()

    def test_mock_mode_accepts_recovery_date_without_publishing_catalog(self):
        topic = {"topic": "mock", "main_category": "기술·공학"}
        report = {"date": "2026-08-26", "title": "mock", "tables": []}
        with (
            patch.object(report_runner, "load_json", return_value={}),
            patch.object(report_runner, "select_topic", return_value=topic),
            patch.object(report_runner, "create_mock_report", return_value=report),
            patch.object(report_runner, "save_render_publish_report") as publish_mock,
            patch.object(report_runner, "get_today_kst", return_value="2026-08-27"),
        ):
            report_runner.run_mock(report_date="2026-08-26")

        publish_mock.assert_called_once_with(report, {}, mode="mock")

    def test_generation_timeline_records_0500_schedule_delay(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            history_path = temp_path / "generation-history.json"
            status_path = temp_path / "generation-status.json"
            report = {
                "date": "2026-08-29",
                "title": "측정 테스트",
                "status": "published_api",
            }
            with (
                patch.object(
                    report_runner,
                    "GENERATION_HISTORY_PATH",
                    history_path,
                ),
                patch.object(
                    report_runner,
                    "GENERATION_STATUS_PATH",
                    status_path,
                ),
                patch.dict(
                    os.environ,
                    {
                        "REPORT_SCHEDULE_CRON": "0 20 * * *",
                        "REPORT_RUN_STARTED_AT": "2026-08-28T20:02:00Z",
                        "GITHUB_EVENT_NAME": "schedule",
                        "GITHUB_RUN_ID": "12345",
                        "GITHUB_RUN_ATTEMPT": "1",
                        "GITHUB_REPOSITORY": "owner/repo",
                        "GITHUB_SERVER_URL": "https://github.com",
                        "GITHUB_SHA": "abc123",
                    },
                ),
            ):
                entry = report_runner.record_generation_timeline(
                    report=report,
                    generation_started_at="2026-08-28T20:03:00Z",
                    generation_completed_at="2026-08-28T20:07:00Z",
                    catalog_updated_at="2026-08-28T20:08:00Z",
                    validation_attempts=1,
                )

            self.assertEqual(
                "2026-08-29T05:00:00+09:00",
                entry["scheduled_for_kst"],
            )
            self.assertEqual(120, entry["scheduler_delay_seconds"])
            self.assertEqual(60, entry["setup_duration_seconds"])
            self.assertEqual(300, entry["generation_duration_seconds"])
            self.assertEqual("12345", entry["run_id"])
            history = json.loads(history_path.read_text(encoding="utf-8"))
            status = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertEqual([entry], history)
            self.assertEqual(entry, status)

    def test_pages_verifier_checks_catalog_and_pdf(self):
        expected = {
            "date": "2026-08-29",
            "status": "published_api",
            "pdf_url": "outputs/report.pdf",
        }
        with (
            patch.object(
                publish_verifier,
                "fetch_json",
                return_value=[expected],
            ) as fetch_mock,
            patch.object(
                publish_verifier,
                "asset_is_visible",
                return_value=True,
            ) as asset_mock,
        ):
            visible = publish_verifier.verify_once(
                "https://example.test/project/",
                "2026-08-29",
                expected,
            )

        self.assertTrue(visible)
        self.assertIn("public/reports.json", fetch_mock.call_args.args[0])
        self.assertIn("outputs/report.pdf", asset_mock.call_args.args[0])

    def test_transient_openai_error_is_retried(self):
        class TemporaryOpenAIError(Exception):
            pass

        calls = []

        def operation():
            calls.append(1)
            if len(calls) == 1:
                raise TemporaryOpenAIError("connection reset")
            return "ok"

        with (
            patch.object(
                report_generator,
                "TRANSIENT_OPENAI_ERRORS",
                (TemporaryOpenAIError,),
            ),
            patch.dict(
                os.environ,
                {
                    "OPENAI_CONNECTION_RETRIES": "2",
                    "OPENAI_RETRY_BASE_SECONDS": "0",
                },
            ),
            patch.object(report_generator.time, "sleep") as sleep_mock,
        ):
            result = report_generator.call_openai_with_transient_retries(
                operation,
                "test operation",
            )

        self.assertEqual("ok", result)
        self.assertEqual(2, len(calls))
        sleep_mock.assert_called_once_with(0.0)

    def test_transient_openai_error_exhaustion_is_clear(self):
        class TemporaryOpenAIError(Exception):
            pass

        with (
            patch.object(
                report_generator,
                "TRANSIENT_OPENAI_ERRORS",
                (TemporaryOpenAIError,),
            ),
            patch.dict(
                os.environ,
                {
                    "OPENAI_CONNECTION_RETRIES": "1",
                    "OPENAI_RETRY_BASE_SECONDS": "0",
                },
            ),
            patch.object(report_generator.time, "sleep"),
        ):
            with self.assertRaisesRegex(RuntimeError, "재시도 후에도"):
                report_generator.call_openai_with_transient_retries(
                    lambda: (_ for _ in ()).throw(
                        TemporaryOpenAIError("connection reset")
                    ),
                    "test operation",
                )

    def test_long_api_timeout_is_not_retried(self):
        class LongTimeoutError(Exception):
            pass

        calls = []

        def operation():
            calls.append(1)
            raise LongTimeoutError("request timed out")

        with (
            patch.object(report_generator, "APITimeoutError", LongTimeoutError),
            patch.object(
                report_generator,
                "TRANSIENT_OPENAI_ERRORS",
                (LongTimeoutError,),
            ),
            patch.dict(
                os.environ,
                {
                    "OPENAI_CONNECTION_RETRIES": "2",
                    "OPENAI_RETRY_BASE_SECONDS": "0",
                },
            ),
            patch.object(report_generator.time, "sleep") as sleep_mock,
        ):
            with self.assertRaises(LongTimeoutError):
                report_generator.call_openai_with_transient_retries(
                    operation,
                    "test operation",
                )

        self.assertEqual(1, len(calls))
        sleep_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
