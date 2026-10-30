---
name: fde-rehearsal
description: FDE-Mode rehearsal — a full dry run with a mock persona whose hidden requirements are sealed, to measure round times, question quality, forced-question rate and timeline before the real event, then tune switches and thresholds. Use only after /fde-mode rehearsal.
user-invocable: false
---

# 리허설 (가짜 인물로 처음부터 끝까지)

설계만 하고 한 번도 끝까지 돌려 보지 않으면 시간표, 결정 등급, 동결 기준이 전부 추측이다. 리허설은 그 추측을 숫자로 바꾼다.

## 1. 준비

1. 실전 프로젝트에서 해도 된다. 다만 코드가 바뀌므로 **브랜치를 따로 만든다**: 사용자에게 `git switch -c fde-rehearsal` 를 권하고(디렉터가 실행해도 된다), 리허설 뒤 `git switch main`과 실전용 재배포를 체크리스트에 넣는다.
2. `fde on --rehearsal` → `fde run rehearsal --theme "<주제>"` → `fde next`로 가짜 인물 생성.
3. 가짜 인물이 만드는 파일:
   - `rehearsal/sealed/persona-secret.md`, `sealed/hidden-requirements.json`, `sealed/roleplay-prompt.md` — **봉인**. 조직의 어떤 분석 에이전트도 읽지 못한다(가드). 디렉터도 읽지 않는다.
   - `rehearsal/public-brief.md` — 참가자가 처음 아는 정보(문제 설명).
4. 사용자는 인물 역할 지시문을 **읽지 않고** 복사해 **다른 채팅**에 붙인다 — 열어 보면 숨은 요구사항을 알게 돼 리허설이 무의미해진다. 사용자 자신의 터미널(이 세션 밖)에서 `pbcopy < <프로젝트>/.claude/fde-mode/rehearsal/sealed/roleplay-prompt.md` 를 실행하면 화면에 내용이 나오지 않는다(디렉터는 이 명령을 대신 실행하지 않는다 — 가드가 봉인 경로를 막는다). `public-brief.md`는 이 세션에 `>>brief`로 붙인다.

## 2. 진행

실전과 똑같이: 브리프 → 인터뷰 붙여넣기 → 빠른 라운드·토론 라운드 → 기술 게이트 → 동결 → 구현 → 배포 → QA → 마감. 실제 시간표(바인딩 `[schedule]`)를 리허설 날짜로 바꿔 두면 시간 경고도 실전처럼 나온다.

## 3. 잴 것

| 지표 | 어디서 |
|---|---|
| 빠른 라운드 소요 시간 | 이벤트 기록(run.created → run.done) |
| 토론 라운드 소요 시간 | 같음 |
| 라운드당 D1 개수 | 결정 큐 |
| 질문 카드 중 억지 비율(사람이 보기에) | 사용자가 "억지"라고 버린 카드 수 / 전체 |
| 이미 답한 것을 다시 묻는 횟수 | 검증관 already_answered, 사용자 지적 |
| 숨은 요구사항 발견률 | 채점관(봉인 해제 후) |
| 메인 세션 압축 발생 | 이벤트(pre-compact) |
| 배포 한 번 걸리는 시간 | 배포 담당 출력 |

## 4. 채점과 조정

1. `/fde-mode rehearsal grade` → `fde run rehearsal-grade`(이때만 봉인이 풀린다) → 리허설 채점관이 `rehearsal/grade.md`를 쓴다.
2. 결과로 조정할 것: 빠른 라운드 구성(스위치), `debate_every`, `min_rounds_before_freeze`, `top_cards`, 시간표, D1 기준, 너무 느린 본부 끄기.
3. 플러그인 자체를 고쳐야 하면(에이전트 프롬프트, 규칙) 그 내용을 플러그인 저장소 `Docs/`의 할 일 목록에 남긴다.
4. `/fde-mode rehearsal end` → `fde archive`로 리허설 기록을 보관하고 실전 상태로 되돌린다. 브랜치를 main으로 돌리고 실전 코드로 재배포했는지 확인한다.
