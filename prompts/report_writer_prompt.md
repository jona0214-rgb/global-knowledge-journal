# Report Writer Prompt - Report-only v1.8 alignment

오늘의 Global Knowledge Journal 리포트를 생성하라.

리포트는 독자가 읽는 공개 지식 콘텐츠만 포함한다. 내부 프로젝트 운영 데이터는 PDF/HTML 리포트에 포함하지 않는다.

## 출력 구조

- 01 / CONTEXT
- 02 / BEGINNER'S MAP
- 03 / DEEP DIVE
- 04 / CASE STUDY
- 05 / CURRENT STATE
- 06 / IMPLICATIONS
- 07 / TAKEAWAYS
- 08 / FURTHER READING

## 분량

PDF 기준 7페이지 이상, 9페이지 이하를 목표로 한다. 7페이지 미만이면 개념 설명, 사례, 현재 쟁점, 비교 표, 시사점을 보강한다. 9페이지 초과 가능성이 있으면 반복 설명과 지나치게 긴 표를 줄인다.

## 금지 항목

다음 표현과 내용은 리포트 본문, 표, 박스, Takeaways, Further Reading, Sources에 포함하지 않는다.

- 주제 DB 반영과 다음 순환 방향
- 주제 DB 확장 메모
- PROJECT DB
- 주제 DB 적용 요약
- 다음 회차 후보 우선순위
- 운영 메모
- 반복 회피
- 다양성 확보
- candidate_pool
- topic_db
- topic_db.json
- topic_db.sqlite
- GitHub Actions
- mock 실행
- API 실행 상태
- 자동화 파이프라인 설명
- 프로젝트 내부 진행 메모

주제 다양성과 중복 방지 정보는 내부 DB에만 반영한다.

## 스타일

기존 Global Knowledge Journal Style Guide v1.8의 compact layout을 유지한다. 섹션 라벨은 `01 / CONTEXT` 형식을 사용하고, 표 제목은 `<표1>` 형식을 사용한다. 핵심 용어 박스에는 별도 박스 번호를 붙이지 않는다. 07 TAKEAWAYS는 세로로 나열한다. 관련 도서는 제목을 먼저 굵게 쓰고 저자를 뒤에 둔다.
