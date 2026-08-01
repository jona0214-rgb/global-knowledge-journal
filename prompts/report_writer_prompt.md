# Report Writer Prompt - Global Knowledge Journal v1.9 Length Reinforced

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
- 03, 04, 05, 06 섹션은 절대 생략하지 않는다.
- 표와 노트는 본문을 대체하지 않는다. 표는 반드시 본문 뒤의 보조 정리로만 사용한다.

---

## 2. 전체 구성 목표

최종 PDF는 Global Knowledge Journal v1.8의 저널형 구성을 따르되, 본문 분량은 7~9페이지가 되도록 충분히 작성한다.

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
18. section_note
19. 07 / TAKEAWAYS
20. 08 / FURTHER READING
21. <표4>
22. Sources

JSON 필드는 반드시 schema에 맞춰 작성한다.

---

## 3. 절대 분량 기준

아래 기준은 권장이 아니라 필수다.

전체 목표:

- 최종 PDF 기준 7~9페이지
- sections의 body에 들어가는 한국어 본문은 공백 포함 최소 6,500자 이상이어야 한다. 권장이 아니라 필수다.
- sections의 body 문단 총합은 최소 36문단 이상이어야 한다.
- 각 body 문단은 공백 포함 최소 160자여야 하며, 160자 미만 문단은 요구 문단 수에 포함되지 않는다.
- 빈 문자열, 공백만 있는 문자열, 문단이 아닌 값은 문단 수로 인정되지 않는다.
- 표, 핵심 용어, 흐름도, Sources는 본문 분량에 포함하지 않는다.
- 짧은 요약형 리포트로 끝내지 않는다.

필수 섹션별 문단 수:

- 01 / CONTEXT: 정확히 4문단
- 02 / BEGINNER'S MAP: 정확히 3문단
- 03 / DEEP DIVE: 정확히 2문단
- 03-1.: 정확히 3문단
- 03-2.: 정확히 3문단
- 03-3.: 정확히 3문단
- 03-4.: 정확히 3문단
- 03-5.: 정확히 3문단
- 04 / CASE STUDY: 정확히 5문단
- 05 / CURRENT STATE: 정확히 5문단
- 06 / IMPLICATIONS: 정확히 5문단

문단 기준:

- 각 문단은 2~4문장으로 작성한다.
- 각 문단은 공백 포함 최소 160자로 작성하되, 180~220자 수준의 충분한 설명을 목표로 한다.
- 한 문장짜리 짧은 문단을 반복하지 않는다.
- 각 문단은 최소한 원인, 과정, 결과, 사례, 함의 중 하나를 설명해야 한다.
- 단순 정의만 나열하지 않는다.

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

estimated_reading_time은 7~9페이지 분량에 맞게 18-22분 범위로 작성한다.

keywords는 6~8개로 작성한다.

---

## 5. Abstract

abstract는 단순 요약이 아니라, 이 주제를 왜 읽어야 하는지 보여준다.

작성 방식:

- 4~5문장으로 작성한다.
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

---

## 7. Sections 작성 규칙

sections 배열은 다음 11개 id를 반드시 모두 포함한다.
각 id는 정확히 한 번만 사용하며, sections는 정확히 11개 객체로 작성한다.

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

절대로 3, 4, 5, 6처럼 앞자리 0을 생략하지 않는다.

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

---

## 8. 03 / DEEP DIVE 작성 규칙

03 / DEEP DIVE는 단순 표로 대체할 수 없다.

반드시 다음을 설명한다.

- 이 주제의 핵심 질문
- 다섯 개 하위 항목이 왜 필요한지
- 독자가 03-1부터 03-5를 어떤 순서로 읽어야 하는지

03-1부터 03-5는 다음 성격을 가진다.

- 03-1: 역사적 출발점 또는 기원
- 03-2: 구조, 작동 원리, 제도, 기술의 변화
- 03-3: 생활, 사회, 문화에 미친 영향
- 03-4: 기준, 규칙, 측정, 관리 방식의 변화
- 03-5: 현재 쟁점과 미래 과제

각 03-x는 정확히 3문단을 작성한다.

---

## 9. 04 / CASE STUDY 작성 규칙

04 / CASE STUDY는 구체적 사례를 깊게 설명한다.

반드시 다음을 포함한다.

