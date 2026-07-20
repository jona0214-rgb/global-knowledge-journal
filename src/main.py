from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.topic_selector import select_topic
from src.report_generator import generate_report


PROMPT_PATH = Path("prompts/daily_report.md")
REPORT_ROOT = Path("reports")


def build_prompt(topic: dict, date: str) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")

    return (
        template
        .replace("{{DATE}}", date)
        .replace("{{CATEGORY}}", topic["category"])
        .replace("{{SUBCATEGORY}}", topic["subcategory"])
        .replace("{{TOPIC}}", topic["title"])
        .replace("{{DIFFICULTY}}", topic["difficulty"])
    )


def save_markdown(report: str, date: str) -> Path:
    year = date[:4]
    month = date[5:7]

    output_dir = REPORT_ROOT / year / month / date
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / "report.md"
    output_path.write_text(report, encoding="utf-8")

    return output_path


def main() -> None:
    today = datetime.now(
        ZoneInfo("Asia/Seoul")
    ).strftime("%Y-%m-%d")

    topic = select_topic()
    prompt = build_prompt(topic, today)
    report = generate_report(prompt)
    saved_path = save_markdown(report, today)

    print(f"리포트 생성 완료: {saved_path}")


if __name__ == "__main__":
    main()