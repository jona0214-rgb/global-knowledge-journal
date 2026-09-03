import argparse
from html import escape
import json
import os
import re
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
OUTPUTS_DIR = ROOT_DIR / "outputs"
PUBLIC_DIR = ROOT_DIR / "public"
TEMPLATES_DIR = ROOT_DIR / "templates"
CONFIG_DIR = ROOT_DIR / "config"

TOPIC_DB_PATH = DATA_DIR / "topic_db.json"
TOPIC_DB_SQLITE_PATH = DATA_DIR / "topic_db.sqlite"
TOPIC_TAXONOMY_PATH = CONFIG_DIR / "topic_taxonomy_v2.json"
QUOTATION_SOURCE_TYPES_PATH = CONFIG_DIR / "quotation_source_types.json"
MANIFEST_PATH = DATA_DIR / "manifest.json"
REPORTS_JSON_PATH = PUBLIC_DIR / "reports.json"
LATEST_JSON_PATH = PUBLIC_DIR / "latest.json"
GENERATION_HISTORY_PATH = PUBLIC_DIR / "generation-history.json"
GENERATION_STATUS_PATH = PUBLIC_DIR / "generation-status.json"


class TopicPoolExhaustedError(RuntimeError):
    """현재 순번의 대분류에 발행 가능한 후보가 없을 때 발생한다."""

    def __init__(self, target_category: str, message: str):
        super().__init__(message)
        self.target_category = target_category


def get_today_kst() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")