- 사례가 등장한 배경
- 사례의 핵심 인물, 기관, 장소, 기술, 제도 중 관련 요소
- 사례가 당시 사회에서 어떤 문제를 해결했는지
- 사례가 남긴 변화
- 오늘날 이 사례를 다시 읽을 때의 의미

정확히 5문단으로 작성한다.

section_notes 중 하나는 placement_hint를 04로 지정하여 사례의 의미를 보조 코멘트 박스로 정리한다.

---

## 10. 05 / CURRENT STATE 작성 규칙

05 / CURRENT STATE는 현재 상황을 설명한다.

반드시 다음을 포함한다.

- 현재 이 주제가 작동하는 방식
- 기술적 또는 제도적 변화
- 사회적 쟁점
- 경제적, 환경적, 문화적 영향 중 관련 요소
- 가까운 미래의 변화 가능성

정확히 5문단으로 작성한다.

---

## 11. 06 / IMPLICATIONS 작성 규칙

06 / IMPLICATIONS는 단순 결론이 아니다.

반드시 다음을 포함한다.

- 개인 생활에 미치는 영향
- 사회 구조에 미치는 영향
- 기술 또는 제도에 미치는 영향
- 문화적 의미
- 앞으로의 질문

정확히 5문단으로 작성한다.

section_notes 중 하나는 placement_hint를 06으로 지정하여 전체 함의를 보조 코멘트 박스로 정리한다.

---

## 12. term_box

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

## 13. flow_diagram

flow_diagram은 02와 03 사이에 들어가는 흐름도다.

필수 구성:

- title: <그림1>으로 시작하는 흐름도 제목
- steps: 5개 단계 권장, 최소 4개, 최대 6개
- caption: 흐름도 아래 설명

steps는 짧은 명사구로 쓴다.

caption은 이 흐름이 왜 중요한지 한 문장으로 설명한다.

---

## 14. Tables 작성 규칙

tables는 정확히 4개를 작성한다.

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

표1, 표2, 표3은 각각 5행 이상으로 작성한다.

표4는 Further Reading 표다. 다음 행을 포함한다.

- 관련 도서
- 탐구 키워드
- 관련 주제

표 caption은 표 아래에 들어갈 짧은 해석 문장으로 작성한다.

---

## 15. section_notes

section_notes는 특정 섹션 뒤에 들어가는 보조 코멘트 박스다.

정확히 2개 작성한다.

placement_hint는 다음 두 개를 사용한다.

- 04
- 06

---

## 16. Takeaways

takeaways는 정확히 3개 객체로 작성한다.

각 title은 반드시 아래 셋 중 하나를 사용한다.

1. 핵심 정리
2. 요약
3. 한마디

각 body는 1~3문장으로 작성한다.

---

## 17. Further Reading

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

## 18. Sources

sources는 리포트 작성에 참고한 출처 목록이다.

각 source는 다음을 포함한다.

- publisher
- title
- url
- used_for

주의:

- 출처는 6~8개로 작성한다.
- URL은 가능한 한 실제 기관 또는 문서 URL을 사용한다.
- 내부 프로젝트 정보는 절대 sources에 넣지 않는다.
- Sources가 PDF에서 너무 길어지지 않게 used_for는 짧게 작성한다.

---

## 19. 금지 항목

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

## 20. 작성 전 최종 자기검사

응답 JSON을 제출하기 전에 스스로 다음을 확인한다.

- sections에 01, 02, 03, 03-1, 03-2, 03-3, 03-4, 03-5, 04, 05, 06이 모두 있는가
- 03, 04, 05, 06이 표로 대체되지 않았는가
- 01~06 본문 문단 총합이 최소 36문단 이상인가
- sections의 body 본문만 합쳐 공백 포함 최소 6,500자 이상인가
- 03-1부터 03-5까지 각각 3문단인가
- 04, 05, 06이 각각 5문단인가
- tables가 정확히 4개인가
- term_box.items가 정확히 4개인가
- flow_diagram.steps가 최소 4개인가
- takeaways가 정확히 3개인가
- section_notes가 정확히 2개인가
- sources가 최소 5개인가
- 전체 분량이 7~9페이지를 만들 만큼 충분한가

---

## 21. Style Guide Reference

아래 스타일 가이드를 참고하되, 문서 안에 스타일 가이드 자체를 요약하거나 언급하지 않는다.

{{ style_guide }}

---

## 22. Topic DB Reference

아래 주제 DB는 중복 회피와 맥락 참고용이다. 리포트 본문에는 절대 언급하지 않는다.

{{ topic_db }}
