import argparse
from html import escape
import json
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
    ]

    candidate_pool = topic_db.get("candidate_pool", [])

    available_topics = [
        topic for topic in candidate_pool
        if topic.get("status") == "candidate"
    ]

    if not available_topics:
        topic_db["candidate_pool"] = [
            dict(topic) for topic in default_candidate_pool
        ]

        candidate_pool = topic_db["candidate_pool"]

        available_topics = [
            topic for topic in candidate_pool
            if topic.get("status") == "candidate"
        ]

        print("후보 주제가 없어 기본 후보 주제를 다시 채웠습니다.")

    if not available_topics:
        raise RuntimeError("사용 가능한 후보 주제가 없습니다.")

    category_rotation = topic_db.get("category_rotation", {})
    recent_main_categories = category_rotation.get("recent_main_categories", [])
    next_priority_categories = category_rotation.get("next_priority", [])

    def calculate_score(topic):
        score = float(topic.get("priority", 0))

        main_category = topic.get("main_category", "")

        if main_category in next_priority_categories:
            score += 0.20

        if main_category in recent_main_categories[-1:]:
            score -= 0.30
        elif main_category in recent_main_categories[-3:]:
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
            "main": topic.get("main_category", "언어·문자"),
            "middle": topic.get("mid_category", "영상번역"),
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
            "이 mock 리포트는 자동화 파이프라인을 검증하기 위한 샘플이며, 실제 API 연결 후에는 최신 출처 기반 본문으로 교체된다."
        ),
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
                "publisher": "Mock Source",
                "title": "This is a mock source for local pipeline testing",
                "url": "https://example.com",
                "used_for": "로컬 테스트용 더미 출처"
            }
        ]
    }


def render_html(report: dict, output_path: Path):
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("report.html.j2")
    html = template.render(report=report)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def render_pdf_with_playwright(html_path: Path, pdf_path: Path, report: dict):
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    date_text = escape(str(report.get("date", "")).replace("-", "."))
    category = report.get("category", {})
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
        'color:#665c52;font-family:Arial,\'Malgun Gothic\',sans-serif;font-size:9px;">'
        '<div style="position:absolute;left:1mm;right:1mm;bottom:270mm;'
        'padding-bottom:6px;border-bottom:1px solid #cbbba7;font-weight:700;'
        'line-height:1.2;display:flex;justify-content:space-between;gap:18px;">'
        f'<span>GLOBAL KNOWLEDGE JOURNAL / {date_text}</span>'
        f'<span>{category_text}</span></div>'
        '<div style="padding-top:6px;border-top:1px solid #cbbba7;'
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

    already_exists = any(item.get("date") == today for item in recent_reports)

    if not already_exists:
        recent_reports.append({
            "date": today,
            "title": report["title"],
            "main_category": report["category"]["main"],
            "mid_category": report["category"]["middle"],
            "sub_category": report["category"]["sub"],
            "keywords": report["keywords"],
            "html_path": str(html_path.as_posix()),
            "pdf_path": str(pdf_path.as_posix()),
            "status": "published_mock"
        })

    topic_db["updated_at"] = today

    recent_main_categories = [
        item.get("main_category")
        for item in recent_reports[-5:]
        if item.get("main_category")
    ]

    topic_db["category_rotation"] = {
        "recent_main_categories": recent_main_categories,
        "next_priority": [
            "인문·철학",
            "자연사·생태",
            "역사·문화",
            "과학·공학",
            "경제·사회",
            "예술·미학",
            "생활기술·일상문화",
            "언어·문자"
        ]
    }

    for candidate in topic_db.get("candidate_pool", []):
        if candidate.get("topic", "").startswith(report["title"]):
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

    update_topic_db(topic_db, report, html_path, pdf_path)
    rebuild_sqlite(topic_db)
    update_public_catalog(report, html_path, pdf_path)

    print("생성 완료")
    print(f"리포트 JSON: {report_json_path}")
    print(f"HTML: {html_path}")
    print(f"PDF: {pdf_path}")
    print(f"주제 DB JSON: {TOPIC_DB_PATH}")
    print(f"주제 DB SQLite: {TOPIC_DB_SQLITE_PATH}")
    print(f"공개 목록: {REPORTS_JSON_PATH}")
    print(f"최신 리포트: {LATEST_JSON_PATH}")


def run_mock():
    today = get_today_kst()

    topic_db = load_json(TOPIC_DB_PATH, default={})
    topic = select_topic(topic_db)

    report = create_mock_report(today, topic)

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


def run_api():
    from generate_report import generate_report

    today = get_today_kst()

    topic_db = load_json(TOPIC_DB_PATH, default={})
    topic = select_topic(topic_db)

    print("OpenAI API로 리포트를 생성합니다.")
    print(f"선정 주제: {topic.get('topic')}")

    report = generate_report(today=today, selected_topic=topic)
    report = enforce_selected_topic(report, topic)
    validate_report_structure(report)

    save_render_publish_report(report, topic_db, mode="api")


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

