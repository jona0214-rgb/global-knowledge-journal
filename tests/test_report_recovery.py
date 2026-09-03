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
    def load_validatable_latest_report(self):
        latest = report_runner.load_json(report_runner.LATEST_JSON_PATH, default={})
        report_path = ROOT_DIR / latest["html_path"].replace(".html", ".json")
        report = copy.deepcopy(report_runner.load_json(report_path, default={}))

        quotation = report.get("quotation", {})
        quotation.setdefault("source_type", "book")
        if quotation.get("kind") == "expert_advice":
            quotation["kind"] = "paraphrase"

        for section in report.get("sections", []):
            body = [
                paragraph.strip()
                for paragraph in section.get("body", [])
                if isinstance(paragraph, str)
                and not paragraph.strip().lower().startswith("section_notes_")
            ]
            if section.get("id") == "04" and len(body) < 5:
                body.append(
                    "이 사례는 향신료 교역이 상품 이동에 그치지 않고 기업 권력과 식민 통치, "
                    "지역 사회의 삶을 함께 바꾼 역사적 과정이었음을 구체적으로 보여준다. "
                    "따라서 교역의 성과뿐 아니라 그 비용과 책임도 함께 살펴야 한다."
                )
            section["body"] = body

        return report

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

    def test_api_schema_uses_fixed_sections_and_source_reference(self):
        canonical_schema = report_generator.load_json(
            report_generator.REPORT_SCHEMA_PATH
        )["schema"]

        api_schema = report_generator.build_api_response_schema(canonical_schema)
        properties = api_schema["properties"]

        self.assertEqual("object", properties["sections"]["type"])
        self.assertEqual(
            list(report_generator.REQUIRED_SECTION_IDS),
            properties["sections"]["required"],
        )
        self.assertEqual(
            set(report_generator.REQUIRED_SECTION_IDS),
            set(properties["sections"]["properties"]),
        )
        self.assertEqual("object", properties["sources"]["type"])
        self.assertEqual(
            list(report_generator.API_SOURCE_KEYS),
            properties["sources"]["required"],
        )
        quotation = properties["quotation"]
        self.assertIn("source_key", quotation["required"])
        self.assertNotIn("source_url", quotation["properties"])
        self.assertNotIn("source_title", quotation["properties"])
        self.assertEqual(
            list(report_generator.API_SOURCE_KEYS),
            quotation["properties"]["source_key"]["enum"],
        )

        # API용 변환이 저장 형식의 기준 schema를 변경하면 안 된다.
        self.assertEqual("array", canonical_schema["properties"]["sections"]["type"])
        self.assertEqual("array", canonical_schema["properties"]["sources"]["type"])

    def test_api_report_normalization_prevents_duplicate_sections_and_url_mismatch(self):
        report = self.load_validatable_latest_report()
        if len(report["sources"]) < 6:
            report["sources"].append(
                {
                    "publisher": "테스트 기관",
                    "title": "추가 검증 출처",
                    "url": "https://example.com/additional-validation-source",
                    "used_for": "API 출처 슬롯 검증",
                }
            )

        report["sections"] = {
            section["id"]: section
            for section in reversed(report["sections"])
        }
        report["sources"] = {
            source_key: source
            for source_key, source in zip(
                report_generator.API_SOURCE_KEYS,
                report["sources"][:6],
            )
        }
        selected_source = report["sources"]["source_3"]
        report["quotation"].pop("source_title", None)
        report["quotation"].pop("source_url", None)
        report["quotation"]["source_key"] = "source_3"

        normalized = report_generator.normalize_api_report(report)

        self.assertEqual(
            list(report_generator.REQUIRED_SECTION_IDS),
            [section["id"] for section in normalized["sections"]],
        )
        self.assertEqual(6, len(normalized["sources"]))
        self.assertEqual(
            selected_source["title"],
            normalized["quotation"]["source_title"],
        )
        self.assertEqual(
            selected_source["url"],
            normalized["quotation"]["source_url"],
        )
        self.assertNotIn("source_key", normalized["quotation"])
        report_runner.validate_report_structure(normalized)

    def test_api_report_normalization_rejects_missing_fixed_section(self):
        report = self.load_validatable_latest_report()
        report["sections"] = {
            section["id"]: section
            for section in report["sections"]
            if section["id"] != "06"
        }

        with self.assertRaisesRegex(ValueError, "고정 섹션이 누락.*06"):
            report_generator.normalize_api_report(report)

    def test_validation_reuses_exact_source_url_after_normalized_match(self):
        report = self.load_validatable_latest_report()
        exact_source_url = report["sources"][0]["url"]
        separator = "&" if "?" in exact_source_url else "?"
        report["quotation"]["source_url"] = (
            exact_source_url + separator + "utm_source=recovery-test"
        )

        report_runner.validate_report_structure(report)

        self.assertEqual(exact_source_url, report["quotation"]["source_url"])

    def test_validation_rejects_snake_case_instruction_leak(self):
        report = self.load_validatable_latest_report()
        case_study = next(
            section for section in report["sections"] if section.get("id") == "04"
        )
        case_study["body"][-1] = (
            "section_notes_paragraph_count_check_must_match_required_4_paragraphs_"
            "length_minimum_4_paragraphs_maximum_10_paragraphs_section_labels_"
            "general_structure"
        )

        with self.assertRaisesRegex(
            ValueError,
            "시스템 지시문·JSON 생성 메모",
        ):
            report_runner.validate_report_structure(report)

    def test_validation_rejects_body_padding_newlines(self):
        report = self.load_validatable_latest_report()
        report["sections"][0]["body"][0] += "\n\n\n"

        with self.assertRaisesRegex(ValueError, "본문 문단 내부 개행"):
            report_runner.validate_report_structure(report)

    def test_validation_rejects_unregistered_quotation_source_type(self):
        report = self.load_validatable_latest_report()
        report["quotation"]["source_type"] = "podcast"

        with self.assertRaisesRegex(ValueError, "등록된 출처 유형이 아닙니다"):
            report_runner.validate_report_structure(report)

    def test_new_quotation_source_type_can_be_added_in_config(self):
        report = self.load_validatable_latest_report()
        report["quotation"]["source_type"] = "podcast"

        with tempfile.TemporaryDirectory() as temp_dir:
            source_types_path = Path(temp_dir) / "quotation_source_types.json"
            source_types_path.write_text(
                json.dumps(
                    {
                        "version": "1.1",
                        "types": [
                            {
                                "id": "podcast",
                                "label": "팟캐스트에서의 대화",
                                "description": "공개 팟캐스트 대화",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with patch.object(
                report_runner,
                "QUOTATION_SOURCE_TYPES_PATH",
                source_types_path,
            ):
                report_runner.validate_report_structure(report)

    def test_report_prompt_loads_configured_quotation_source_types(self):
        prompt = report_generator.build_user_prompt(
            today="2026-08-30",
            selected_topic={
                "topic": "출처 유형 검증",
                "main_category": "역사·문화",
                "mid_category": "기록문화",
                "sub_category": "출처 분류",
            },
        )

        self.assertIn('"id": "book"', prompt)
        self.assertIn("도서 속의 문장", prompt)
        self.assertNotIn("{{ quotation_source_types }}", prompt)

    def test_template_does_not_render_legacy_expert_heading(self):
        template_text = (
            ROOT_DIR / "templates" / "report.html.j2"
        ).read_text(encoding="utf-8")

        self.assertNotIn("전문가의 첨언", template_text)
        self.assertIn("관련 문헌에서의 관점", template_text)

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

    def test_validation_retry_passes_exact_error_feedback_and_then_publishes(self):
        topic = {
            "topic": "구조 복구 피드백 테스트",
            "main_category": "기술·공학",
            "mid_category": "자동화",
            "sub_category": "검증",
            "detail_category": "오류 피드백",
        }
        first_report = self.load_validatable_latest_report()
        second_report = self.load_validatable_latest_report()
        first_report["title"] = topic["topic"]
        second_report["title"] = topic["topic"]
        validation_error = "필수 섹션이 누락되었습니다: 06"

        with (
            patch.object(report_runner, "load_json", return_value={}),
            patch.object(report_runner, "select_topic", return_value=topic),
            patch.object(
                report_generator,
                "generate_report",
                side_effect=[first_report, second_report],
            ) as generate_mock,
            patch.object(
                report_runner,
                "validate_report_structure",
                side_effect=[ValueError(validation_error), None],
            ),
            patch.object(
                report_runner,
                "save_render_publish_report",
            ) as publish_mock,
            patch.object(
                report_runner,
                "record_generation_timeline",
                return_value={},
            ),
            patch.dict(
                os.environ,
                {
                    "REPORT_SKIP_EXISTING_DATE": "0",
                    "REPORT_VALIDATION_RETRIES": "2",
                    "REPORT_DATE": "",
                },
            ),
        ):
            report_runner.run_api()

        self.assertEqual("", generate_mock.call_args_list[0].kwargs["validation_feedback"])
        self.assertEqual(
            validation_error,
            generate_mock.call_args_list[1].kwargs["validation_feedback"],
        )
        publish_mock.assert_called_once()

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
