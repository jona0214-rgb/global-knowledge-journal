# Global Knowledge Journal

OpenAI API와 GitHub Actions를 이용해 한국어 지식 리포트를 생성·검증하고,
HTML/PDF와 공개 카탈로그를 GitHub Pages에 게시하는 프로젝트입니다.

## 주요 기능

- taxonomy v2의 10개 대분류 순환과 중·소분류 다양화
- OpenAI Responses API 기반 구조화 리포트 생성
- 필수 섹션·분량·출처·시스템 문구 유출 검증
- HTML 및 6~9쪽 PDF 렌더링
- 실패 재생성, 누락 날짜 백필, 스테이징 후 예약 공개
- 월별·대분류별 공개 아카이브와 자동화 로그
- 지식 지도용 버전드 taxonomy·리포트·계층 그래프 데이터 생성

## 활성 구조

```text
.github/workflows/
  ci.yml                    코드와 데이터 검증
  daily-report.yml          00:00 생성, 03:15 누락 복구
  publish-report.yml        07:00 스테이징 결과 공개

config/
  topic_taxonomy_v2.json    대분류와 기본 주제의 단일 원본
  taxonomy_aliases.json     구형 분류명 변환 규칙

scripts/
  run_daily_report.py       호환 CLI 및 파이프라인 조정
  generate_report.py        OpenAI 요청·응답 정규화
  record_publication.py     공개 시각 기록
  verify_published_site.py  GitHub Pages 최종 확인
  build_knowledge_graph.py  공개 API와 계층 그래프 생성
  audit_project.py          운영 데이터 일관성 감사
  report_pipeline/          저장·분류·카탈로그·그래프 공통 모듈

public/
  reports.json              기존 공개 카탈로그 호환본
  latest.json               기존 최신 리포트 호환본
  api/v1/                   홈페이지와 지식 지도의 버전드 데이터

outputs/                    발행 JSON·HTML·PDF
tests/                      Python 및 브라우저 없는 JavaScript 테스트
```

초기 프로토타입의 미사용 `src/`와 빈 placeholder 파일은 제거했습니다. 신규 코드는
`scripts/report_pipeline/`에 추가하고 `scripts/run_daily_report.py`는 CLI 조정 계층으로
점차 축소합니다.

## 로컬 실행

Python 3.12 환경에서 다음 순서로 실행합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium
```

레이아웃 검증용 mock은 공개 카탈로그와 주제 DB를 변경하지 않습니다.

```powershell
python scripts/run_daily_report.py --mock
```

실제 API 생성은 로컬 `.env` 또는 GitHub Actions Secret의 `OPENAI_API_KEY`를 사용합니다.

```powershell
python scripts/run_daily_report.py --api
python scripts/run_daily_report.py --api --date 2026-10-02
```

API 키를 소스, 로그, 명령행 인자에 기록하지 않습니다.

## 검증 명령

```powershell
python -m py_compile scripts/run_daily_report.py scripts/generate_report.py
python -m unittest discover -s tests -p "test_*.py"
node tests/test_homepage_filters.mjs
node tests/test_logs_page.mjs
python scripts/audit_project.py
python scripts/build_knowledge_graph.py --check
```

PR과 `main`, `codex/**` 브랜치 push에서는 `.github/workflows/ci.yml`이 같은 검증을
자동 수행합니다.

## 자동 생성과 공개

- 23:45 KST에 runner를 요청하고 00:00 KST부터 1차 생성을 시작합니다.
- 03:15 KST에 최근 3일 중 가장 오래된 미발행 날짜를 다시 확인하고 복구합니다.
- 검증을 통과한 예약 리포트는 `report-staging` 브랜치에 저장합니다.
- 별도 공개 workflow가 06:45 KST에 시작해 07:00 KST 이후 `main`으로 승격합니다.
- Pages에서 카탈로그와 PDF가 실제로 보이지 않으면 공개 workflow가 실패합니다.
- 수동 API 실행은 실행한 브랜치에 반영되며, mock은 artifact만 업로드합니다.

GitHub 예약 실행 자체가 지연되면 목표 시각보다 늦게 실행될 수 있습니다. 생성·스테이징·
공개 시각은 홈페이지의 `자동화 로그 보기`에서 확인합니다.

## 주제 선정 정책

대분류는 다음 순서로 순환합니다.

1. 인문·철학
2. 사회·정치·법
3. 경제·경영
4. 과학·수학
5. 기술·공학
6. 생명·건강
7. 자연·환경·지리
8. 역사·문화
9. 예술·디자인
10. 언어·미디어·지식

현재 순번 안에서 최근 사용하지 않은 중·소분류를 우선하고, 발행 제목과 유사도가 높은
후보를 제외합니다. 후보가 소진되면 API로 해당 대분류의 신규 후보를 보충합니다.

분류 원본은 `config/topic_taxonomy_v2.json`, 구형 값 변환은
`config/taxonomy_aliases.json`에서만 관리합니다.

## 지식 지도 데이터

`python scripts/build_knowledge_graph.py`는 다음 파일을 생성합니다.

- `public/api/v1/taxonomy.json`
- `public/api/v1/reports.json`
- `public/api/v1/knowledge-graph.json`

현재 그래프는 대분류→중분류→소분류→세부분류→리포트의 재현 가능한 계층 연결만
생성합니다. 교차 주제 연결은 `data/knowledge_edge_overrides.json`에 근거와 설명을 가진
검수된 관계만 추가할 수 있습니다. 향후 의미 유사도 계산도 동일한 그래프 스키마에
연결하되, 근거 없는 모델 연결은 공개하지 않습니다.

## 환경변수

- `OPENAI_API_KEY`: 필수, 저장소에 커밋하지 않음
- `OPENAI_MODEL`: 기본 `gpt-4.1-mini`
- `OPENAI_TOPIC_MODEL`: 주제 후보 생성 모델, 미설정 시 `OPENAI_MODEL`
- `OPENAI_MAX_OUTPUT_TOKENS`: 기본 24000
- `OPENAI_TIMEOUT_SECONDS`: API 요청 제한시간
- `REPORT_VALIDATION_RETRIES`: 구조 검증 후 전체 재생성 횟수
- `REPORT_RECOVER_MISSING_DAYS`: 예약 실행의 누락일 탐색 범위

공개 사이트: https://jona0214-rgb.github.io/global-knowledge-journal/
