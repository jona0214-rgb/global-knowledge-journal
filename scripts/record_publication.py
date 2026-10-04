import argparse
import os
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from report_pipeline.json_store import load_json as load_json_file
from report_pipeline.json_store import save_json_atomic


ROOT_DIR = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT_DIR / "public"
LATEST_PATH = PUBLIC_DIR / "latest.json"
HISTORY_PATH = PUBLIC_DIR / "generation-history.json"
STATUS_PATH = PUBLIC_DIR / "generation-status.json"
KST = ZoneInfo("Asia/Seoul")


def load_json(path: Path, default):
    return load_json_file(path, default)


def save_json(path: Path, value) -> None:
    save_json_atomic(path, value)


def publication_metadata(published_at: datetime) -> dict:
    published_at = published_at.astimezone(timezone.utc)
    publication_date = published_at.astimezone(KST).date()
    target = datetime.combine(publication_date, time(7, 0), tzinfo=KST)
    server_url = os.getenv("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
    repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    run_id = os.getenv("GITHUB_RUN_ID", "").strip()
    run_url = (
        f"{server_url}/{repository}/actions/runs/{run_id}"
        if repository and run_id
        else ""
    )
    return {
        "publication_target_kst": target.isoformat(),
        "publication_pushed_at": published_at.isoformat().replace("+00:00", "Z"),
        "publication_schedule_cron": os.getenv(
            "REPORT_PUBLICATION_CRON", ""
        ).strip(),
        "publication_run_id": run_id,
        "publication_run_url": run_url,
    }


def record_publication(published_at: datetime) -> str:
    latest = load_json(LATEST_PATH, {})
    report_date = str(latest.get("date", "")).strip()
    if not report_date:
        raise ValueError("public/latest.json에서 공개할 리포트 날짜를 찾지 못했습니다.")

    metadata = publication_metadata(published_at)
    history = load_json(HISTORY_PATH, [])
    if not isinstance(history, list):
        history = []

    matching_entry = None
    for entry in history:
        if isinstance(entry, dict) and str(entry.get("date", "")) == report_date:
            entry.update(metadata)
            matching_entry = entry
            break

    if matching_entry is None:
        matching_entry = {
            "date": report_date,
            "title": latest.get("title", ""),
            "status": latest.get("status", "published_api"),
            **metadata,
        }
        history.insert(0, matching_entry)

    save_json(HISTORY_PATH, history[:30])
    save_json(STATUS_PATH, matching_entry)
    return report_date


def append_github_env(report_date: str) -> None:
    github_env = os.getenv("GITHUB_ENV", "").strip()
    if github_env:
        with Path(github_env).open("a", encoding="utf-8") as env_file:
            env_file.write(f"\nREPORT_EFFECTIVE_DATE={report_date}\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--published-at",
        help="UTC ISO timestamp; defaults to the current time",
    )
    args = parser.parse_args()
    published_at = (
        datetime.fromisoformat(args.published_at.replace("Z", "+00:00"))
        if args.published_at
        else datetime.now(timezone.utc)
    )
    report_date = record_publication(published_at)
    append_github_env(report_date)
    print(f"공개 타임라인 기록 완료: {report_date}")


if __name__ == "__main__":
    main()