def utc_now_iso() -> str:
    return datetime.now(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")


def parse_iso_datetime(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def seconds_between(start: str, end: str) -> int | None:
    start_time = parse_iso_datetime(start)
    end_time = parse_iso_datetime(end)
    if not start_time or not end_time:
        return None
    return max(0, round((end_time - start_time).total_seconds()))


def scheduled_for_kst(report_date: str, cron_expression: str) -> str | None:
    schedule_times = {
        "0 20 * * *": "05:00:00",
        "15 23 * * *": "08:15:00",
    }
    schedule_time = schedule_times.get(str(cron_expression).strip())
    if not schedule_time:
        return None
    return f"{report_date}T{schedule_time}+09:00"


def resolve_report_date(explicit_date: str | None = None) -> str:
    """수동 백필 날짜를 검증하고, 없으면 한국 날짜를 사용한다."""
    requested_date = str(
        explicit_date if explicit_date is not None else os.getenv("REPORT_DATE", "")
    ).strip()
    today = get_today_kst()
    if not requested_date:
        return today

    try:
        parsed_date = datetime.strptime(requested_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("리포트 날짜는 YYYY-MM-DD 형식이어야 합니다.") from exc

    if parsed_date.isoformat() != requested_date:
        raise ValueError("리포트 날짜는 YYYY-MM-DD 형식이어야 합니다.")
    if requested_date > today:
        raise ValueError(
            f"미래 날짜의 리포트는 생성할 수 없습니다: {requested_date}"
        )
    return requested_date


def compact_date(date_text: str) -> str:
    return date_text.replace("-", "")


def slugify_korean(text: str) -> str:
    cleaned = re.sub(r"[^\w가-힣]+", "", text)
    return cleaned[:24] or "report"


def load_json(path: Path, default):
    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_topic_title(title: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", str(title).lower())


def topic_tokens(title: str) -> set[str]:
    stopwords = {
        "어떻게", "무엇인가", "무엇을", "그리고", "대한", "위한",
        "되었나", "되는가", "바꾸었나", "있는가", "왜", "은", "는",
        "이", "가", "을", "를", "의",
    }
    return {
        token
        for token in re.findall(r"[0-9a-z가-힣]{2,}", str(title).lower())
        if token not in stopwords
    }


def topic_similarity(left: str, right: str) -> float:
    left_key = normalize_topic_title(left)
    right_key = normalize_topic_title(right)
    if not left_key or not right_key:
        return 0.0
    if left_key == right_key:
        return 1.0

    left_tokens = topic_tokens(left)
    right_tokens = topic_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0

    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def get_published_topic_history(topic_db: dict) -> list[dict]:
    """mock을 제외한 실제 발행 이력을 제목 기준으로 합친다."""
    history = []
    history.extend(topic_db.get("recent_reports", []))

    catalog = load_json(REPORTS_JSON_PATH, default=[])
    if isinstance(catalog, list):
        history.extend(catalog)

    published_statuses = {"published", "published_api"}
    unique_by_title = {}
    for item in history:
        if not isinstance(item, dict) or item.get("status") not in published_statuses:
            continue
        title_key = normalize_topic_title(item.get("title", ""))
        if title_key:
            unique_by_title[title_key] = item

    return sorted(
        unique_by_title.values(),
        key=lambda item: str(item.get("date", "")),
    )


def load_topic_taxonomy() -> dict:
    taxonomy = load_json(TOPIC_TAXONOMY_PATH, default={})
    version = str(taxonomy.get("taxonomy_version", "")).strip()
    category_order = taxonomy.get("category_order", [])
    categories = taxonomy.get("categories", [])

    if version != "2.0":
        raise ValueError("주제 taxonomy_version은 2.0이어야 합니다.")
    if not isinstance(category_order, list) or len(category_order) != 10:
        raise ValueError("주제 taxonomy에는 대분류가 정확히 10개 있어야 합니다.")
    if len(set(category_order)) != len(category_order):
        raise ValueError("주제 taxonomy의 대분류 순서에 중복이 있습니다.")
    if not isinstance(categories, list):
        raise ValueError("주제 taxonomy categories가 list가 아닙니다.")

    category_names = {
        str(category.get("name", "")).strip()
        for category in categories
        if isinstance(category, dict)
    }
    if category_names != set(category_order):
        raise ValueError(
            "주제 taxonomy의 category_order와 categories 정의가 일치하지 않습니다."
        )

    for category in categories:
        seed_topics = category.get("seed_topics", [])
        if not isinstance(seed_topics, list):
            raise ValueError(
                f"{category.get('name', '')}의 seed_topics가 list가 아닙니다."
            )
        for seed in seed_topics:
            required = ("topic", "mid_category", "sub_category", "detail_category")
            missing = [
                field for field in required
                if not str(seed.get(field, "")).strip()
            ]
            if missing:
                raise ValueError(
                    f"{category.get('name', '')} seed topic 필드 누락: "
                    + ", ".join(missing)
                )

    return taxonomy


def get_taxonomy_seed_index(taxonomy: dict) -> dict[str, dict]:
    seed_index = {}
    for category in taxonomy["categories"]:
        main_category = category["name"]
        for seed in category.get("seed_topics", []):
            item = dict(seed)
            item["main_category"] = main_category
            seed_index[normalize_topic_title(item["topic"])] = item
    return seed_index


def merge_taxonomy_candidates(topic_db: dict, taxonomy: dict) -> None:
    """기존 상태를 보존하면서 v2 분류와 큐레이션 후보를 합친다."""
    seed_index = get_taxonomy_seed_index(taxonomy)
    candidate_pool = topic_db.setdefault("candidate_pool", [])
    existing_by_title = {
        normalize_topic_title(item.get("topic", "")): item
        for item in candidate_pool
        if isinstance(item, dict) and item.get("topic")
    }

    for title_key, seed in seed_index.items():
        existing = existing_by_title.get(title_key)
        if existing is None:
            candidate_pool.append({
                **seed,
                "status": "candidate",
                "source": "taxonomy_seed",
            })
            continue

        preserved_status = existing.get("status", "candidate")
        preserved_source = existing.get("source", "legacy_migration")
        existing.update(seed)
        existing["status"] = preserved_status
        existing["source"] = preserved_source

    topic_db["schema_version"] = "2.0"
    topic_db["taxonomy_version"] = taxonomy["taxonomy_version"]


def canonical_main_category(item: dict, taxonomy: dict) -> str:
    main_category = str(item.get("main_category", "")).strip()
    if main_category in taxonomy["category_order"]:
        return main_category

    title_key = normalize_topic_title(item.get("title") or item.get("topic") or "")
    seed = get_taxonomy_seed_index(taxonomy).get(title_key)
    if seed:
        return str(seed.get("main_category", "")).strip()

    legacy_middle_map = {
        "식생활·가전문화": "역사·문화",
        "도시인프라": "기술·공학",
        "행정인프라": "사회·정치·법",
        "에너지정책": "경제·경영",
        "위험과 제도": "경제·경영",
        "재료와 문명": "기술·공학",
        "물환경공학": "기술·공학",
        "동물행동": "생명·건강",
        "생물과 구조": "과학·수학",
        "생태환경": "자연·환경·지리",
    }
    middle_category = str(item.get("mid_category", "")).strip()
    if middle_category in legacy_middle_map:
        return legacy_middle_map[middle_category]

    legacy_main_map = {
        "인문·철학": "인문·철학",
        "역사·문화": "역사·문화",
        "과학·공학": "기술·공학",
        "경제·사회": "경제·경영",
        "자연사·생태": "자연·환경·지리",
        "예술·미학": "예술·디자인",
        "생활기술·일상문화": "기술·공학",
        "언어·문자": "언어·미디어·지식",
    }
    return legacy_main_map.get(main_category, "")


def get_rotation_target(
    topic_db: dict,
    taxonomy: dict,
    published_history: list[dict],
) -> str:
    category_order = taxonomy["category_order"]
    rotation = topic_db.get("category_rotation", {})
    configured_next = str(rotation.get("next_main_category", "")).strip()

    if configured_next in category_order:
        return configured_next

    for item in reversed(published_history):
        previous_category = canonical_main_category(item, taxonomy)
        if previous_category in category_order:
            previous_index = category_order.index(previous_category)
            return category_order[(previous_index + 1) % len(category_order)]

    return category_order[0]


def select_topic(topic_db):
    taxonomy = load_topic_taxonomy()
    merge_taxonomy_candidates(topic_db, taxonomy)

    candidate_pool = topic_db["candidate_pool"]
    published_history = get_published_topic_history(topic_db)
    published_titles = [item.get("title", "") for item in published_history]
    published_title_keys = {
        normalize_topic_title(title) for title in published_titles if title
    }
    target_category = get_rotation_target(
        topic_db=topic_db,
        taxonomy=taxonomy,
        published_history=published_history,
    )

    category_candidates = [
        topic for topic in candidate_pool
        if isinstance(topic, dict)
        and topic.get("status") == "candidate"
        and topic.get("main_category") == target_category
    ]

    available_topics = []
    rejected_similar_topics = []
    rejected_invalid_topics = []
    for topic in category_candidates:
        required_fields = (
            "topic", "main_category", "mid_category",
            "sub_category", "detail_category",
        )
        missing_fields = [
            field for field in required_fields
            if not str(topic.get(field, "")).strip()
        ]
        if missing_fields:
            rejected_invalid_topics.append(
                (topic.get("topic", "(제목 없음)"), missing_fields)
            )
            continue

        candidate_title = topic["topic"]
        if normalize_topic_title(candidate_title) in published_title_keys:
            rejected_similar_topics.append((candidate_title, "exact"))
            continue

        highest_similarity = max(
            (topic_similarity(candidate_title, title) for title in published_titles),
            default=0.0,
        )
        if highest_similarity >= 0.72:
            rejected_similar_topics.append(
                (candidate_title, f"{highest_similarity:.2f}")
            )
            continue

        available_topics.append(topic)

    print(
        "주제 선정 점검: "
        f"taxonomy v{taxonomy['taxonomy_version']}, "
        f"이번 대분류 '{target_category}', "
        f"전체 후보 {len(candidate_pool)}개, "
        f"분류 내 대기 {len(category_candidates)}개, "
        f"중복·고유사도 제외 {len(rejected_similar_topics)}개, "
        f"필드 오류 제외 {len(rejected_invalid_topics)}개, "
        f"선택 가능 {len(available_topics)}개"
    )

    minimum_ready = int(taxonomy.get("minimum_ready_candidates", 1))
    if 0 < len(available_topics) < minimum_ready:
        print(
            f"주제 후보 재고 경고: '{target_category}'에 "
            f"{len(available_topics)}개만 남았습니다. 권장 최소 {minimum_ready}개"
        )

    if not available_topics:
        detail = ", ".join(
            title for title, _ in rejected_similar_topics[:3]
        )
        raise TopicPoolExhaustedError(
            target_category,
            f"순환 순번 '{target_category}'에 발행 가능한 주제가 없습니다. "
            "해당 대분류의 신규 중분류·소분류·주제 후보를 보충해야 합니다."
            + (f" 제외 예시: {detail}" if detail else ""),
        )

    recent_reports = published_history[-30:]
    used_middle_counts = {}
    used_sub_counts = {}
    for item in recent_reports:
        middle = str(item.get("mid_category", "")).strip()
        sub = str(item.get("sub_category", "")).strip()
        if middle:
            used_middle_counts[middle] = used_middle_counts.get(middle, 0) + 1
        if sub:
            used_sub_counts[sub] = used_sub_counts.get(sub, 0) + 1

    def calculate_score(topic):
        score = float(topic.get("priority", 0))
        middle = topic["mid_category"]
        sub = topic["sub_category"]

        # 같은 대분류 안에서는 아직 쓰지 않은 중분류와 소분류를 먼저 선택한다.
        if middle not in used_middle_counts:
            score += 0.40
        else:
            score -= min(used_middle_counts[middle] * 0.20, 0.60)

        if sub not in used_sub_counts:
            score += 0.20
        else:
            score -= min(used_sub_counts[sub] * 0.12, 0.36)

        highest_similarity = max(
            (
                topic_similarity(topic["topic"], published_title)
                for published_title in published_titles
            ),
            default=0.0,
        )
        if highest_similarity >= 0.45:
            score -= 0.35
        elif highest_similarity >= 0.25:
            score -= 0.15

        return score

    return max(
        available_topics,
        key=lambda topic: (
            calculate_score(topic),
            float(topic.get("priority", 0)),
            topic.get("topic", ""),
        ),
    )


def add_generated_topic_candidates(
    topic_db: dict,
    target_category: str,
    generated_candidates: list[dict],
) -> int:
    """API가 제안한 후보를 검증해 메모리의 후보 풀에 추가한다."""
    taxonomy = load_topic_taxonomy()
    if target_category not in taxonomy["category_order"]:
        raise ValueError(f"알 수 없는 대분류입니다: {target_category}")
    if not isinstance(generated_candidates, list):
        raise ValueError("생성된 주제 후보가 list가 아닙니다.")

    candidate_pool = topic_db.setdefault("candidate_pool", [])
    existing_titles = [
        item.get("topic", "")
        for item in candidate_pool
        if isinstance(item, dict)
    ]
    existing_titles.extend(
        item.get("title", "")
        for item in get_published_topic_history(topic_db)
    )

    added = 0
    for candidate in generated_candidates:
        if not isinstance(candidate, dict):
            continue

        required_fields = (
            "topic", "mid_category", "sub_category", "detail_category",
        )
        if any(not str(candidate.get(field, "")).strip() for field in required_fields):
            continue

        title = str(candidate["topic"]).strip()
        if any(topic_similarity(title, existing) >= 0.72 for existing in existing_titles):
            continue

        candidate_pool.append({
            "topic": title,
            "main_category": target_category,
            "mid_category": str(candidate["mid_category"]).strip(),
            "sub_category": str(candidate["sub_category"]).strip(),
            "detail_category": str(candidate["detail_category"]).strip(),
            "priority": float(candidate.get("priority", 0.75)),
            "status": "candidate",
            "source": "api_generated",
        })
        existing_titles.append(title)
        added += 1

    if added == 0:
        raise RuntimeError(
            f"'{target_category}' 신규 후보가 모두 필드 또는 중복 검증에서 제외되었습니다."
        )

    return added
def create_mock_report(today: str, topic: dict) -> dict:
    return {
        "date": today,
        "title": "자막과 더빙의 문화사",
        "subtitle": "번역은 어떻게 화면의 리듬과 목소리를 바꾸었나",
        "difficulty": "중",
        "estimated_reading_time": "13-16분",
        "category": {
            "main": "언어·문자",
            "middle": "영상문화",
            "sub": "시청각 번역",
            "detail": "자막·더빙 문화"
        },
        "keywords": [
            "자막",
            "더빙",
            "영상번역",
            "로컬라이징",
            "화면 리듬",
            "문화 번역"
        ],
        "abstract": (
            "자막과 더빙은 단순히 언어를 바꾸는 기술이 아니다. "
            "그것은 화면의 속도, 배우의 몸짓, 관객의 시선, 문화적 농담을 다시 배열하는 작업이다. "
            "영상 번역은 서로 다른 언어권의 관객이 같은 장면을 각자의 감각으로 이해하도록 돕는 문화적 설계다."
        ),
        "summary_note": {
            "body": "영상 번역은 언어뿐 아니라 화면의 시간, 시선, 목소리를 함께 다시 설계하는 작업이다."
        },
        "quotation": {
            "source_type": "research",
            "kind": "paraphrase",
            "quote": "영상 번역은 말의 의미뿐 아니라 장면의 시간과 관객의 읽기 속도를 함께 설계해야 한다.",
            "attribution": "영상 번역 연구의 일반 원칙",
            "source_title": "영상 번역 개요 자료",
            "source_url": "https://example.com"
        },
        "sections": [
            {
                "label": "01 / CONTEXT",
                "title": "왜 번역은 화면에서 다시 태어나는가",
                "body": [
                    "영상 번역은 책 번역과 다르다. 문장은 화면 위에 잠깐 나타났다 사라지고, 배우의 표정과 음악, 장면 전환 속도와 함께 읽힌다.",
                    "자막은 관객이 원어의 목소리를 유지한 채 의미를 따라가게 만든다. 반대로 더빙은 관객이 화면을 읽지 않아도 이야기에 몰입하게 만든다.",
                    "따라서 영상 번역은 언어의 문제가 아니라 시간과 시선의 문제이기도 하다."
                ]
            },
            {
                "label": "02 / BEGINNER'S MAP",
                "title": "자막과 더빙의 기본 차이",
                "body": [
                    "자막은 원래 목소리를 남기고 번역문을 화면에 얹는 방식이다. 더빙은 원래 목소리를 새로운 언어의 목소리로 바꾸는 방식이다.",
                    "자막은 제작비가 상대적으로 낮고 원음의 감각을 보존하지만, 관객이 글자를 읽어야 한다. 더빙은 몰입감이 높지만 목소리 연기와 입 모양 맞춤이 중요하다."
                ]
            },
            {
                "label": "03 / DEEP DIVE",
                "title": "번역은 왜 짧아지는가",
                "body": [
                    "자막 번역은 글자 수 제한을 가진다. 말로는 길게 들을 수 있는 문장도 화면 위에서는 짧고 빠르게 읽혀야 한다.",
                    "이 과정에서 번역가는 내용을 모두 옮기기보다, 장면 이해에 필요한 의미를 압축한다. 삭제는 실패가 아니라 화면 언어에 맞춘 재구성일 수 있다.",
                    "더빙은 다른 압축을 요구한다. 번역문은 배우의 입 모양, 감정의 길이, 호흡의 위치에 맞아야 한다."
                ]
            },
            {
                "label": "04 / CASE STUDY",
                "title": "농담은 왜 가장 번역하기 어려운가",
                "body": [
                    "농담은 언어뿐 아니라 문화적 배경, 말투, 리듬에 의존한다. 그래서 직역하면 의미는 남아도 웃음은 사라질 수 있다.",
                    "영상 번역에서 좋은 농담 번역은 원문과 똑같은 문장을 찾는 것이 아니라, 같은 순간에 비슷한 반응을 일으키는 표현을 찾는 일에 가깝다."
                ]
            },
            {
                "label": "05 / CURRENT STATE",
                "title": "스트리밍 시대의 번역",
                "body": [
                    "스트리밍 플랫폼은 여러 언어의 자막과 더빙을 동시에 제공한다. 한 작품은 공개되는 순간 여러 문화권의 관객을 만난다.",
                    "그 결과 영상 번역은 부가 작업이 아니라 글로벌 배급의 핵심 인프라가 되었다."
                ]
            },
            {
                "label": "06 / IMPLICATIONS",
                "title": "번역은 누구의 목소리를 남기는가",
                "body": [
                    "자막과 더빙의 선택은 단순한 취향 문제가 아니다. 그것은 원래 배우의 목소리를 남길 것인지, 관객의 언어 경험을 우선할 것인지에 대한 선택이다.",
                    "번역은 원작을 가리는 막이 아니라, 다른 관객이 작품에 들어갈 수 있도록 놓인 문이다."
                ]
            }
        ],
        "tables": [
            {
                "title": "<표1> 자막과 더빙의 비교",
                "headers": ["구분", "자막", "더빙"],
                "rows": [
                    ["방식", "원음을 유지하고 번역문을 표시", "목소리를 현지 언어로 교체"],
                    ["장점", "원어의 감정과 연기 보존", "화면 몰입과 접근성 강화"],
                    ["약점", "읽기 부담과 글자 수 제한", "입 모양·연기·비용 부담"],
                    ["핵심", "시선을 설계하는 번역", "목소리를 설계하는 번역"]
                ],
                "caption": "자막과 더빙은 같은 내용을 옮기지만, 관객의 감각 경험을 서로 다르게 설계한다."
            }
        ],
        "takeaways": [
            {
                "title": "핵심 정리",
                "body": "영상 번역은 언어 변환이 아니라 화면의 시간, 시선, 목소리를 다시 설계하는 작업이다."
            },
            {
                "title": "요약",
                "body": "자막은 원음을 보존하고, 더빙은 관객의 언어 몰입을 높인다. 두 방식 모두 장면의 리듬에 맞춘 재구성이 필요하다."
            },
            {
                "title": "한마디",
                "body": "좋은 번역은 원문을 복사하는 일이 아니라, 다른 언어의 관객에게 같은 문을 다시 여는 일이다."
            }
        ],
        "further_reading": [
            {
                "title": "Subtitling",
                "author": "Jorge Díaz Cintas & Aline Remael",
                "reason": "자막 번역의 제약과 실제 작업 원칙을 이해하기 좋다."
            },
            {
                "title": "Audiovisual Translation",
                "author": "Frederic Chaume",
                "reason": "더빙과 영상 번역의 이론적 틀을 살펴볼 수 있다."
            }
        ],
        "sources": [
            {
                "publisher": "Reference Source",
                "title": "Audiovisual Translation Overview",
                "url": "https://example.com",
                "used_for": "영상 번역의 기본 원칙"
            }
        ]
    }


def get_report_palette(main_category: str) -> dict:
    palettes = {
        "인문·철학": {
            "paper": "#fdfcff", "ink": "#242033", "body": "#312c3d",
            "muted": "#6b6476", "line": "#c8c0d8", "line_soft": "#e4deec",
            "accent": "#65518a", "accent_dark": "#44345f",
            "table_header": "#e8e2f0", "box_bg": "#f7f4fa",
            "box_bg_strong": "#eee9f5", "screen_bg": "#f1eef6",
        },
        "자연사·생태": {
            "paper": "#fbfdf9", "ink": "#1e2e25", "body": "#2b3c31",
            "muted": "#627066", "line": "#b8cbbd", "line_soft": "#dce8df",
            "accent": "#4f7a5d", "accent_dark": "#31523d",
            "table_header": "#dfeae1", "box_bg": "#f2f7f2",
            "box_bg_strong": "#e6f0e7", "screen_bg": "#edf3ee",
        },
        "역사·문화": {
            "paper": "#fffaf8", "ink": "#30211f", "body": "#3e2d29",
            "muted": "#75635e", "line": "#d2bdb5", "line_soft": "#eaded9",
            "accent": "#975747", "accent_dark": "#68392f",
            "table_header": "#eedfd9", "box_bg": "#faf3f0",
            "box_bg_strong": "#f2e6e1", "screen_bg": "#f5eeeb",
        },
        "과학·공학": {
            "paper": "#fafdff", "ink": "#1d2b35", "body": "#273944",
            "muted": "#5e707b", "line": "#b7cbd5", "line_soft": "#dce8ed",
            "accent": "#3e7895", "accent_dark": "#28536a",
            "table_header": "#dceaf0", "box_bg": "#f1f7f9",
            "box_bg_strong": "#e4f0f4", "screen_bg": "#edf3f6",
        },
        "경제·사회": {
            "paper": "#fafffe", "ink": "#1d2d2e", "body": "#293c3d",
            "muted": "#607374", "line": "#b8cecc", "line_soft": "#dce9e8",
            "accent": "#477d7b", "accent_dark": "#2f5756",
            "table_header": "#dcebea", "box_bg": "#f1f7f7",
            "box_bg_strong": "#e5f0ef", "screen_bg": "#edf4f3",
        },
        "경제·경영": {
            "paper": "#fffdf8", "ink": "#30291d", "body": "#403727",
            "muted": "#766b55", "line": "#d4c59e", "line_soft": "#ece4cf",
            "accent": "#8a6b24", "accent_dark": "#5f4817",
            "table_header": "#eee5ca", "box_bg": "#faf6ea",
            "box_bg_strong": "#f2ead4", "screen_bg": "#f5f1e7",
        },
        "기술·공학": {
            "paper": "#f9fcff", "ink": "#1c2938", "body": "#28394b",
            "muted": "#5d6e80", "line": "#b7c8db", "line_soft": "#dce6f0",
            "accent": "#416f9f", "accent_dark": "#2b4e73",
            "table_header": "#dce7f2", "box_bg": "#f0f5fa",
            "box_bg_strong": "#e4edf6", "screen_bg": "#ecf2f7",
        },
        "생명·건강": {
            "paper": "#fcfdfb", "ink": "#203029", "body": "#2d4037",
            "muted": "#63746c", "line": "#b9cec3", "line_soft": "#dce9e2",
            "accent": "#4c8068", "accent_dark": "#315844",
            "table_header": "#dcebe3", "box_bg": "#f1f7f4",
            "box_bg_strong": "#e4f0e9", "screen_bg": "#edf4f0",
        },
        "예술·미학": {
            "paper": "#fffafd", "ink": "#30232d", "body": "#3f303b",
            "muted": "#786873", "line": "#d3becb", "line_soft": "#eadde5",
            "accent": "#8b5878", "accent_dark": "#613a53",
            "table_header": "#eedfe8", "box_bg": "#faf3f7",
            "box_bg_strong": "#f2e6ed", "screen_bg": "#f5eef2",
        },
        "생활기술·일상문화": {
            "paper": "#fffdf8", "ink": "#2d251e", "body": "#3c3128",
            "muted": "#74685d", "line": "#d2c2b2", "line_soft": "#e9dfd5",
            "accent": "#96663f", "accent_dark": "#654329",
            "table_header": "#eadfce", "box_bg": "#f8f4ed",
            "box_bg_strong": "#f0e8dc", "screen_bg": "#f3f0ea",
        },
        "언어·문자": {
            "paper": "#fbfcff", "ink": "#222937", "body": "#303849",
            "muted": "#667080", "line": "#bdc7d7", "line_soft": "#dee4ed",
            "accent": "#536b91", "accent_dark": "#384b6c",
            "table_header": "#dfe5ef", "box_bg": "#f3f6fa",
            "box_bg_strong": "#e7ecf4", "screen_bg": "#eef1f6",
        },
    }
    category_aliases = {
        "환경": "자연사·생태",
        "기술": "과학·공학",
        "사회·정치·법": "경제·사회",
        "과학·수학": "과학·공학",
        "자연·환경·지리": "자연사·생태",
        "예술·디자인": "예술·미학",
        "언어·미디어·지식": "언어·문자",
    }
    palette_key = category_aliases.get(main_category, main_category)
    return palettes.get(palette_key, {
        "paper": "#fffdf8", "ink": "#1f1b16", "body": "#2b241d",
        "muted": "#665c52", "line": "#cbbba7", "line_soft": "#ded1c2",
        "accent": "#8a5a2b", "accent_dark": "#4d3018",
        "table_header": "#e7d9c5", "box_bg": "#f8f3ec",
        "box_bg_strong": "#f1e6d8", "screen_bg": "#f4f0e8",
    })


def load_quotation_source_types() -> dict[str, str]:
    """첨언 출처 유형 id와 PDF 소제목을 설정 파일에서 불러온다."""
    config = load_json(QUOTATION_SOURCE_TYPES_PATH, default={})
    raw_types = config.get("types", []) if isinstance(config, dict) else []
    if not isinstance(raw_types, list) or not raw_types:
        raise ValueError("quotation_source_types 설정에 types 목록이 필요합니다.")

    source_types = {}
    for index, item in enumerate(raw_types, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"quotation_source_types.types[{index}]가 객체가 아닙니다.")
        source_type_id = str(item.get("id", "")).strip()
        label = str(item.get("label", "")).strip()
        if not re.fullmatch(r"[a-z][a-z0-9_]*", source_type_id):
            raise ValueError(
                f"quotation 출처 유형 id가 올바르지 않습니다: {source_type_id or '(빈 값)'}"
            )
        if not label:
            raise ValueError(f"quotation 출처 유형 '{source_type_id}'의 label이 비었습니다.")
        if source_type_id in source_types:
            raise ValueError(f"중복된 quotation 출처 유형 id입니다: {source_type_id}")
        source_types[source_type_id] = label
    return source_types


def render_html(report: dict, output_path: Path):
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("report.html.j2")
    palette = get_report_palette(report.get("category", {}).get("main", ""))
    html = template.render(
        report=report,
        palette=palette,
        quotation_source_types=load_quotation_source_types(),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def render_pdf_with_playwright(html_path: Path, pdf_path: Path, report: dict):
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    date_text = escape(str(report.get("date", "")).replace("-", "."))
    category = report.get("category", {})
    palette = get_report_palette(category.get("main", ""))
    category_text = " / ".join(
        escape(str(category.get(key, "")).strip())
        for key in ("main", "middle")
        if category.get(key)
    )
    # Chromium can paint body fragments over a standalone header template on
    # continuation pages. The footer template repeats reliably, so it carries
    # both the running header (shifted to the top margin) and the page number.
    footer_template = (
        '<div style="box-sizing:border-box;width:100%;margin:0 14mm;position:relative;'
        f'color:{palette["muted"]};font-family:Arial,\'Malgun Gothic\',sans-serif;font-size:9px;">'
        '<div style="position:absolute;left:1mm;right:1mm;bottom:270mm;'
        f'padding-bottom:6px;border-bottom:1px solid {palette["line"]};font-weight:700;'
        'line-height:1.2;display:flex;justify-content:space-between;gap:18px;">'
        f'<span>GLOBAL KNOWLEDGE JOURNAL / {date_text}</span>'
        f'<span>{category_text}</span></div>'
        f'<div style="padding-top:6px;border-top:1px solid {palette["line"]};'
        'font-family:Arial,sans-serif;text-align:center;">'
        '<span class="pageNumber"></span></div></div>'
    )

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
        page.pdf(
            path=str(pdf_path),
            format="A4",
            print_background=True,
            prefer_css_page_size=True,
            display_header_footer=True,
            margin={"top": "23mm", "right": "15mm", "bottom": "23mm", "left": "15mm"},
            header_template="<div></div>",
            footer_template=footer_template,
        )
        browser.close()


def validate_pdf_page_count(pdf_path: Path, min_pages: int = 6, max_pages: int = 9) -> None:
    """렌더링된 API PDF가 목표 페이지 범위인지 검사한다."""
    from pypdf import PdfReader

    with pdf_path.open("rb") as pdf_stream:
        page_count = len(PdfReader(pdf_stream).pages)
    if not min_pages <= page_count <= max_pages:
        raise ValueError(
            f"PDF 페이지 수가 목표 범위를 벗어났습니다: "
            f"{page_count}페이지, {min_pages}~{max_pages}페이지 필요"
        )


def update_topic_db(topic_db: dict, report: dict, html_path: Path, pdf_path: Path):
    today = report["date"]
    taxonomy = load_topic_taxonomy()
    category_order = taxonomy["category_order"]
    current_main_category = report["category"]["main"]
    if current_main_category not in category_order:
        raise ValueError(
            f"발행 리포트의 대분류가 taxonomy v2에 없습니다: {current_main_category}"
        )

    recent_reports = topic_db.setdefault("recent_reports", [])
    report_title_key = normalize_topic_title(report["title"])
    recent_reports[:] = [
        item for item in recent_reports
        if not (
            item.get("date") == today
            and normalize_topic_title(item.get("title", "")) == report_title_key
        )
    ]
    recent_reports.append({
        "date": today,
        "title": report["title"],
        "main_category": report["category"]["main"],
        "mid_category": report["category"]["middle"],
        "sub_category": report["category"]["sub"],
        "detail_category": report["category"]["detail"],
        "taxonomy_version": taxonomy["taxonomy_version"],
        "keywords": report["keywords"],
        "html_path": str(html_path.as_posix()),
        "pdf_path": str(pdf_path.as_posix()),
        "status": report.get("status", "published_api")
    })

    topic_db["updated_at"] = today

    published_reports = [
        item for item in recent_reports
        if item.get("status") in {"published", "published_api"}
    ]
    recent_main_categories = [
        canonical_main_category(item, taxonomy) or item.get("main_category", "")
        for item in published_reports[-10:]
        if item.get("main_category")
    ]
    category_counts = {category: 0 for category in category_order}
    for item in published_reports:
        category = canonical_main_category(item, taxonomy)
        if category in category_counts:
            category_counts[category] += 1

    current_index = category_order.index(current_main_category)
    next_index = (current_index + 1) % len(category_order)
    previous_rotation = topic_db.get("category_rotation", {})
    completed_cycles = int(previous_rotation.get("completed_cycles", 0))
    if next_index == 0:
        completed_cycles += 1

    topic_db["category_rotation"] = {
        "taxonomy_version": taxonomy["taxonomy_version"],
        "category_order": category_order,
        "last_main_category": current_main_category,
        "next_main_category": category_order[next_index],
        "next_index": next_index,
        "completed_cycles": completed_cycles,
        "published_counts": category_counts,
        "recent_main_categories": recent_main_categories,
    }

    for candidate in topic_db.get("candidate_pool", []):
        if normalize_topic_title(candidate.get("topic", "")) == report_title_key:
            candidate["status"] = "used"

    save_json(TOPIC_DB_PATH, topic_db)


def rebuild_sqlite(topic_db: dict):
    if TOPIC_DB_SQLITE_PATH.exists():
        TOPIC_DB_SQLITE_PATH.unlink()

    conn = sqlite3.connect(TOPIC_DB_SQLITE_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE reports (
            date TEXT PRIMARY KEY,
            title TEXT,
            main_category TEXT,
            mid_category TEXT,
            sub_category TEXT,
            detail_category TEXT,
            taxonomy_version TEXT,
            keywords TEXT,
            html_path TEXT,
            pdf_path TEXT,
            status TEXT
        )
    """)

    for item in topic_db.get("recent_reports", []):
        cur.execute(
            """
            INSERT OR REPLACE INTO reports
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.get("date", ""),
                item.get("title", ""),
                item.get("main_category", ""),
                item.get("mid_category", ""),
                item.get("sub_category", ""),
                item.get("detail_category", ""),
                item.get("taxonomy_version", ""),
                json.dumps(item.get("keywords", []), ensure_ascii=False),
                item.get("html_path", ""),
                item.get("pdf_path", ""),
                item.get("status", "")
            )
        )

    cur.execute("""
        CREATE TABLE candidates (
            topic TEXT,
            main_category TEXT,
            mid_category TEXT,
            sub_category TEXT,
            detail_category TEXT,
            priority REAL,
            status TEXT,
            source TEXT
        )
    """)

    for item in topic_db.get("candidate_pool", []):
        cur.execute(
            """
            INSERT INTO candidates
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.get("topic", ""),
                item.get("main_category", ""),
                item.get("mid_category", ""),
                item.get("sub_category", ""),
                item.get("detail_category", ""),
                float(item.get("priority", 0)),
                item.get("status", ""),
                item.get("source", "")
            )
        )

    conn.commit()
    conn.close()


def update_public_catalog(report: dict, html_path: Path, pdf_path: Path):
    def to_public_asset_path(path_value) -> str:
        path_text = str(path_value).replace("\\", "/")

        if "outputs/" in path_text:
            return "outputs/" + path_text.split("outputs/", 1)[1]

        try:
            return Path(path_value).resolve().relative_to(ROOT_DIR.resolve()).as_posix()
        except ValueError:
            return Path(path_value).name

    def normalize_catalog_item(item: dict) -> dict:
        normalized = dict(item)

        for key in ["html_path", "pdf_path", "html_url", "pdf_url"]:
            value = normalized.get(key)

            if value and value != "...":
                normalized[key] = to_public_asset_path(value)

        if normalized.get("html_path") and not normalized.get("html_url"):
            normalized["html_url"] = normalized["html_path"]

        if normalized.get("pdf_path") and not normalized.get("pdf_url"):
            normalized["pdf_url"] = normalized["pdf_path"]

        return normalized

    reports = load_json(REPORTS_JSON_PATH, [])

    reports = [
        normalize_catalog_item(item)
        for item in reports
        if isinstance(item, dict)
    ]

    today = report["date"]

    reports = [
        item for item in reports
        if item.get("date") != today
    ]

    html_public_path = to_public_asset_path(html_path)
    pdf_public_path = to_public_asset_path(pdf_path)

    item = {
        "date": today,
        "title": report["title"],
        "subtitle": report["subtitle"],
        "main_category": report["category"]["main"],
        "mid_category": report["category"]["middle"],
        "sub_category": report["category"]["sub"],
        "detail_category": report["category"]["detail"],
        "taxonomy_version": report.get("taxonomy_version", "2.0"),
        "html_path": html_public_path,
        "pdf_path": pdf_public_path,
        "html_url": html_public_path,
        "pdf_url": pdf_public_path,
        "status": report.get("status", "published_mock")
    }

    reports.append(item)
    reports.sort(key=lambda x: x["date"], reverse=True)

    save_json(REPORTS_JSON_PATH, reports)
    # 과거 누락 날짜를 백필해도 홈페이지의 최신 리포트는 가장 최근 날짜를 유지한다.
    save_json(LATEST_JSON_PATH, reports[0])

    manifest = {
        "last_updated": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
        "reports": reports
    }

    save_json(MANIFEST_PATH, manifest)


def record_generation_timeline(
    report: dict,
    generation_started_at: str,
    generation_completed_at: str,
    catalog_updated_at: str,
    validation_attempts: int,
) -> dict:
    """성공한 API 생성의 예약·실행·저장 시각을 공개 이력에 누적한다."""
    report_date = str(report.get("date", "")).strip()
    schedule_cron = os.getenv("REPORT_SCHEDULE_CRON", "").strip()
    workflow_started_at = os.getenv("REPORT_RUN_STARTED_AT", "").strip()
    run_id = os.getenv("GITHUB_RUN_ID", "").strip()
    repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    server_url = os.getenv("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
    run_url = (
        f"{server_url}/{repository}/actions/runs/{run_id}"
        if repository and run_id
        else ""
    )
    scheduled_at = scheduled_for_kst(report_date, schedule_cron)

    entry = {
        "date": report_date,
        "title": report.get("title", ""),
        "status": report.get("status", "published_api"),
        "event_name": os.getenv("GITHUB_EVENT_NAME", "local"),
        "schedule_cron": schedule_cron,
        "scheduled_for_kst": scheduled_at,
        "workflow_started_at": workflow_started_at,
        "generation_started_at": generation_started_at,
        "generation_completed_at": generation_completed_at,
        "catalog_updated_at": catalog_updated_at,
        "scheduler_delay_seconds": (
            seconds_between(scheduled_at, workflow_started_at)
            if scheduled_at and workflow_started_at
            else None
        ),
        "setup_duration_seconds": seconds_between(
            workflow_started_at,
            generation_started_at,
        ),
        "generation_duration_seconds": seconds_between(
            generation_started_at,
            catalog_updated_at,
        ),
        "validation_attempts": validation_attempts,
        "run_id": run_id,
        "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT", ""),
        "run_url": run_url,
        "source_sha": os.getenv("GITHUB_SHA", ""),
    }

    history = load_json(GENERATION_HISTORY_PATH, default=[])
    if not isinstance(history, list):
        history = []
    if run_id:
        history = [
            item for item in history
            if str(item.get("run_id", "")) != run_id
        ]
    history.append(entry)
    history.sort(
        key=lambda item: str(item.get("catalog_updated_at", "")),
        reverse=True,
    )
    history = history[:30]

    save_json(GENERATION_HISTORY_PATH, history)
    save_json(GENERATION_STATUS_PATH, entry)
    return entry


def save_render_publish_report(report: dict, topic_db: dict, mode: str = "mock"):
    today = resolve_report_date(str(report.get("date", "")).strip() or None)
    report["date"] = today
    report["status"] = f"published_{mode}"
    if mode == "api":
        report["taxonomy_version"] = load_topic_taxonomy()["taxonomy_version"]

    date_compact = compact_date(today)

    raw_slug = report.get("title_slug") or report.get("title") or "report"
    title_slug = slugify_korean(raw_slug)

    html_path = OUTPUTS_DIR / f"{date_compact}_{title_slug}_Report.html"
    pdf_path = OUTPUTS_DIR / f"{date_compact}_{title_slug}_Report.pdf"
    report_json_path = OUTPUTS_DIR / f"{date_compact}_{title_slug}_Report.json"

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=".report-", dir=OUTPUTS_DIR) as staging_dir:
        staging_path = Path(staging_dir)
        staged_json_path = staging_path / report_json_path.name
        staged_html_path = staging_path / html_path.name
        staged_pdf_path = staging_path / pdf_path.name

        save_json(staged_json_path, report)
        render_html(report, staged_html_path)
        render_pdf_with_playwright(staged_html_path, staged_pdf_path, report)

        if mode == "api":
            validate_pdf_page_count(staged_pdf_path)

        staged_json_path.replace(report_json_path)
        staged_html_path.replace(html_path)
        staged_pdf_path.replace(pdf_path)

    if mode == "api":
        update_topic_db(topic_db, report, html_path, pdf_path)
        rebuild_sqlite(topic_db)
        update_public_catalog(report, html_path, pdf_path)

    print("생성 완료")
    print(f"리포트 JSON: {report_json_path}")
    print(f"HTML: {html_path}")
    print(f"PDF: {pdf_path}")
    if mode == "api":
        print(f"주제 DB JSON: {TOPIC_DB_PATH}")
        print(f"주제 DB SQLite: {TOPIC_DB_SQLITE_PATH}")
        print(f"공개 목록: {REPORTS_JSON_PATH}")
        print(f"최신 리포트: {LATEST_JSON_PATH}")
    else:
        print("mock 모드: outputs만 생성하고 주제 DB와 공개 카탈로그는 변경하지 않았습니다.")


def normalize_table_rows(report: dict) -> dict:
    """표의 모든 행을 헤더 열 수에 맞춰 PDF 레이아웃 붕괴를 방지한다."""
    tables = report.get("tables", [])
    if not isinstance(tables, list):
        return report

    for table in tables:
        if not isinstance(table, dict):
            continue

        headers = table.get("headers", [])
        rows = table.get("rows", [])
        if not isinstance(headers, list) or not headers or not isinstance(rows, list):
            continue

        column_count = len(headers)
        normalized_rows = []

        for row in rows:
            cells = list(row) if isinstance(row, list) else [row]
            cells = [str(cell).strip() for cell in cells]

            while len(cells) > column_count and not cells[-1]:
                cells.pop()

            if len(cells) > column_count:
                overflow = " · ".join(cell for cell in cells[column_count - 1:] if cell)
                cells = cells[:column_count - 1] + [overflow]
            elif len(cells) < column_count:
                cells.extend([""] * (column_count - len(cells)))

            normalized_rows.append(cells)

        table["rows"] = normalized_rows

    return report


def run_mock(report_date: str | None = None):
    today = resolve_report_date(report_date)

    topic_db = load_json(TOPIC_DB_PATH, default={})
    topic = select_topic(topic_db)

    report = normalize_table_rows(create_mock_report(today, topic))

    save_render_publish_report(report, topic_db, mode="mock")

def enforce_selected_topic(report: dict, selected_topic: dict) -> dict:
    expected_title = (
        selected_topic.get("topic")
        or selected_topic.get("title")
        or ""
    ).strip()

    actual_title = str(report.get("title", "")).strip()

    if expected_title and actual_title and expected_title != actual_title:
        raise ValueError(
            "생성된 리포트 제목이 선정 주제와 다릅니다. "
            f"선정 주제='{expected_title}', 생성 제목='{actual_title}'"
        )

    if expected_title:
        report["title"] = expected_title

    category = report.get("category")
    if not isinstance(category, dict):
        category = {}

    main_category = (
        selected_topic.get("main_category")
        or selected_topic.get("main")
        or category.get("main")
        or ""
    )

    middle_category = (
        selected_topic.get("middle_category")
        or selected_topic.get("mid_category")
        or selected_topic.get("middle")
        or category.get("middle")
        or ""
    )

    sub_category = (
        selected_topic.get("sub_category")
        or selected_topic.get("sub")
        or category.get("sub")
        or ""
    )

    detail_category = (
        selected_topic.get("detail_category")
        or selected_topic.get("detail")
        or category.get("detail")
        or selected_topic.get("topic")
        or report.get("title")
        or ""
    )

    report["category"] = {
        "main": main_category,
        "middle": middle_category,
        "sub": sub_category,
        "detail": detail_category,
    }

    return report


def normalize_source_url_for_comparison(url: str) -> str:
    """표시 URL은 보존하되 흔한 추적값·표기 차이를 제외하고 비교한다."""
    url_text = str(url).strip()
    try:
        parts = urlsplit(url_text)
    except ValueError:
        return url_text

    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        return url_text

    query_items = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in {"fbclid", "gclid"}
    ]
    normalized_path = parts.path.rstrip("/") or "/"
    return urlunsplit((
        parts.scheme.lower(),
        parts.netloc.lower(),
        normalized_path,
        urlencode(sorted(query_items), doseq=True),
        "",
    ))

def validate_report_structure(report: dict) -> None:
    """API 리포트가 핵심 섹션과 최소 분량을 갖췄는지 검사한다."""
    min_valid_paragraph_characters = 80
    min_total_body_characters = 5000
    required_ids = ["01", "02", "03", "03-1", "03-2", "03-3", "03-4", "03-5", "04", "05", "06"]

    sections = report.get("sections", [])
    if not isinstance(sections, list):
        raise ValueError("report.sections가 list가 아닙니다.")

    section_map = {}
    duplicate_ids = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("id", "")).strip()
        if section_id in section_map:
            duplicate_ids.append(section_id)
        section_map[section_id] = section

    if duplicate_ids:
        raise ValueError("중복된 섹션 ID가 있습니다: " + ", ".join(sorted(set(duplicate_ids))))

    missing = [section_id for section_id in required_ids if section_id not in section_map]
    if missing:
        raise ValueError("필수 섹션이 누락되었습니다: " + ", ".join(missing))

    min_paragraphs = {
        "01": 4,
        "02": 2,
        "03": 2,
        "03-1": 3,
        "03-2": 3,
        "03-3": 3,
        "03-4": 3,
        "03-5": 3,
        "04": 5,
        "05": 5,
        "06": 5,
    }

    too_short = []
    short_paragraphs = []
    total_paragraphs = 0
    total_body_characters = 0
    leaked_instruction_text = []
    forbidden_fragments = (
        "the final complete json response output",
        "this is the only output",
        "json follows",
        "without explanations",
        "sorry for the partial response",
        "section_notes area was requested",
        "need full json",
        "partial and corrupt",
        "body: 5문단 작성 required",
        "자동화 파이프라인 설명",
        "section_notes_",
        "paragraph_count_",
        "general_structure",
        "length_minimum_",
        "paragraphs_maximum_",
    )
    instruction_snake_case = re.compile(
        r"\b(?:section|sections|section_notes|paragraph|paragraphs|body|label|labels|"
        r"schema|json|response|instruction|system|prompt|minimum|maximum|required|must|check)"
        r"(?:_[a-z0-9]+){2,}\b",
        re.IGNORECASE,
    )
    section_body_path = re.compile(r"^report\.sections\[\d+\]\.body\[\d+\]$")

    def iter_text_nodes(value, path="report"):
        if isinstance(value, str):
            yield path, value
        elif isinstance(value, dict):
            for key, child in value.items():
                yield from iter_text_nodes(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                yield from iter_text_nodes(child, f"{path}[{index}]")

    for section_id, minimum in min_paragraphs.items():
        raw_body = section_map[section_id].get("body", [])
        body = (
            [paragraph for paragraph in raw_body if isinstance(paragraph, str) and paragraph.strip()]
            if isinstance(raw_body, list)
            else []
        )
        total_paragraphs += len(body)
        total_body_characters += sum(len(paragraph.strip()) for paragraph in body)
        if len(body) < minimum:
            too_short.append(f"{section_id}: 유효한 {len(body)}문단, 최소 {minimum}문단 필요")
        for paragraph_index, paragraph in enumerate(body, start=1):
            clean_paragraph = paragraph.strip()
            paragraph_length = len(clean_paragraph)
            if paragraph_length < min_valid_paragraph_characters:
                short_paragraphs.append(
                    f"{section_id}의 {paragraph_index}번째 문단: "
                    f"{paragraph_length}자, 최소 {min_valid_paragraph_characters}자 필요"
                )

    for text_path, text_value in iter_text_nodes(report):
        lowered = text_value.strip().lower()
        matched_fragment = next(
            (fragment for fragment in forbidden_fragments if fragment in lowered),
            None,
        )
        json_key_hits = sum(
            marker in lowered
            for marker in ('"sections"', '"label"', '"id"', '"title"', '"body"')
        )
        leak_reasons = []
        if matched_fragment:
            leak_reasons.append(matched_fragment)
        if json_key_hits >= 3:
            leak_reasons.append(f"JSON 필드 표식 {json_key_hits}개")
        if instruction_snake_case.search(lowered):
            leak_reasons.append("내부 지시문 형태의 snake_case 문자열")
        if any(fragment in lowered for fragment in ("},{", "}],{", "},{\"")):
            leak_reasons.append("직렬화된 JSON 조각")
        if section_body_path.match(text_path) and ("\n" in text_value or "\r" in text_value):
            leak_reasons.append("본문 문단 내부 개행")
        if len(text_value) - len(text_value.rstrip()) > 3:
            leak_reasons.append("과도한 후행 공백")
        if leak_reasons:
            leaked_instruction_text.append(
                f"{text_path} ({', '.join(dict.fromkeys(leak_reasons))})"
            )

    if too_short:
        raise ValueError("본문 분량이 부족합니다. " + " / ".join(too_short))

    if short_paragraphs:
        raise ValueError("너무 짧은 본문 문단이 있습니다. " + " / ".join(short_paragraphs))

    if leaked_instruction_text:
        raise ValueError(
            "리포트에 시스템 지시문·JSON 생성 메모로 의심되는 문구가 있습니다: "
            + " / ".join(leaked_instruction_text)
        )

    if total_paragraphs < 36:
        raise ValueError(f"본문 총 문단 수가 부족합니다: {total_paragraphs}문단, 최소 36문단 필요")

    if total_body_characters < min_total_body_characters:
        raise ValueError(
            f"본문 총 글자 수가 부족합니다: "
            f"{total_body_characters}자, 최소 {min_total_body_characters}자 필요"
        )

    tables = report.get("tables", [])
    if not isinstance(tables, list) or len(tables) < 4:
        raise ValueError("tables는 최소 4개가 필요합니다.")

    takeaways = report.get("takeaways", [])
    if not isinstance(takeaways, list) or len(takeaways) != 3:
        raise ValueError("takeaways는 정확히 3개가 필요합니다.")

    term_box = report.get("term_box", {})
    term_items = term_box.get("items", []) if isinstance(term_box, dict) else []
    if not isinstance(term_items, list) or len(term_items) != 4:
        raise ValueError("term_box.items는 정확히 4개가 필요합니다.")

    flow_diagram = report.get("flow_diagram", {})
    flow_steps = flow_diagram.get("steps", []) if isinstance(flow_diagram, dict) else []
    if not isinstance(flow_steps, list) or len(flow_steps) < 4:
        raise ValueError("flow_diagram.steps는 최소 4개가 필요합니다.")

    section_notes = report.get("section_notes", [])
    if not isinstance(section_notes, list) or len(section_notes) < 2:
        raise ValueError("section_notes는 최소 2개가 필요합니다.")

    sources = report.get("sources", [])
    if not isinstance(sources, list) or len(sources) < 5:
        raise ValueError("sources는 최소 5개가 필요합니다.")

    quotation = report.get("quotation", {})
    if not isinstance(quotation, dict):
        raise ValueError("quotation은 출처가 있는 인용·전문가 첨언 객체여야 합니다.")

    quotation_required = [
        "source_type", "kind", "quote", "attribution", "source_title", "source_url"
    ]
    missing_quotation_fields = [
        field for field in quotation_required
        if not str(quotation.get(field, "")).strip()
    ]
    if missing_quotation_fields:
        raise ValueError(
            "quotation 필수 필드가 누락되었습니다: "
            + ", ".join(missing_quotation_fields)
        )

    if quotation.get("kind") not in {"direct_quote", "paraphrase"}:
        raise ValueError("quotation.kind는 direct_quote 또는 paraphrase여야 합니다.")

    source_types = load_quotation_source_types()
    quotation_source_type = str(quotation.get("source_type", "")).strip()
    if quotation_source_type not in source_types:
        raise ValueError(
            "quotation.source_type이 등록된 출처 유형이 아닙니다: "
            f"{quotation_source_type or '(빈 값)'}. "
            "허용값: " + ", ".join(source_types)
        )

    quotation_url = str(quotation.get("source_url", "")).strip()
    if not quotation_url.startswith(("https://", "http://")):
        raise ValueError("quotation.source_url은 확인 가능한 http(s) URL이어야 합니다.")

    source_urls = {
        normalize_source_url_for_comparison(source.get("url", "")): str(
            source.get("url", "")
        ).strip()
        for source in sources
        if isinstance(source, dict)
    }
    normalized_quotation_url = normalize_source_url_for_comparison(quotation_url)
    matching_source_url = source_urls.get(normalized_quotation_url)
    if not matching_source_url:
        raise ValueError(
            "quotation.source_url이 sources의 URL과 일치하지 않습니다"
            "(추적 매개변수·끝 슬래시 정규화 비교 포함)."
        )
    # 렌더링·저장 데이터에는 Sources에 적힌 정확한 문자열을 재사용한다.
    quotation["source_url"] = matching_source_url


def run_api(report_date: str | None = None):
    from generate_report import (
        generate_report,
        generate_topic_candidates_with_api,
    )

    requested_date = str(
        report_date if report_date is not None else os.getenv("REPORT_DATE", "")
    ).strip()
    today = resolve_report_date(report_date)
    generation_started_at = utc_now_iso()

    if os.getenv("REPORT_SKIP_EXISTING_DATE", "0") == "1" or requested_date:
        published_reports = load_json(REPORTS_JSON_PATH, default=[])
        if not isinstance(published_reports, list):
            published_reports = []
        already_published = any(
            isinstance(item, dict)
            and item.get("date") == today
            and item.get("status") == "published_api"
            for item in published_reports
        )
        if already_published:
            print(
                f"{today}에는 이미 정식 발행된 리포트가 있어 "
                "중복 생성·덮어쓰기를 건너뜁니다."
            )
            return

    topic_db = load_json(TOPIC_DB_PATH, default={})
    try:
        topic = select_topic(topic_db)
    except TopicPoolExhaustedError as exc:
        taxonomy = load_topic_taxonomy()
        category_definition = next(
            category for category in taxonomy["categories"]
            if category["name"] == exc.target_category
        )
        existing_titles = [
            item.get("topic", "")
            for item in topic_db.get("candidate_pool", [])
            if isinstance(item, dict)
        ]
        existing_titles.extend(
            item.get("title", "")
            for item in get_published_topic_history(topic_db)
        )
        batch_size = int(taxonomy.get("generated_candidate_batch_size", 5))
        generated_candidates = generate_topic_candidates_with_api(
            target_category=exc.target_category,
            category_description=category_definition.get("description", ""),
            existing_titles=existing_titles,
            count=batch_size,
        )
        added_count = add_generated_topic_candidates(
            topic_db=topic_db,
            target_category=exc.target_category,
            generated_candidates=generated_candidates,
        )
        print(
            f"주제 후보 보충 완료: '{exc.target_category}' {added_count}개 추가"
        )
        topic = select_topic(topic_db)

    print("OpenAI API로 리포트를 생성합니다.")
    print(f"선정 주제: {topic.get('topic')}")

    validation_retries = int(os.getenv("REPORT_VALIDATION_RETRIES", "1"))
    if validation_retries < 0:
        raise ValueError("REPORT_VALIDATION_RETRIES는 0 이상의 정수여야 합니다.")

    validation_feedback = ""
    total_attempts = validation_retries + 1

    for attempt_index in range(total_attempts):
        attempt_number = attempt_index + 1
        print(f"리포트 생성 시도 {attempt_number}/{total_attempts}")

        report = generate_report(
            today=today,
            selected_topic=topic,
            validation_feedback=validation_feedback,
        )
        # 모델 응답의 날짜를 신뢰하지 않고 실행에서 확정한 발행일을 고정한다.
        report["date"] = today
        report = enforce_selected_topic(report, topic)
        report = normalize_table_rows(report)

        try:
            validate_report_structure(report)
        except ValueError as exc:
            if attempt_index >= validation_retries:
                raise

            validation_feedback = str(exc)
            print(
                "리포트 구조 검증 실패: "
                f"{validation_feedback} / 오류 내용을 반영해 전체 JSON을 다시 생성합니다. "
                f"남은 재생성 횟수: {validation_retries - attempt_index}"
            )
            continue

        generation_completed_at = utc_now_iso()
        save_render_publish_report(report, topic_db, mode="api")
        catalog_updated_at = utc_now_iso()
        try:
            timeline = record_generation_timeline(
                report=report,
                generation_started_at=generation_started_at,
                generation_completed_at=generation_completed_at,
                catalog_updated_at=catalog_updated_at,
                validation_attempts=attempt_number,
            )
            print("생성 타임라인 기록 완료")
            print(json.dumps(timeline, ensure_ascii=False))
        except Exception as exc:
            # 측정 정보 실패가 검증 완료 리포트의 발행을 막지 않도록 한다.
            print(f"경고: 생성 타임라인을 기록하지 못했습니다: {exc}")
        return

    raise RuntimeError("리포트 생성 시도 횟수를 소진했습니다.")


def main():
    parser = argparse.ArgumentParser()
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--mock", action="store_true", help="OpenAI API 없이 mock 리포트를 생성합니다.")
    mode_group.add_argument("--api", action="store_true", help="OpenAI API로 실제 리포트를 생성합니다.")
    parser.add_argument(
        "--date",
        help="누락 날짜 복구용 발행일(YYYY-MM-DD). 생략하면 한국 기준 오늘입니다.",
    )

    args = parser.parse_args()

    if args.api:
        run_api(report_date=args.date)
    else:
        run_mock(report_date=args.date)


if __name__ == "__main__":
    main()




