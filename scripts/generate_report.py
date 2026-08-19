import json
import os
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
from openai import APITimeoutError, OpenAI


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


def build_user_prompt(
    today: str,
    selected_topic: Dict[str, Any],
    validation_feedback: str = "",
) -> str:
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

    sub_category_rule = (
        locked_sub_category
        if locked_sub_category
        else "선정 주제에서 추론한 구체적인 소분류"
    )

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
- report.category.sub: {sub_category_rule}
- report.category.detail: 소분류보다 한 단계 더 구체적인 최소 분류

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

    correction_prompt = ""
    if validation_feedback:
        correction_prompt = f"""
# STRUCTURE CORRECTION

이전 초안은 아래 자동 검증 오류로 폐기되었습니다.

검증 오류:
{validation_feedback}

이전 초안을 부분 수정하거나 이어 쓰지 말고 전체 JSON을 처음부터 다시 작성하세요.
특히 sections는 정확히 11개 객체이며 다음 id를 아래 순서대로 각각 정확히 한 번만 사용해야 합니다.

01, 02, 03, 03-1, 03-2, 03-3, 03-4, 03-5, 04, 05, 06

중복 id, 누락 id, 추가 section 객체는 모두 금지합니다.
""".strip()

    prompt_parts = [topic_lock]
    if correction_prompt:
        prompt_parts.append(correction_prompt)
    prompt_parts.append(prompt)
    return "\n\n".join(prompt_parts)


def validate_env() -> None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()

    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY가 설정되지 않았습니다. "
            "프로젝트 최상단의 .env 파일에 API 키를 입력하세요."
        )


def get_openai_client() -> OpenAI:
    validate_env()
    timeout_seconds = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "600"))
    max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "0"))

    return OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        timeout=timeout_seconds,
        max_retries=max_retries,
    )


def generate_report_with_api(
    today: str,
    selected_topic: Dict[str, Any],
    validation_feedback: str = "",
) -> Dict[str, Any]:
    load_dotenv(ROOT_DIR / ".env")

    client = get_openai_client()

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
    system_prompt = load_text(SYSTEM_PROMPT_PATH)
    user_prompt = build_user_prompt(
        today=today,
        selected_topic=selected_topic,
        validation_feedback=validation_feedback,
    )

    schema_doc = load_json(REPORT_SCHEMA_PATH)
    schema_name = schema_doc.get("name", "daily_report")
    schema = schema_doc["schema"]

    timeout_seconds = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "600"))
    max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "0"))
    print(
        "OpenAI API 요청 시작: "
        f"요청당 제한 {timeout_seconds:g}초, 최대 재시도 {max_retries}회"
    )

    try:
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
    except APITimeoutError as exc:
        raise RuntimeError(
            "OpenAI API 응답 제한시간을 초과했습니다. "
            f"요청당 {timeout_seconds:g}초, 최대 재시도 {max_retries}회"
        ) from exc

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


def generate_report(
    today: str,
    selected_topic: Dict[str, Any],
    validation_feedback: str = "",
) -> Dict[str, Any]:
    return generate_report_with_api(
        today=today,
        selected_topic=selected_topic,
        validation_feedback=validation_feedback,
    )


def generate_topic_candidates_with_api(
    target_category: str,
    category_description: str,
    existing_titles: list[str],
    count: int = 5,
) -> list[Dict[str, Any]]:
    """현재 순번의 대분류가 고갈됐을 때 계층형 후보를 보충한다."""
    load_dotenv(ROOT_DIR / ".env")
    if count < 1:
        raise ValueError("생성할 주제 후보 수는 1개 이상이어야 합니다.")

    client = get_openai_client()
    model = os.getenv(
        "OPENAI_TOPIC_MODEL",
        os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
    ).strip()
    timeout_seconds = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "600"))

    existing_text = "\n".join(
        f"- {title}" for title in existing_titles if str(title).strip()
    )
    prompt = f"""
Global Knowledge Journal의 다음 일일 리포트 주제 후보를 작성하세요.

고정 대분류: {target_category}
대분류 범위: {category_description}
생성 개수: {count}개

기존 발행·대기 주제:
{existing_text}

규칙:
- 고정 대분류를 바꾸지 마세요.
- 기존 주제와 제목뿐 아니라 핵심 개념과 사례도 겹치지 않아야 합니다.
- 후보마다 서로 다른 중분류와 소분류를 우선 사용하세요.
- middle은 학문·산업의 중분류, sub는 그 아래의 구체적 소분류로 작성하세요.
- detail은 소분류보다 한 단계 더 좁은 탐구 초점이어야 합니다.
- 하루짜리 뉴스가 아니라 시간이 지나도 읽을 수 있는 지식 주제를 고르세요.
- 신뢰할 수 있는 공개 자료를 5개 이상 확보할 수 있는 주제만 고르세요.
- 제목은 한국어로 쓰고 독자의 질문을 자극하되 과장하지 마세요.
- 내부 운영, 자동화, API, GitHub, 주제 선정 시스템은 주제로 삼지 마세요.
""".strip()

    candidate_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["candidates"],
        "properties": {
            "candidates": {
                "type": "array",
                "minItems": count,
                "maxItems": count,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "topic", "mid_category", "sub_category",
                        "detail_category", "priority",
                    ],
                    "properties": {
                        "topic": {"type": "string", "minLength": 10},
                        "mid_category": {"type": "string", "minLength": 2},
                        "sub_category": {"type": "string", "minLength": 2},
                        "detail_category": {"type": "string", "minLength": 2},
                        "priority": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                        },
                    },
                },
            }
        },
    }

    print(
        f"주제 후보 보충 API 요청: '{target_category}' {count}개, "
        f"제한 {timeout_seconds:g}초"
    )
    try:
        response = client.responses.create(
            model=model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "당신은 지식 리포트의 주제 편집자입니다. "
                        "응답 스키마에 맞는 후보만 작성합니다."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "topic_candidates",
                    "schema": candidate_schema,
                    "strict": True,
                }
            },
        )
    except APITimeoutError as exc:
        raise RuntimeError(
            f"'{target_category}' 주제 후보 생성 제한시간을 초과했습니다."
        ) from exc

    try:
        payload = json.loads(response.output_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("주제 후보 API 응답이 올바른 JSON이 아닙니다.") from exc

    candidates = payload.get("candidates", [])
    if not isinstance(candidates, list) or len(candidates) != count:
        raise RuntimeError(
            f"주제 후보가 {count}개 생성되지 않았습니다: {len(candidates)}개"
        )
    return candidates


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


