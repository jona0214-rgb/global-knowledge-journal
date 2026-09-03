import copy
import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, TypeVar

from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)


ROOT_DIR = Path(__file__).resolve().parents[1]

CONFIG_DIR = ROOT_DIR / "config"
PROMPTS_DIR = ROOT_DIR / "prompts"
SCHEMAS_DIR = ROOT_DIR / "schemas"
DATA_DIR = ROOT_DIR / "data"
OUTPUTS_DIR = ROOT_DIR / "outputs"

STYLE_GUIDE_PATH = CONFIG_DIR / "style_guide_v1_8.md"
QUOTATION_SOURCE_TYPES_PATH = CONFIG_DIR / "quotation_source_types.json"
SYSTEM_PROMPT_PATH = PROMPTS_DIR / "system_prompt.md"
REPORT_WRITER_PROMPT_PATH = PROMPTS_DIR / "report_writer_prompt.md"
REPORT_SCHEMA_PATH = SCHEMAS_DIR / "report.schema.json"
TOPIC_DB_PATH = DATA_DIR / "topic_db.json"

ResponseT = TypeVar("ResponseT")
TRANSIENT_OPENAI_ERRORS = (
    APIConnectionError,
    InternalServerError,
    RateLimitError,
)

REQUIRED_SECTION_IDS = (
    "01",
    "02",
    "03",
    "03-1",
    "03-2",
    "03-3",
    "03-4",
    "03-5",
    "04",
    "05",
    "06",
)
API_SOURCE_KEYS = tuple(f"source_{index}" for index in range(1, 7))


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


def build_api_response_schema(canonical_schema: Dict[str, Any]) -> Dict[str, Any]:
    """API 응답에서 교차 필드 제약을 구조적으로 강제하는 wire schema를 만든다.

    OpenAI Structured Outputs는 배열의 고유 ID나 다른 배열 원소의 URL 참조를
    직접 강제하지 못한다. API 응답에만 고정 키 객체를 사용하고, 저장 전 기존
    공개 JSON 형식으로 정규화해 렌더러와 카탈로그 호환성을 유지한다.
    """
    schema = copy.deepcopy(canonical_schema)
    properties = schema["properties"]

    section_schema = properties["sections"]
    variants = section_schema["items"]["anyOf"]
    variants_by_id = {}
    for variant in variants:
        section_ids = variant.get("properties", {}).get("id", {}).get("enum", [])
        if len(section_ids) != 1:
            raise ValueError("section schema의 각 anyOf 항목에는 단일 id enum이 필요합니다.")
        variants_by_id[section_ids[0]] = variant

    missing_section_schemas = [
        section_id
        for section_id in REQUIRED_SECTION_IDS
        if section_id not in variants_by_id
    ]
    if missing_section_schemas:
        raise ValueError(
            "API schema로 변환할 필수 section 정의가 없습니다: "
            + ", ".join(missing_section_schemas)
        )

    properties["sections"] = {
        "type": "object",
        "description": (
            "고정 섹션 객체. 각 키와 내부 id는 일치하며 모든 키가 정확히 한 번 필요하다."
        ),
        "additionalProperties": False,
        "required": list(REQUIRED_SECTION_IDS),
        "properties": {
            section_id: variants_by_id[section_id]
            for section_id in REQUIRED_SECTION_IDS
        },
    }

    source_item_schema = properties["sources"]["items"]
    properties["sources"] = {
        "type": "object",
        "description": "정확히 6개의 출처를 source_1부터 source_6까지 작성한다.",
        "additionalProperties": False,
        "required": list(API_SOURCE_KEYS),
        "properties": {
            source_key: copy.deepcopy(source_item_schema)
            for source_key in API_SOURCE_KEYS
        },
    }

    quotation_schema = properties["quotation"]
    quotation_properties = quotation_schema["properties"]
    quotation_properties.pop("source_title", None)
    quotation_properties.pop("source_url", None)
    quotation_properties["source_key"] = {
        "type": "string",
        "enum": list(API_SOURCE_KEYS),
        "description": (
            "인용·첨언의 근거가 되는 sources 키. 제목과 URL은 코드가 해당 출처에서 연결한다."
        ),
    }
    quotation_schema["required"] = [
        field
        for field in quotation_schema["required"]
        if field not in {"source_title", "source_url"}
    ] + ["source_key"]

    return schema


