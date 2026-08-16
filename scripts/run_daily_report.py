import argparse
from html import escape
import json
import os
import re
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
OUTPUTS_DIR = ROOT_DIR / "outputs"
PUBLIC_DIR = ROOT_DIR / "public"
TEMPLATES_DIR = ROOT_DIR / "templates"

TOPIC_DB_PATH = DATA_DIR / "topic_db.json"
TOPIC_DB_SQLITE_PATH = DATA_DIR / "topic_db.sqlite"
MANIFEST_PATH = DATA_DIR / "manifest.json"
REPORTS_JSON_PATH = PUBLIC_DIR / "reports.json"
LATEST_JSON_PATH = PUBLIC_DIR / "latest.json"


def get_today_kst() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")


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


def select_topic(topic_db):
    default_candidate_pool = [
        {
            "topic": "자막과 더빙의 문화사: 번역은 어떻게 화면의 리듬이 되었나",
            "main_category": "언어·문자",
            "mid_category": "영상번역",
            "priority": 0.88,
            "status": "candidate",
        },
        {
            "topic": "무지의 베일: 공정한 사회는 어떻게 상상되는가",
            "main_category": "인문·철학",
            "mid_category": "정치철학",
            "priority": 0.86,
            "status": "candidate",
        },
        {
            "topic": "철새의 항로: 새들은 어떻게 지구를 기억하는가",
            "main_category": "자연사·생태",
            "mid_category": "동물행동",
            "priority": 0.84,
            "status": "candidate",
        },
        {
            "topic": "시간표의 탄생: 근대 사회는 어떻게 시간을 표준화했나",
            "main_category": "역사·문화",
            "mid_category": "시간문화",
            "priority": 0.82,
            "status": "candidate",
        },
        {
            "topic": "전기요금의 정치학: 에너지 가격은 왜 단순한 숫자가 아닌가",
            "main_category": "경제·사회",
            "mid_category": "에너지정책",
            "priority": 0.80,
            "status": "candidate",
        },
        {
            "topic": "타이포그래피의 목소리: 글자는 어떻게 말투가 되었나",
            "main_category": "예술·미학",
            "mid_category": "그래픽디자인",
            "priority": 0.78,
            "status": "candidate",
        },
        {
            "topic": "도시의 하수도: 보이지 않는 위생 인프라는 어떻게 문명을 바꾸었나",
            "main_category": "생활기술·일상문화",
            "mid_category": "도시인프라",
            "priority": 0.76,
            "status": "candidate",
        },
        {
            "topic": "달력의 역사: 인간은 어떻게 시간을 나누고 약속했나",
            "main_category": "역사·문화",
            "mid_category": "시간문화",
            "priority": 0.74,
            "status": "candidate",
        },
        {
            "topic": "유리의 문명사: 투명한 물질은 어떻게 세계를 바꾸었나",
            "main_category": "과학·공학",
            "mid_category": "재료와 문명",
            "priority": 0.72,
            "status": "candidate",
        },
        {
            "topic": "벌집의 수학: 육각형은 왜 자연의 설계도가 되었나",
            "main_category": "자연사·생태",
            "mid_category": "생물과 구조",
            "priority": 0.70,
            "status": "candidate",
        },
        {
            "topic": "도서관 분류의 정치학: 지식은 누가 어떤 순서로 배열하는가",
            "main_category": "언어·문자",
            "mid_category": "지식분류",
            "priority": 0.81,
            "status": "candidate",
        },
        {
            "topic": "보험의 탄생: 위험은 어떻게 공동의 계산이 되었나",
            "main_category": "경제·사회",
            "mid_category": "위험과 제도",
            "priority": 0.80,
            "status": "candidate",
        },
        {
            "topic": "밤의 빛과 생태계: 인공조명은 생명의 시간을 어떻게 바꾸는가",
            "main_category": "자연사·생태",
            "mid_category": "생태환경",
            "priority": 0.79,
            "status": "candidate",
        },
        {
            "topic": "소리의 건축: 공간은 어떻게 듣는 경험을 설계하는가",
            "main_category": "예술·미학",
            "mid_category": "공간미학",
            "priority": 0.78,
            "status": "candidate",
        },
        {
            "topic": "바닷물을 식수로: 담수화 기술은 물 부족의 해답이 될 수 있는가",
            "main_category": "과학·공학",
            "mid_category": "물환경공학",
            "priority": 0.77,
            "status": "candidate",
        },
        {
            "topic": "우편번호의 사회사: 숫자는 어떻게 도시와 사람을 연결했나",
            "main_category": "생활기술·일상문화",
            "mid_category": "행정인프라",
            "priority": 0.76,
            "status": "candidate",
        },
        {
            "topic": "확률과 우연의 철학: 불확실성은 어떻게 지식이 되는가",
            "main_category": "인문·철학",
            "mid_category": "과학철학",
            "priority": 0.75,
            "status": "candidate",
        },
        {
            "topic": "향신료 교역의 세계사: 맛은 어떻게 제국과 항로를 움직였나",
            "main_category": "역사·문화",
            "mid_category": "교역문화",
            "priority": 0.74,
            "status": "candidate",
        },
    ]

    candidate_pool = topic_db.setdefault("candidate_pool", [])
    known_candidate_titles = {
        normalize_topic_title(topic.get("topic", ""))
        for topic in candidate_pool
        if isinstance(topic, dict)
    }
    for default_topic in default_candidate_pool:
        title_key = normalize_topic_title(default_topic["topic"])
        if title_key not in known_candidate_titles:
            candidate_pool.append(dict(default_topic))
            known_candidate_titles.add(title_key)

    published_history = get_published_topic_history(topic_db)
    published_titles = [item.get("title", "") for item in published_history]
    published_title_keys = {
        normalize_topic_title(title) for title in published_titles if title
    }

    available_topics = []
    rejected_similar_topics = []
    for topic in candidate_pool:
        if topic.get("status") != "candidate":
            continue

        candidate_title = topic.get("topic", "")
        if normalize_topic_title(candidate_title) in published_title_keys:
            rejected_similar_topics.append((candidate_title, "exact"))
            continue

        highest_similarity = max(
            (topic_similarity(candidate_title, title) for title in published_titles),
            default=0.0,
        )
        if highest_similarity >= 0.72:
            rejected_similar_topics.append((candidate_title, f"{highest_similarity:.2f}"))
            continue

        available_topics.append(topic)

    if not available_topics:
        detail = ", ".join(title for title, _ in rejected_similar_topics[:3])
        raise RuntimeError(
            "중복·유사 주제를 제외한 사용 가능한 후보가 없습니다. "
            "candidate_pool에 새 주제를 추가해야 합니다."
            + (f" 제외 예시: {detail}" if detail else "")
        )

    print(
        "주제 선정 점검: "
        f"후보 {len(candidate_pool)}개, 실제 발행 이력 {len(published_history)}개, "
        f"중복·고유사도 제외 {len(rejected_similar_topics)}개, "
        f"선택 가능 {len(available_topics)}개"
    )

    recent_reports = published_history[-12:]
    recent_main_categories = [item.get("main_category", "") for item in recent_reports]
    recent_middle_categories = [item.get("mid_category", "") for item in recent_reports]

    def calculate_score(topic):
        score = float(topic.get("priority", 0))

        main_category = topic.get("main_category", "")
        middle_category = topic.get("mid_category", "")
        candidate_title = topic.get("topic", "")

        if main_category in recent_main_categories[-1:]:
            score -= 0.35
        elif main_category in recent_main_categories[-3:]:
            score -= 0.15

        if middle_category and middle_category in recent_middle_categories[-3:]:
            score -= 0.30

        recent_category_count = recent_main_categories.count(main_category)
        score -= min(recent_category_count * 0.04, 0.20)

        highest_similarity = max(
            (topic_similarity(candidate_title, title) for title in published_titles),
            default=0.0,
        )
        if highest_similarity >= 0.45:
            score -= 0.35
        elif highest_similarity >= 0.25:
            score -= 0.15

        return score

    selected_topic = max(available_topics, key=calculate_score)

    return selected_topic


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
        "quotation": {
            "kind": "expert_advice",
            "quote": "영상 번역은 말의 의미뿐 아니라 장면의 시간과 관객의 읽기 속도를 함께 설계해야 한다.",
            "attribution": "영상 번역 연구의 일반 원칙",
            "source_title": "영상 번역 개요 자료",
            "source_url": "https://example.com",
            "context": "화면의 시간 제약이 번역 선택에 미치는 영향을 설명한다."
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
    }
    palette_key = category_aliases.get(main_category, main_category)
    return palettes.get(palette_key, {
        "paper": "#fffdf8", "ink": "#1f1b16", "body": "#2b241d",
        "muted": "#665c52", "line": "#cbbba7", "line_soft": "#ded1c2",
        "accent": "#8a5a2b", "accent_dark": "#4d3018",
        "table_header": "#e7d9c5", "box_bg": "#f8f3ec",
        "box_bg_strong": "#f1e6d8", "screen_bg": "#f4f0e8",
    })


