# Report Writer Prompt - Global Knowledge Journal v1.8 Extended

오늘의 Global Knowledge Journal 리포트를 작성하라.

이 리포트는 독자가 읽는 공개 지식 콘텐츠다. 내부 프로젝트 운영 정보, 자동화 상태, GitHub Actions, mock 실행, API 실행, topic_db, candidate_pool, 주제 DB 반영 내용은 절대 포함하지 않는다.

---

## 1. 작성 대상

아래 선정 주제를 기준으로만 작성한다.

{{ selected_topic }}

오늘 날짜:

{{ today }}

중요 규칙:

- 새로운 주제를 고르지 않는다.
- 선정 주제를 다른 주제로 바꾸지 않는다.
- report.title은 선정 주제의 topic 문자열과 정확히 같아야 한다.
- report.category는 선정 주제의 main_category, mid_category, sub_category를 따른다.
- 제목은 고정하되 subtitle은 독자가 이해하기 쉬운 설명으로 작성한다.

---

## 2. 전체 구성 목표

최종 PDF는 Global Knowledge Journal v1.8 스타일을 따른다.

목표 흐름은 다음과 같다.

1. Cover metadata
2. Keywords
3. Abstract
4. summary_note
5. 01 / CONTEXT
6. 02 / BEGINNER'S MAP
7. term_box
8. flow_diagram
9. 03 / DEEP DIVE
10. 03-1. ~ 03-5.
11. <표1>
12. 04 / CASE STUDY
13. section_note
14. <표2>
15. 05 / CURRENT STATE
16. <표3>
17. 06 / IMPLICATIONS
18. 07 / TAKEAWAYS
19. 08 / FURTHER READING
20. <표4>
21. Sources

JSON 필드는 반드시 schema에 맞춰 작성한다.

---

## 3. 분량 기준

최종 PDF 기준 7~9페이지를 목표로 한다.

분량 기준:

- abstract: 3~5문장
- summary_note: 1~2문장 + 짧은 caption
- sections: 최소 11개 이상
- 01 / CONTEXT: 3~4문단
- 02 / BEGINNER'S MAP: 2~3문단
- 03 / DEEP DIVE: 반드시 03, 03-1, 03-2, 03-3, 03-4, 03-5로 구성
- 각 03-x 소항목: 2~3문단
- 04 / CASE STUDY: 4~5문단
- 05 / CURRENT STATE: 4~5문단
- 06 / IMPLICATIONS: 4~5문단
- term_box: 정확히 4개 용어
- flow_diagram: 4~6개 단계
- tables: 최소 4개
- section_notes: 최소 1개, 권장 2개
- takeaways: 정확히 3개
- further_reading: 3~5개
- sources: 5~8개

---

## 4. Cover metadata

다음 필드를 반드시 채운다.

- date
- title
- title_slug
- subtitle
- difficulty
- estimated_reading_time
- category
- keywords

title_slug는 영문 소문자, 숫자, 밑줄만 사용한다.

예: title_slug는 history_of_refrigerator 형식으로 작성한다.

keywords는 6~8개로 작성한다.

- 고유명사만 나열하지 않는다.
- 주제의 핵심 개념, 기술, 사회적 의미를 함께 포함한다.
- 약어를 사용할 경우 가능하면 풀어쓴 표현을 우선한다.

---

## 5. Abstract

abstract는 단순 요약이 아니라, 이 주제를 왜 읽어야 하는지 보여준다.

작성 방식:

- 첫 문장은 독자의 일상적 감각에서 시작한다.
- 중간 문장은 주제의 역사, 구조, 사회적 의미를 연결한다.
- 마지막 문장은 리포트의 관점을 분명히 제시한다.
- 내부 프로젝트나 자동화 언급은 금지한다.

---

## 6. summary_note

summary_note는 Abstract 아래에 들어가는 보조 코멘트 박스다.

필수 구성:

- body: 리포트의 핵심 관점을 1~2문장으로 쓴다.
- caption: 짧은 보조 설명을 쓴다.

예시 표현:

- body: 이 주제를 한 문장으로 꿰뚫는 관점
- caption: - 주요 개념, 사례, 현재 쟁점을 바탕으로 정리

caption 예시:

- - 역사적 사례와 현재 쟁점을 바탕으로 정리
- - 핵심 개념과 사회적 영향을 중심으로 정리

---

## 7. Sections 작성 규칙

sections 배열은 다음 구조를 반드시 포함한다.

- 01
- 02
- 03
- 03-1
- 03-2
- 03-3
- 03-4
- 03-5
- 04
- 05
- 06

각 section은 다음 필드를 가진다.

- id
- label
- title
- body

label 규칙:

- 01 / CONTEXT
- 02 / BEGINNER'S MAP
- 03 / DEEP DIVE
- 03-1.
- 03-2.
- 03-3.
- 03-4.
- 03-5.
- 04 / CASE STUDY
- 05 / CURRENT STATE
- 06 / IMPLICATIONS

03-1부터 03-5까지는 각각 별도의 section 객체로 작성한다.

03-1~03-5의 title은 짧고 구체적으로 작성한다.

좋은 예:

