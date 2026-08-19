# Global Knowledge Journal

OpenAI API와 GitHub Actions를 이용해
매일 글로벌 지식 리포트를 자동 생성하는 프로젝트입니다.

## 주요 기능

- 주제 DB 기반 주제 선택
- taxonomy v2 기반 10개 대분류 순환 및 중·소분류 다양화
- OpenAI API 리포트 생성
- Markdown, HTML, PDF 출력
- 외부 저장소 업로드
- 리포트 목록 자동 갱신
- GitHub Actions 정기 실행

## 프로젝트 구조

프로젝트 폴더 구조 설명

## 로컬 실행 방법

1. Python 설치
2. 가상환경 생성
3. requirements 설치
4. 환경변수 설정
5. python -m src.main 실행

## 환경변수

- OPENAI_API_KEY
- OPENAI_MODEL
- OPENAI_TOPIC_MODEL (선택, 미설정 시 OPENAI_MODEL 사용)
- STORAGE_BUCKET
- DATABASE_URL

## 자동 실행

GitHub Actions가 매일 오전 6시 15분(Asia/Seoul)에 API 리포트를 생성합니다.
예약 실행은 항상 `api` 모드이며, 수동 실행에서는 `mock` 또는 `api`를 선택할 수 있습니다.
같은 날짜에 정식 리포트가 이미 있으면 예약 재실행은 생성과 API 호출을 건너뜁니다.
검증을 통과한 API 리포트만 결과 파일과 공개 카탈로그에 반영됩니다.

## 주제 선정 정책

대분류는 아래 10개를 고정 순서로 순환합니다.

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

현재 순번의 대분류 안에서는 최근 사용하지 않은 중분류와 소분류를
우선하며, 이미 발행된 제목과 유사도가 높은 후보는 제외합니다.
순환 커서는 API 리포트가 검증과 PDF 생성을 모두 통과한 뒤에만 이동합니다.
해당 대분류의 후보가 고갈되면 API로 신규 후보를 보충하고 다시 검증하며,
유효한 후보를 확보하지 못하면 리포트를 발행하지 않습니다.

분류 정의와 기본 후보는 `config/topic_taxonomy_v2.json`에서 관리합니다.

공개 사이트: https://jona0214-rgb.github.io/global-knowledge-journal/

공개 사이트의 아카이브에서는 taxonomy v2 대분류와 발행 월을 함께 선택하고,
최신순 또는 오래된순으로 정렬할 수 있습니다. 선택한 조건은 URL 쿼리에
반영되어 필터 결과를 그대로 공유할 수 있습니다.

## 결과물

- `outputs/`: 발행된 JSON, HTML, PDF
- `public/latest.json`: 최신 리포트 정보
- `public/reports.json`: 날짜별 공개 리포트 목록