def render_html(report: dict, output_path: Path):
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("report.html.j2")
    palette = get_report_palette(report.get("category", {}).get("main", ""))
    html = template.render(report=report, palette=palette)

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
        item.get("main_category")
        for item in published_reports[-5:]
        if item.get("main_category")
    ]

    category_order = [
        "인문·철학",
        "자연사·생태",
        "역사·문화",
        "과학·공학",
        "경제·사회",
        "예술·미학",
        "생활기술·일상문화",
        "언어·문자",
    ]
    recent_category_set = set(recent_main_categories[-3:])
    topic_db["category_rotation"] = {
        "recent_main_categories": recent_main_categories,
        "next_priority": [
            category for category in category_order
            if category not in recent_category_set
        ],
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.get("date", ""),
                item.get("title", ""),
                item.get("main_category", ""),
                item.get("mid_category", ""),
                item.get("sub_category", ""),
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
            priority REAL,
            status TEXT
        )
    """)

    for item in topic_db.get("candidate_pool", []):
        cur.execute(
            """
            INSERT INTO candidates
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                item.get("topic", ""),
                item.get("main_category", ""),
                item.get("mid_category", ""),
                float(item.get("priority", 0)),
                item.get("status", "")
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
        "html_path": html_public_path,
        "pdf_path": pdf_public_path,
        "html_url": html_public_path,
        "pdf_url": pdf_public_path,
        "status": report.get("status", "published_mock")
    }

    reports.append(item)
    reports.sort(key=lambda x: x["date"], reverse=True)

    save_json(REPORTS_JSON_PATH, reports)
    save_json(LATEST_JSON_PATH, item)

    manifest = {
        "last_updated": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
        "reports": reports
    }

    save_json(MANIFEST_PATH, manifest)