def normalize_api_report(report: Dict[str, Any]) -> Dict[str, Any]:
    """API wire format을 렌더링·저장용 canonical report 형식으로 변환한다."""
    sections = report.get("sections")
    if isinstance(sections, dict):
        missing_sections = [
            section_id
            for section_id in REQUIRED_SECTION_IDS
            if not isinstance(sections.get(section_id), dict)
        ]
        if missing_sections:
            raise ValueError(
                "API 응답의 고정 섹션이 누락되었습니다: "
                + ", ".join(missing_sections)
            )

        normalized_sections = []
        for section_id in REQUIRED_SECTION_IDS:
            section = sections[section_id]
            section["id"] = section_id
            normalized_sections.append(section)
        report["sections"] = normalized_sections

    sources = report.get("sources")
    source_map = sources if isinstance(sources, dict) else None
    if source_map is not None:
        missing_sources = [
            source_key
            for source_key in API_SOURCE_KEYS
            if not isinstance(source_map.get(source_key), dict)
        ]
        if missing_sources:
            raise ValueError(
                "API 응답의 고정 출처가 누락되었습니다: "
                + ", ".join(missing_sources)
            )
        report["sources"] = [source_map[source_key] for source_key in API_SOURCE_KEYS]

    quotation = report.get("quotation")
    if isinstance(quotation, dict) and "source_key" in quotation:
        if source_map is None:
            raise ValueError(
                "quotation.source_key를 해석하려면 sources가 고정 키 객체여야 합니다."
            )
        source_key = str(quotation.get("source_key", "")).strip()
        source = source_map.get(source_key)
        if not isinstance(source, dict):
            raise ValueError(
                "quotation.source_key가 유효한 sources 키가 아닙니다: "
                f"{source_key or '(빈 값)'}"
            )
        quotation["source_title"] = str(source.get("title", "")).strip()
        quotation["source_url"] = str(source.get("url", "")).strip()
        quotation.pop("source_key", None)

    return report


def build_user_prompt(
    today: str,
    selected_topic: Dict[str, Any],
    validation_feedback: str = "",
) -> str:
    style_guide = load_text(STYLE_GUIDE_PATH)
    quotation_source_types = load_text(QUOTATION_SOURCE_TYPES_PATH)
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
    prompt = prompt.replace(
        "{{ quotation_source_types }}",
        quotation_source_types,
    )
    prompt = prompt.replace("{{ topic_db }}", topic_db)

    correction_prompt = ""
    if validation_feedback:
        correction_prompt = f"""
# STRUCTURE CORRECTION

이전 초안은 아래 자동 검증 오류로 폐기되었습니다.

검증 오류:
{validation_feedback}

이전 초안을 부분 수정하거나 이어 쓰지 말고 전체 JSON을 처음부터 다시 작성하세요.
특히 sections는 다음 11개 키를 모두 갖는 고정 객체이며, 각 값의 내부 id도 키와 같아야 합니다.

01, 02, 03, 03-1, 03-2, 03-3, 03-4, 03-5, 04, 05, 06

중복 id, 누락 키, 추가 section 키는 모두 금지합니다.
quotation.source_key는 source_1부터 source_6 중 실제 인용 근거가 되는 키를 선택하세요.
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


def call_openai_with_transient_retries(
    operation: Callable[[], ResponseT],
    operation_name: str,
) -> ResponseT:
    """연결 끊김·429·5xx만 짧은 지수 백오프로 다시 시도한다."""
    retry_count = int(os.getenv("OPENAI_CONNECTION_RETRIES", "2"))
    base_delay_seconds = float(os.getenv("OPENAI_RETRY_BASE_SECONDS", "10"))
    if retry_count < 0:
        raise ValueError("OPENAI_CONNECTION_RETRIES는 0 이상의 정수여야 합니다.")
    if base_delay_seconds < 0:
        raise ValueError("OPENAI_RETRY_BASE_SECONDS는 0 이상이어야 합니다.")

    for attempt_index in range(retry_count + 1):
        try:
            return operation()
        except APITimeoutError:
            # 요청당 제한이 600초이므로 시간 초과를 반복하면 job 제한을 넘는다.
            # 타임아웃은 호출부의 명확한 오류 안내로 즉시 넘긴다.
            raise
        except TRANSIENT_OPENAI_ERRORS as exc:
            if attempt_index >= retry_count:
                raise RuntimeError(
                    f"{operation_name}의 일시적 오류가 재시도 후에도 계속되었습니다: "
                    f"{type(exc).__name__}"
                ) from exc

            delay_seconds = min(
                base_delay_seconds * (2 ** attempt_index),
                60,
            )
            print(
                f"{operation_name} 일시적 오류({type(exc).__name__}): "
                f"{delay_seconds:g}초 후 연결 재시도 "
                f"{attempt_index + 1}/{retry_count}"
            )
            time.sleep(delay_seconds)

    raise RuntimeError(f"{operation_name} 재시도 흐름이 비정상 종료되었습니다.")


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
    schema = build_api_response_schema(schema_doc["schema"])

    timeout_seconds = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "600"))
    max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "0"))
    print(
        "OpenAI API 요청 시작: "
        f"요청당 제한 {timeout_seconds:g}초, 최대 재시도 {max_retries}회"
    )

    try:
        response = call_openai_with_transient_retries(
            lambda: client.responses.create(
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
            ),
            "OpenAI 리포트 생성",
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

    return normalize_api_report(report)


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
        response = call_openai_with_transient_retries(
            lambda: client.responses.create(
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
            ),
            "OpenAI 주제 후보 생성",
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