- 03-1. 얼음 상자에서 전기 냉장고로
- 03-2. 장보기의 주기가 바뀌다
- 03-3. 남은 음식의 의미가 바뀌다

나쁜 예:

- 03-1.
- 역사적 발전과 사회적 변화

---

## 8. term_box

term_box는 02 / BEGINNER'S MAP 뒤에 들어가는 핵심 용어 박스다.

정확히 4개 용어를 작성한다.

필수 구성:

- title: 핵심 용어
- items: 4개 용어 목록
- 각 item은 term과 description을 가진다.

용어 선정 기준:

1. 기본 개념
2. 작동 원리
3. 사회적 효과
4. 현재 쟁점

각 description은 1~2문장으로 작성한다.

---

## 9. flow_diagram

flow_diagram은 02와 03 사이에 들어가는 흐름도다.

필수 구성:

- title: <그림1>으로 시작하는 흐름도 제목
- steps: 4~6개 단계
- caption: 흐름도 아래 설명

steps는 짧은 명사구로 쓴다.

좋은 예:

생활하수 발생 → 관로 수집 → 처리장 이동 → 정화 처리 → 방류/재이용

caption은 이 흐름이 왜 중요한지 한 문장으로 설명한다.

---

## 10. Tables 작성 규칙

tables는 최소 4개를 작성한다.

각 table은 placement_hint를 반드시 가진다.

권장 배치:

- table_1: placement_hint는 03
- table_2: placement_hint는 04
- table_3: placement_hint는 05
- table_4: placement_hint는 08

표 제목은 반드시 다음 형식으로 작성한다.

- <표1> 주제와 관련된 비교
- <표2> 사례가 보여주는 특징
- <표3> 현재 쟁점
- <표4> 관련 도서·탐구 키워드·확장 주제

표 caption은 표 아래에 들어갈 짧은 해석 문장으로 작성한다.

표4는 Further Reading 표다. 다음 행을 포함한다.

- 관련 도서
- 탐구 키워드
- 관련 주제

---

## 11. section_notes

section_notes는 특정 섹션 뒤에 들어가는 보조 코멘트 박스다.

최소 1개, 권장 2개 작성한다.

권장 placement_hint:

- 04
- 06

필수 구성:

- placement_hint: 노트가 들어갈 섹션 ID
- body: 사례나 함의의 핵심 의미를 요약하는 1~2문장
- caption: 짧은 보조 설명

예시:

- placement_hint: 04
- body: 사례의 핵심 의미를 요약하는 문장
- caption: - 사례 분석을 바탕으로 정리

---

## 12. Takeaways

takeaways는 정확히 3개 객체로 작성한다.

각 title은 반드시 아래 셋 중 하나를 사용한다.

1. 핵심 정리
2. 요약
3. 한마디

각 body는 1~3문장으로 작성한다.

- 핵심 정리: 주제의 본질을 한 문장으로 정리한다.
- 요약: 리포트 전체 내용을 압축한다.
- 한마디: 독자가 기억할 수 있는 문장으로 작성한다.

---

## 13. Further Reading

further_reading은 3~5개로 작성한다.

각 항목은 다음을 포함한다.

- title
- author
- reason

주의:

- Further Reading 목록은 보조 정보다.
- 최종 PDF에서는 <표4>가 중심이 되므로, further_reading은 과하게 길게 쓰지 않는다.
- 정확한 도서명과 저자를 확신할 수 없으면 기관 보고서, 논문, 탐구 키워드 중심으로 작성한다.
- 도서명을 지어내지 않는다.

---

## 14. Sources

sources는 리포트 작성에 참고한 출처 목록이다.

각 source는 다음을 포함한다.

- publisher
- title
- url
- used_for

주의:

- 출처는 5~8개 이내로 작성한다.
- URL은 가능한 한 실제 기관 또는 문서 URL을 사용한다.
- 내부 프로젝트 정보는 절대 sources에 넣지 않는다.
- Sources가 PDF에서 너무 길어지지 않게 used_for는 짧게 작성한다.

---

## 15. 금지 항목

다음 표현과 내용은 어떤 필드에도 넣지 않는다.

- PROJECT DB
- 주제 DB 반영
- 주제 DB 확장 메모
- 다음 회차 후보
- 후보 우선순위
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
- 내부 진행 메모

---

## 16. 문체

- 전문적이지만 독자가 이해할 수 있게 쓴다.
- 단순 정보 나열보다 설명, 사례, 해석을 함께 제공한다.
- 각 섹션은 “왜 중요한가”를 드러내야 한다.
- 독자가 읽고 나서 다음 질문을 떠올릴 수 있게 쓴다.
- 문단은 너무 짧은 한 문장 나열로 만들지 않는다.
- 각 문단은 2~4문장 정도로 작성한다.

---

## 17. Style Guide Reference

아래 스타일 가이드를 참고하되, 문서 안에 스타일 가이드 자체를 요약하거나 언급하지 않는다.

{{ style_guide }}

---

## 18. Topic DB Reference

아래 주제 DB는 중복 회피와 맥락 참고용이다. 리포트 본문에는 절대 언급하지 않는다.

{{ topic_db }}