def save_render_publish_report(report: dict, topic_db: dict, mode: str = "mock"):
    today = datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    report["date"] = today
    report["status"] = f"published_{mode}"

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


def run_mock():
    today = get_today_kst()

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
    )

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
        if matched_fragment or json_key_hits >= 3:
            reason = matched_fragment or f"JSON 필드 표식 {json_key_hits}개"
            leaked_instruction_text.append(f"{text_path} ({reason})")

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
        "kind", "quote", "attribution", "source_title", "source_url", "context"
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

    if quotation.get("kind") not in {"direct_quote", "expert_advice"}:
        raise ValueError("quotation.kind는 direct_quote 또는 expert_advice여야 합니다.")

    quotation_url = str(quotation.get("source_url", "")).strip()
    if not quotation_url.startswith(("https://", "http://")):
        raise ValueError("quotation.source_url은 확인 가능한 http(s) URL이어야 합니다.")

    source_urls = {
        str(source.get("url", "")).strip()
        for source in sources
        if isinstance(source, dict)
    }
    if quotation_url not in source_urls:
        raise ValueError("quotation.source_url과 동일한 URL이 sources에도 있어야 합니다.")


def run_api():
    from generate_report import generate_report

    today = get_today_kst()

    topic_db = load_json(TOPIC_DB_PATH, default={})
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
                f"{validation_feedback} / 전체 JSON을 한 번 다시 생성합니다."
            )
            continue

        save_render_publish_report(report, topic_db, mode="api")
        return

    raise RuntimeError("리포트 생성 시도 횟수를 소진했습니다.")


def main():
    parser = argparse.ArgumentParser()
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--mock", action="store_true", help="OpenAI API 없이 mock 리포트를 생성합니다.")
    mode_group.add_argument("--api", action="store_true", help="OpenAI API로 실제 리포트를 생성합니다.")

    args = parser.parse_args()

    if args.api:
        run_api()
    else:
        run_mock()


if __name__ == "__main__":
    main()




