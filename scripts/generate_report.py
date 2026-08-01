import json
import os
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
from openai import OpenAI


ROOT_DIR = Path(__file__).resolve().parents[1]

CONFIG_DIR = ROOT_DIR / "config"
PROMPTS_DIR = ROOT_DIR / "prompts"
SCHEMAS_DIR = ROOT_DIR / "schemas"
DATA_DIR = ROOT_DIR / "data"
OUTPUTS_DIR = ROOT_DIR / "outputs"

STYLE_GUIDE_PATH = CONFIG_DIR / "style_guide_v1_8.md"
SYSTEM_PROMPT_PATH = PROMPTS_DIR / "system_prompt.md"
REPORT_WRITER_PROMPT_PATH = PROMPTS_DIR / "report_writer_prompt.md"
REPORT_SCHEMA_PATH = SCHEMAS_DIR / "report.schema.json"
TOPIC_DB_PATH = DATA_DIR / "topic_db.json"


def load_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")

    return path.read_text(encoding="utf-8")


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def build_user_prompt(today: str, selected_topic: Dict[str, Any]) -> str:
    style_guide = load_text(STYLE_GUIDE_PATH)
    topic_db = load_text(TOPIC_DB_PATH)
    prompt_template = load_text(REPORT_WRITER_PROMPT_PATH)

    selected_topic_json = json.dumps(
        selected_topic,
        ensure_ascii=False,
        indent=2,
    )

    locked_title = str(
        selected_topic.get("topic")
        or selected_topic.get("title")
        or ""
    ).strip()

    locked_main_category = str(
        selected_topic.get("main_category")
        or selected_topic.get("main")
        or ""
    ).strip()

    locked_middle_category = str(
        selected_topic.get("mid_category")
        or selected_topic.get("middle_category")
        or selected_topic.get("middle")
        or ""
    ).strip()

    locked_sub_category = str(
        selected_topic.get("sub_category")
        or selected_topic.get("sub")
        or ""
    ).strip()

    topic_lock = f"""
# TOPIC LOCK

오늘 리포트는 아래 선정 주제만 사용해야 합니다.

선정 주제 JSON:
{selected_topic_json}

반드시 지켜야 할 고정값:
- report.date: {today}
- report.title: {locked_title}
- report.category.main: {locked_main_category}
- report.category.middle: {locked_middle_category}
- report.category.sub: {locked_sub_category}

절대 금지:
- 새로운 주제를 고르지 마세요.
- 선정 주제를 다른 주제로 바꾸지 마세요.
- 제목을 임의로 요약하거나 재작성하지 마세요.
- report.title은 반드시 선정 주제의 topic 문자열과 완전히 같아야 합니다.
- 인공지능 윤리, 도시 농업, 자동화 파이프라인 같은 임의 주제로 바꾸지 마세요.
- topic_db, candidate_pool, GitHub Actions, mock 실행, API 실행, 프로젝트 운영 메모를 리포트 본문에 포함하지 마세요.

작성 지침:
- 선정 주제의 범위 안에서만 설명하세요.
- subtitle은 독자가 이해하기 쉬운 보조 설명으로 작성해도 됩니다.
- 본문은 Global Knowledge Journal 리포트 형식을 따르세요.
""".strip()

    prompt = prompt_template.replace("{{ today }}", today)
    prompt = prompt.replace("{{ selected_topic }}", selected_topic_json)
    prompt = prompt.replace("{{ style_guide }}", style_guide)
    prompt = prompt.replace("{{ topic_db }}", topic_db)

    return topic_lock + "\n\n" + prompt


def validate_env() -> None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()

    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY가 설정되지 않았습니다. "
            "프로젝트 최상단의 .env 파일에 API 키를 입력하세요."
        )


def get_openai_client() -> OpenAI:
    validate_env()
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def generate_report_with_api(today: str, selected_topic: Dict[str, Any]) -> Dict[str, Any]:
    load_dotenv(ROOT_DIR / ".env")

    client = get_openai_client()

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
    system_prompt = load_text(SYSTEM_PROMPT_PATH)
    user_prompt = build_user_prompt(today=today, selected_topic=selected_topic)

    schema_doc = load_json(REPORT_SCHEMA_PATH)
    schema_name = schema_doc.get("name", "daily_report")
    schema = schema_doc["schema"]

    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "schema": schema,
                "strict": True,
            }
        },
    )

    raw_text = response.output_text

    try:
        report = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        debug_path = OUTPUTS_DIR / "api_raw_response_debug.txt"
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.write_text(raw_text, encoding="utf-8")

        raise RuntimeError(
            "OpenAI API 응답을 JSON으로 해석하지 못했습니다. "
            f"원본 응답을 저장했습니다: {debug_path}"
        ) from exc

    return report


def generate_report(today: str, selected_topic: Dict[str, Any]) -> Dict[str, Any]:
    return generate_report_with_api(today=today, selected_topic=selected_topic)


def main() -> None:
    load_dotenv(ROOT_DIR / ".env")

    today = "2026-07-20"

    selected_topic = {
        "topic": "테스트 리포트: 자동화 파이프라인은 어떻게 지식 생산을 바꾸는가",
        "main_category": "과학·공학",
        "mid_category": "자동화 시스템",
        "priority": 0.5,
        "status": "test",
    }

    report = generate_report(today=today, selected_topic=selected_topic)

    output_path = OUTPUTS_DIR / "api_test_report.json"
    save_json(output_path, report)

    print("API 리포트 생성 성공")
    print(f"저장 위치: {output_path}")
    print(f"제목: {report.get('title')}")
    print(f"카테고리: {report.get('category', {}).get('main')} / {report.get('category', {}).get('middle')}")


if __name__ == "__main__":
    main()