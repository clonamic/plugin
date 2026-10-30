---
name: fde-closing
description: FDE-Mode closing and retrospective (P6/P7) — feature freeze, final QA sweep, demo scenario, final release and report, the human submission checklist, then the retrospective and archiving. Use only while FDE-Mode is on and the closing or retro run is active.
user-invocable: false
---

# 마감과 회고 (P6, P7)

## 1. 마감 모드로 들어가는 때

바인딩 `[schedule] feature_freeze` 시각이 지나면 `CLOSING` 실행이 저절로 생기고 단계가 P6가 된다. 이때부터:
- **새 기능 금지.** 새 요구는 변경 통제에서 거절을 권고한다.
- 진행 중인 조각은 끝까지 가되, 시간 예산 관리자가 위험하다고 하면 마지막 정상 태그로 고정할지 D1로 묻는다.

## 2. 마감 흐름

1. 최종 QA 7석(시나리오, 가상 사용자, 응답 시간, 표시 형식, 맞춤 적합성, UX, AI티). 핵심 동결 없이 기능 동결 시각이 와도 마감은 시작된다 — 그때는 지금 배포돼 있는 것이 제출본이다.
2. QA 본부장 최종 판정 + 데모 시나리오 작가가 심사용 대화 흐름을 확정(`docs/demo-scenario.md`).
3. 릴리스 관리자 최종 태그 + 서기장 최종 보고서(`docs/final-report.md`: 무엇을 왜 만들었나, 개인화 표, 가정, 기술 결정, 남은 위험).
4. **사람이 할 일**: 바인딩 `[submission] checklist`를 체크리스트로 보여 준다(예: 실제 봇으로 마지막 실기 확인, 채널 URL·봇 정보 제출, 상태 문서 갱신). 제출은 사용자가 직접 한다.
5. 프로젝트에 상태 문서 동기화 스킬이 있으면(예: 대회 프로젝트의 `sync-status`) 사용자에게 실행을 권한다.

## 3. 회고 (P7)

- 제출 뒤 `fde run retro` → 회고 분석가가 교훈을 증거와 함께 `docs/retro.md`에 쓰고, 다음 프로젝트에 쓸 교훈을 `~/.clonamic/fde-mode/lessons.md`에 덧붙인다(인터뷰 품질, 억지 질문 비율, 시간 배분, 플러그인에서 바꿀 것).
- 회고가 끝나면 사용자에게 모드를 끌지 묻는다(D3에 가까우나 사용자의 명시적 동의로 끈다): `fde off`.
- 다음 대회·프로젝트를 위해 작업 기록을 보관하려면 `fde archive`(지우지 않고 `archive/<시각>/`으로 옮김).

## 4. 하지 않는 것

- 서버·인프라 철거(`make down` 같은 것). 대회 서버는 대회 뒤에도 일정 기간 유지해야 할 수 있다. 철거는 사람이 정해진 날에 직접 한다.
