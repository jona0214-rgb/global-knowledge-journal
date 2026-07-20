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

GitHub Actions를 통해 매일 오전 6시 실행

## 결과물

reports/YYYY/MM/YYYY-MM-DD/