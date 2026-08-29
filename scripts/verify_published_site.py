import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


ROOT_DIR = Path(__file__).resolve().parents[1]
REPORTS_JSON_PATH = ROOT_DIR / "public" / "reports.json"


def utc_now_iso() -> str:
    return datetime.now(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")


def kst_now_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).isoformat()


def load_expected_report(report_date: str) -> dict:
    reports = json.loads(REPORTS_JSON_PATH.read_text(encoding="utf-8"))
    report = next(
        (
            item for item in reports
            if isinstance(item, dict)
            and item.get("date") == report_date
            and item.get("status") == "published_api"
        ),
        None,
    )
    if not report:
        raise RuntimeError(f"로컬 공개 목록에 {report_date} API 리포트가 없습니다.")
    return report


def fetch_json(url: str) -> object:
    request = Request(
        url,
        headers={
            "Cache-Control": "no-cache",
            "User-Agent": "gkj-publish-verifier",
        },
    )
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def asset_is_visible(url: str) -> bool:
    request = Request(
        url,
        method="HEAD",
        headers={
            "Cache-Control": "no-cache",
            "User-Agent": "gkj-publish-verifier",
        },
    )
    with urlopen(request, timeout=20) as response:
        return response.status == 200


def verify_once(base_url: str, report_date: str, expected_report: dict) -> bool:
    cache_buster = int(time.time())
    reports_url = urljoin(base_url, "public/reports.json") + f"?v={cache_buster}"
    remote_reports = fetch_json(reports_url)
    if not isinstance(remote_reports, list):
        return False

    remote_report = next(
        (
            item for item in remote_reports
            if isinstance(item, dict)
            and item.get("date") == report_date
            and item.get("status") == "published_api"
        ),
        None,
    )
    if not remote_report:
        return False

    pdf_path = remote_report.get("pdf_url") or expected_report.get("pdf_url")
    if not pdf_path:
        return False
    pdf_url = urljoin(base_url, str(pdf_path)) + f"?v={cache_buster}"
    return asset_is_visible(pdf_url)


def append_step_summary(report_date: str, visible: bool, message: str) -> None:
    summary_path = os.getenv("GITHUB_STEP_SUMMARY", "").strip()
    if not summary_path:
        return
    with Path(summary_path).open("a", encoding="utf-8") as summary:
        summary.write("\n## GitHub Pages publication check\n\n")
        summary.write(f"- Report date: `{report_date}`\n")
        summary.write(f"- Result: `{'visible' if visible else 'timeout'}`\n")
        summary.write(f"- {message}\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--interval-seconds", type=int, default=15)
    args = parser.parse_args()

    expected_report = load_expected_report(args.date)
    deadline = time.monotonic() + max(1, args.timeout_seconds)
    attempt = 0
    last_error = ""

    while time.monotonic() < deadline:
        attempt += 1
        try:
            if verify_once(args.base_url, args.date, expected_report):
                visible_utc = utc_now_iso()
                visible_kst = kst_now_iso()
                message = (
                    f"Pages visible after {attempt} checks: "
                    f"UTC {visible_utc}, KST {visible_kst}"
                )
                print(message)
                append_step_summary(args.date, True, message)
                return
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"

        print(
            f"Pages 공개 대기 {attempt}회: {args.date}, "
            f"마지막 오류={last_error or '아직 목록·PDF 미반영'}"
        )
        time.sleep(max(1, args.interval_seconds))

    message = (
        f"{args.timeout_seconds}초 안에 Pages 공개를 확인하지 못했습니다. "
        f"마지막 오류={last_error or '목록·PDF 미반영'}"
    )
    print(message)
    append_step_summary(args.date, False, message)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
