# Report Writer Prompt - Global Knowledge Journal v1.8

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

## 2. 전체 구성

다음 구조를 따른다.

1. Cover metadata
2. Keywords
3. Abstract
4. 01 / CONTEXT
5. 02 / BEGINNER'S MAP
6. 핵심 용어
7. 그림 또는 흐름 설명
8. 03 / DEEP DIVE
9. 04 / CASE STUDY
10. 05 / CURRENT STATE
11. 06 / IMPLICATIONS
12. 07 / TAKEAWAYS
13. 08 / FURTHER READING
14. Sources

JSON 필드는 반드시 schema에 맞춰 작성한다.

---

## 3. 분량 기준

최종 PDF 기준 7~9페이지를 목표로 한다.

이를 위해 다음 분량을 지킨다.

- abstract: 3~5문장
- sections: 최소 9개 이상
- 01 / CONTEXT: 3~4문단
- 02 / BEGINNER'S MAP: 2~3문단
- 03 / DEEP DIVE: 반드시 03-1부터 03-5까지 하위 소항목을 만든다.
- 각 03-x 소항목은 별도의 section 객체로 작성한다.
- 04 / CASE STUDY: 4~5문단
- 05 / CURRENT STATE: 4~5문단
- 06 / IMPLICATIONS: 4~5문단
- tables: 최소 4개
- takeaways: 정확히 3개
- further_reading: 3~5개

sections 배열은 다음 예시처럼 구성한다.

- id: "01"
  label: "01 / CONTEXT"
- id: "02"
  label: "02 / BEGINNER'S MAP"
- id: "03"
  label: "03 / DEEP DIVE"
- id: "03-1"
  label: "03-1."
- id: "03-2"
  label: "03-2."
- id: "03-3"
  label: "03-3."
- id: "03-4"
  label: "03-4."
- id: "03-5"
  label: "03-5."
- id: "04"
  label: "04 / CASE STUDY"
- id: "05"
  label: "05 / CURRENT STATE"
- id: "06"
  label: "06 / IMPLICATIONS"

---

## 4. Keywords

keywords는 6~8개로 작성한다.

- 고유명사만 나열하지 않는다.
- 약어를 사용할 경우 가능한 한 풀어쓴 표현도 함께 고려한다.
- 리포트의 핵심 개념을 독자가 훑어볼 수 있게 한다.

---

## 5. Abstract

abstract는 다음 성격을 가진다.

- 단순 요약이 아니라, 이 주제를 왜 읽어야 하는지 보여준다.
- 첫 문장은 독자의 일상적 감각에서 시작한다.
- 마지막 문장은 리포트의 관점을 분명히 제시한다.
- 내부 프로젝트나 자동화 언급은 금지한다.

---

## 6. Sections 작성 규칙

각 section의 body는 문단 배열로 작성한다.

문단은 너무 짧은 한 문장 나열로 만들지 않는다. 각 문단은 2~4문장 정도로 작성한다.

03 / DEEP DIVE는 본격 해설 섹션이다. 반드시 다음처럼 작성한다.

- 03 / DEEP DIVE: 전체 질문을 여는 짧은 도입
- 03-1.: 첫 번째 원리 또는 역사
- 03-2.: 두 번째 구조 또는 변화
- 03-3.: 세 번째 사회적 효과
- 03-4.: 네 번째 쟁점 또는 기술적 기준
- 03-5.: 다섯 번째 현재/미래 문제

03-1부터 03-5까지는 각각 별도의 section 객체로 작성한다.

---

## 7. Tables 작성 규칙

tables는 최소 4개를 작성한다.

각 table은 placement_hint를 반드시 가진다.

권장 배치:

- table_1: placement_hint "03"
- table_2: placement_hint "04"
- table_3: placement_hint "05"
- table_4: placement_hint "08"

표 제목은 반드시 다음 형식으로 작성한다.

- "<표1> 주제와 관련된 비교"
- "<표2> 사례가 보여주는 특징"
- "<표3> 현재 쟁점"
- "<표4> 관련 도서·탐구 키워드·확장 주제"

표는 단순 장식이 아니라 본문 내용을 정리해야 한다.

표 caption은 표 아래에 들어갈 짧은 해석 문장으로 작성한다.

---

## 8. 핵심 용어

현재 schema에는 핵심 용어 전용 필드가 없다.

따라서 핵심 용어는 tables 중 하나로 작성하지 말고, 02 / BEGINNER'S MAP의 마지막 문단에서 4개 핵심 용어를 자연스럽게 설명한다.

단, 가능하면 다음과 같은 네 개 개념을 포함한다.

- 기본 개념
- 작동 원리
- 사회적 효과
- 현재 쟁점

추후 schema 확장 시 term_boxes 필드로 분리한다.

---

## 9. Takeaways

takeaways는 정확히 3개 객체로 작성한다.

각 객체의 title은 반드시 아래 셋 중 하나를 사용한다.

1. "핵심 정리"
2. "요약"
3. "한마디"

각 body는 1~3문장으로 작성한다.

- 핵심 정리: 주제의 본질을 한 문장으로 정리한다.
- 요약: 리포트 전체 내용을 압축한다.
- 한마디: 독자가 기억할 수 있는 문장으로 작성한다.

---

## 10. Further Reading

further_reading은 3~5개로 작성한다.

각 항목은 다음을 포함한다.

- title
- author
- reason

도서 제목은 실제 존재하는 책, 논문, 보고서, 키워드형 탐구 자료 중에서 주제와 관련 있는 것으로 작성한다.

정확한 출처를 확신할 수 없는 경우, 저자를 무리하게 지어내지 말고 넓은 탐구 키워드나 기관 자료를 사용한다.

---

## 11. Sources

sources는 리포트 작성에 참고한 출처 목록이다.

각 source는 다음을 포함한다.

- publisher
- title
- url
- used_for

출처는 본문 하단에 표시될 수 있으므로, 내부 프로젝트 정보는 절대 sources에 넣지 않는다.

---

## 12. 금지 항목

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

## 13. 스타일 기준

Global Knowledge Journal v1.8 스타일을 따른다.

문체:

- 전문적이지만 독자가 이해할 수 있게 쓴다.
- 단순 정보 나열보다 설명, 사례, 해석을 함께 제공한다.
- 각 섹션은 “왜 중요한가”를 드러내야 한다.
- 독자가 읽고 나서 다음 질문을 떠올릴 수 있게 쓴다.

형식:

- 섹션 라벨은 "01 / CONTEXT" 형식을 사용한다.
- 하위 소항목은 "03-1." 형식을 사용한다.
- 표 제목은 "<표1>" 형식을 사용한다.
- 07 / TAKEAWAYS는 세로 박스형으로 표시될 수 있게 title/body 구조를 지킨다.
- 08 / FURTHER READING은 도서명 또는 자료명을 먼저 쓰고, 저자와 추천 이유를 뒤에 둔다.

---

## 14. Style Guide Reference

아래 스타일 가이드를 참고하되, 문서 안에 스타일 가이드 자체를 요약하거나 언급하지 않는다.

{{ style_guide }}

---

## 15. Topic DB Reference

아래 주제 DB는 중복 회피와 맥락 참고용이다. 리포트 본문에는 절대 언급하지 않는다.

{{ topic_db }}