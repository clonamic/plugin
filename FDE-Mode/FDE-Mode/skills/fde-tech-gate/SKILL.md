---
name: fde-tech-gate
description: FDE-Mode technical decision gate (P2, runs alongside the interview) — how the director relays the tech committee's ADRs and asks the user's D1/D2 technology decisions so the stack is fixed before core freeze. Use only while FDE-Mode is on and a techgate run is active.
user-invocable: false
---

# 기술 결정 게이트 (P2)

기술 스택은 구현 도중이 아니라 **동결 전에** 확정한다. 그래야 구현 조직이 확정된 기술로만 움직인다. 게이트는 인터뷰와 동시에 열리고, 인터뷰를 멈추지 않는다.

## 1. 언제 열리나

- must 요구사항이 2라운드 연속 바뀌지 않고 대화 라운드가 3번 이상일 때, 또는 핵심 동결 30분 전(`TG1` 실행이 자동으로 생김).
- 사용자가 "기술 결정 지금 하자"고 하면 `fde run techgate`.
- 스위치 `tech_gate`가 꺼져 있으면 열리지 않는다. 그때는 뼈대의 기존 구조로 가고, 구조를 바꾸는 일은 모두 D1로 묻는다.

## 2. 무엇을 정하나

- 바인딩 `[runtime] fixed_decisions`에 있는 것은 **이미 정해진 것**이라 다시 논의하지 않는다(예: 봇 LLM, 임베딩, 저장소, 응답 구조).
- 남는 것은 플랫폼 프로필 5절의 기본 항목과 요구사항에서 나온 항목이다: 그래프 구조 변경 범위, 데이터 배치, 인물 데이터의 공용/전용, 외부 API 추가, 버튼 중심 대화, 선제 발송, 심사자 첫 방문 처리 등.

## 3. 흐름

1. 위원 6명(런타임·데이터 아키텍트, 통합 담당, 플랫폼 제약 검사관, 구현 비용 추정가, 패키징 전략가)이 항목별 선택지와 장단점·예상 시간을 낸다.
2. **반대 위원**이 모든 제안에 "더 단순한 방법은 없나"로 반박한다. 5시간짜리 구현에서는 거의 항상 단순한 쪽이 이긴다.
3. **테크 리드(위원장)**가 결정 기록(ADR)을 쓰고 등급을 매긴다: 카탈로그 밖 외부 서비스·데이터 구조·되돌리기 어려운 것은 D1, 되돌릴 수 있지만 영향이 큰 것은 D2, 나머지는 D3(자동).
4. D1·D2는 결정 큐에 들어가고, 디렉터가 다음 보고 때 AskUserQuestion으로 묻는다(fde-director 4절). D1은 답이 올 때까지 해당 구현을 시작하지 않는다.

## 4. 사용자에게 전하는 형식

- "기술 결정 기록이 나왔습니다" + 결정 목록(제목 · 결정 · 등급)을 5줄 이내로.
- 각 D1 질문에는 반대 위원의 반론을 한 줄 붙인다(선택의 근거가 보이게).
- ADR 전문은 `.claude/fde-mode/tech/ADR-*.md`와 대시보드 구현 탭에 있다고 알린다. 이 기록은 발표·심사에서 "왜 이렇게 만들었나"를 설명하는 자료다.

## 5. 다음

게이트가 끝나도 동결은 별도다(fde-freeze). 동결 판단관은 D1 기술 결정이 남아 있으면 그것을 막는 항목으로 올린다.
