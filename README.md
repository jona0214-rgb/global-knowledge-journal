# Global Knowledge Journal

OpenAI API와 GitHub Actions를 이용해
매일 글로벌 지식 리포트를 자동 생성하는 프로젝트입니다.

## 주요 기능

- 주제 DB 기반 주제 선택
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
- STORAGE_BUCKET
- DATABASE_URL

## 자동 실행

GitHub Actions가 매일 오전 6시 15분(Asia/Seoul)에 API 리포트를 생성합니다.
예약 실행은 항상 `api` 모드이며, 수동 실행에서는 `mock` 또는 `api`를 선택할 수 있습니다.
같은 날짜에 정식 리포트가 이미 있으면 예약 재실행은 생성과 API 호출을 건너뜁니다.
검증을 통과한 API 리포트만 결과 파일과 공개 카탈로그에 반영됩니다.

공개 사이트: https://jona0214-rgb.github.io/global-knowledge-journal/

## 결과물

- `outputs/`: 발행된 JSON, HTML, PDF
- `public/latest.json`: 최신 리포트 정보
- `public/reports.json`: 날짜별 공개 리포트 목록
