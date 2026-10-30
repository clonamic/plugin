# 조직도 (org-chart)

`src/fde_mode/roster.py`에서 만든 표다(에이전트 94명). 모델은 전원 `claude-opus-5-5`, 추론 강도는 일반 `high`, 판단·통합·중재 `xhigh`. 다시 만들기: `fde roster --md`.

- ★ 본부장(본부 입장을 통합하고 토론에서 본부를 대표)
- 빠른 = 매 라운드 빠른 분석에 참여
- 독립석 = 토론 기록을 보지 않음(가드가 읽기를 막는 자리도 있다: 블라인드 검증관·반론관·맞춤 적합성 심사관·AI티 검사관)

## 지휘부 (`command`)

| 에이전트 | 직함 | 팀 | 강도 | 모드 | 표시 |
|---|---|---|---|---|---|
| `fde-engagement-lead` | 엔게이지먼트 리드 | 지휘부 | xhigh | conclude, opening | ★ 빠른 |
| `fde-arbiter` | 중재관 | 지휘부 | xhigh | ruling |  |
| `fde-freeze-judge` | 동결 판단관 | 지휘부 | xhigh | freeze |  |
| `fde-change-analyst` | 변경 영향 분석관 | 지휘부 | xhigh | change |  |
| `fde-chief-clerk` | 서기장 | 지휘부 | high | minutes, final |  |
| `fde-candidate-merger` | 후보 통합관 | 지휘부 | high | merge | 빠른 |

## 검증 본부(독립석) (`verify`)

| 에이전트 | 직함 | 팀 | 강도 | 모드 | 표시 |
|---|---|---|---|---|---|
| `fde-blind-verifier` | 블라인드 검증관 | 검증 | xhigh | verify | 빠른 독립석 |
| `fde-counter-arguer` | 반론관 | 검증 | xhigh | counter | 빠른 독립석 |
| `fde-doc-auditor` | 문서 일관성 감사관 | 검증 | high | audit | 독립석 |

## 접수·기록실 (`intake`)

| 에이전트 | 직함 | 팀 | 강도 | 모드 | 표시 |
|---|---|---|---|---|---|
| `fde-scribe` | 기록관 | 기록팀 | high | scribe | 빠른 |
| `fde-utterance-tagger` | 발화 태거 | 태깅팀 | high | tag | 빠른 |
| `fde-topic-classifier` | 주제 분류가 | 태깅팀 | high | topic | 빠른 |

## 인물 이해 본부 (`persona`) — 스위치 `division_persona`

팀: 언어 행동팀 · 생활 패턴팀 · 심리·결정팀 · 변화 추적팀

| 에이전트 | 직함 | 팀 | 강도 | 모드 | 표시 |
|---|---|---|---|---|---|
| `fde-persona-modeler` | 인물 통합 모델러(본부장) | 본부장 | xhigh | position, review, rebuttal | ★ |
| `fde-language-pattern` | 언어 패턴 분석가 | 언어 행동팀 | high | analyze, complement | 빠른 |
| `fde-emotion-signal` | 감정 신호 분석가 | 언어 행동팀 | high | analyze, complement |  |
| `fde-routine-time` | 루틴·시간 분석가 | 생활 패턴팀 | high | analyze, complement |  |
| `fde-tools-environment` | 도구·환경 분석가 | 생활 패턴팀 | high | analyze, complement |  |
| `fde-motivation-values` | 동기·가치 분석가 | 심리·결정팀 | high | analyze, complement |  |
| `fde-decision-style` | 의사결정 스타일 분석가 | 심리·결정팀 | high | analyze, complement | 빠른 |
| `fde-consistency-tracker` | 일관성 추적가 | 변화 추적팀 | xhigh | analyze, complement | 빠른 |
| `fde-leading-answer-detector` | 유도 답변 판별가 | 변화 추적팀 | high | analyze, complement |  |

## 문제 정의 본부 (`problem`) — 스위치 `division_problem`

팀: 근본 문제팀 · 여정팀 · 맥락팀 · 요구사항팀

| 에이전트 | 직함 | 팀 | 강도 | 모드 | 표시 |
|---|---|---|---|---|---|
| `fde-problem-lead` | 문제 정의 리드(본부장) | 본부장 | xhigh | position, review, rebuttal | ★ |
| `fde-problem-archaeologist` | 문제 고고학자 | 근본 문제팀 | high | analyze, complement | 빠른 |
| `fde-current-process` | 현재 방식 분석가 | 근본 문제팀 | high | analyze, complement |  |
| `fde-journey-mapper` | 사용 여정 분석가 | 여정팀 | high | analyze, complement |  |
| `fde-trigger-exit` | 시작·종료 조건 분석가 | 여정팀 | high | analyze, complement |  |
| `fde-domain-expert` | 도메인 전문가 | 맥락팀 | high | analyze, complement, brief |  |
| `fde-stakeholder-mapper` | 이해관계자 분석가 | 맥락팀 | high | analyze, complement |  |
| `fde-glossary-keeper` | 용어 사전 담당 | 맥락팀 | high | analyze, complement |  |
| `fde-requirements-registrar` | 요구사항 관리관 | 요구사항팀 | xhigh | analyze, complement | 빠른 |

## 솔루션 설계 본부 (`solution`) — 스위치 `division_solution`

팀: 경험팀 · 개인화팀 · 엔지니어링팀 · 환경·패키징팀

| 에이전트 | 직함 | 팀 | 강도 | 모드 | 표시 |
|---|---|---|---|---|---|
| `fde-solution-architect` | 솔루션 아키텍트(본부장) | 본부장 | xhigh | position, review, rebuttal | ★ |
| `fde-conversation-ux` | 대화 UX 설계자 | 경험팀 | high | analyze, complement |  |
| `fde-bot-character` | 봇 캐릭터 설계자 | 경험팀 | high | analyze, complement |  |
| `fde-data-memory-designer` | 데이터·메모리 설계자 | 개인화팀 | high | analyze, complement |  |
| `fde-personalization-strategist` | 개인화 전략가 | 개인화팀 | xhigh | analyze, complement |  |
| `fde-agent-architect` | 에이전트 아키텍트 | 엔지니어링팀 | high | analyze, complement |  |
| `fde-platform-constraints` | 플랫폼 제약 검사관 | 엔지니어링팀 | high | analyze, complement, tech, brief | 빠른 |
| `fde-cost-estimator` | 구현 비용 추정가 | 엔지니어링팀 | high | analyze, complement, tech |  |
| `fde-environment-analyst` | 환경 분석가 | 환경·패키징팀 | high | analyze, complement, brief | 빠른 |
| `fde-packaging-strategist` | 패키징 전략가 | 환경·패키징팀 | xhigh | analyze, complement, brief, tech |  |

## 리스크·품질 본부 (`risk`) — 스위치 `division_risk`

팀: 실패 분석팀 · 검수 설계팀

| 에이전트 | 직함 | 팀 | 강도 | 모드 | 표시 |
|---|---|---|---|---|---|
| `fde-quality-lead` | 품질 리드(본부장) | 본부장 | xhigh | position, review, rebuttal | ★ |
| `fde-exception-scenarios` | 예외 시나리오 분석가 | 실패 분석팀 | high | analyze, complement |  |
| `fde-safety-privacy` | 안전·개인정보 검토관 | 실패 분석팀 | high | analyze, complement |  |
| `fde-acceptance-designer` | 수용 테스트 설계자 | 검수 설계팀 | high | analyze, complement | 빠른 |
| `fde-simulated-user-writer` | 가상 사용자 작가 | 검수 설계팀 | high | analyze, complement |  |

## 전략·범위 본부 (`strategy`) — 스위치 `division_strategy`

팀: 범위팀 · 차별화팀

| 에이전트 | 직함 | 팀 | 강도 | 모드 | 표시 |
|---|---|---|---|---|---|
| `fde-strategy-lead` | 전략 리드(본부장) | 본부장 | xhigh | position, review, rebuttal | ★ |
| `fde-scope-manager` | 범위 매니저 | 범위팀 | xhigh | analyze, complement, brief | 빠른 |
| `fde-time-budget` | 시간 예산 관리자 | 범위팀 | high | analyze, complement |  |
| `fde-hidden-expectations` | 숨은 기대 분석가 | 차별화팀 | high | analyze, complement |  |
| `fde-judge-perspective` | 심사 관점 분석가 | 차별화팀 | high | analyze, complement, brief |  |
| `fde-demo-scenario` | 데모 시나리오 작가 | 차별화팀 | high | analyze, complement, final |  |

## 커뮤니케이션 본부 (`comms`) — 스위치 `division_comms`

팀: 질문팀 · 확인팀 · 코칭팀

| 에이전트 | 직함 | 팀 | 강도 | 모드 | 표시 |
|---|---|---|---|---|---|
| `fde-interview-director` | 인터뷰 디렉터(본부장) | 본부장 | xhigh | position, review, rebuttal | ★ |
| `fde-question-writer` | 질문 작성가 | 질문팀 | high | write | 빠른 |
| `fde-question-sequencer` | 질문 순서 설계자 | 질문팀 | high | sequence |  |
| `fde-readback-writer` | 확인 요약 작성가 | 확인팀 | high | readback |  |
| `fde-interviewer-coach` | 인터뷰어 코치 | 코칭팀 | high | analyze, complement | 빠른 |

## 데이터 본부 (`data`) — 스위치 `division_data`

팀: 수집팀 · 검증팀 · 정제·적재팀

| 에이전트 | 직함 | 팀 | 강도 | 모드 | 표시 |
|---|---|---|---|---|---|
| `fde-data-lead` | 데이터 리드(본부장) | 본부장 | xhigh | position, review, rebuttal, dataplan, datareport | ★ |
| `fde-data-sourcing-planner` | 데이터 수집 계획가 | 수집팀 | high | analyze, complement, brief |  |
| `fde-data-validator` | 데이터 검증관 | 검증팀 | high | validate |  |
| `fde-data-consistency-checker` | 인터뷰 대조 검사관 | 검증팀 | high | consistency |  |
| `fde-data-cleaner` | 데이터 정제 담당 | 정제·적재팀 | high | clean |  |
| `fde-data-loader` | 데이터 적재 담당 | 정제·적재팀 | high | load |  |
| `fde-data-provenance-auditor` | 데이터 출처 감사관 | 정제·적재팀 | xhigh | audit | 독립석 |

## 기술 위원회 (`techgate`) — 스위치 `tech_gate`

| 에이전트 | 직함 | 팀 | 강도 | 모드 | 표시 |
|---|---|---|---|---|---|
| `fde-tech-lead` | 테크 리드(위원장·구현 총괄) | 위원장 | xhigh | decide, plan, replan | ★ |
| `fde-runtime-architect` | 런타임 아키텍트 | 위원 | high | tech |  |
| `fde-data-architect` | 데이터 아키텍트 | 위원 | high | tech |  |
| `fde-integration-specialist` | 통합 담당 | 위원 | high | tech |  |
| `fde-tech-devils-advocate` | 반대 위원 | 위원 | xhigh | challenge |  |

## 구현-설계 본부 (`build-design`) — 스위치 `build`

| 에이전트 | 직함 | 팀 | 강도 | 모드 | 표시 |
|---|---|---|---|---|---|
| `fde-design-lead` | 설계 본부장 | 본부장 | xhigh | design | ★ |
| `fde-graph-designer` | 그래프 설계자 | 설계팀 | high | design |  |
| `fde-prompt-engineer` | 프롬프트 엔지니어 | 설계팀 | high | design, implement |  |
| `fde-schema-designer` | 데이터 스키마 설계자 | 설계팀 | high | design |  |
| `fde-spec-tracer` | 명세 추적관 | 설계팀 | high | trace |  |
| `fde-detail-designer` | 디테일 설계자 | 설계팀 | high | design |  |

## 구현-개발 본부 (`build-dev`) — 스위치 `build`

| 에이전트 | 직함 | 팀 | 강도 | 모드 | 표시 |
|---|---|---|---|---|---|
| `fde-dev-lead` | 개발 본부장 | 본부장 | xhigh | unblock | ★ |
| `fde-graph-developer` | 그래프·노드 개발자 | 개발팀 | high | implement |  |
| `fde-tool-developer` | 도구 통합 개발자 | 개발팀 | high | implement |  |
| `fde-platform-integrator` | 플랫폼 연결 담당 | 개발팀 | high | implement |  |

## 구현-리뷰 본부(독립석) (`build-review`) — 스위치 `build`

| 에이전트 | 직함 | 팀 | 강도 | 모드 | 표시 |
|---|---|---|---|---|---|
| `fde-code-reviewer` | 코드 리뷰어 | 리뷰 | xhigh | codereview | 독립석 |
| `fde-spec-conformance` | 명세 대조관 | 리뷰 | xhigh | codereview | 독립석 |

## 구현-배포·운영 본부 (`build-ops`) — 스위치 `build`

| 에이전트 | 직함 | 팀 | 강도 | 모드 | 표시 |
|---|---|---|---|---|---|
| `fde-release-manager` | 릴리스 관리자(본부장) | 본부장 | xhigh | release, rollback, final | ★ |
| `fde-deploy-operator` | 배포 담당 | 배포팀 | high | deploy |  |
| `fde-observability` | 관측 담당 | 운영팀 | high | observe |  |

## 구현-QA 본부(독립석) (`build-qa`) — 스위치 `build`

| 에이전트 | 직함 | 팀 | 강도 | 모드 | 표시 |
|---|---|---|---|---|---|
| `fde-qa-lead` | QA 본부장 | 본부장 | xhigh | verdict | ★ 독립석 |
| `fde-scenario-tester` | 시나리오 시험관 | QA팀 | high | qa | 독립석 |
| `fde-simulated-user-tester` | 가상 사용자 시험관 | QA팀 | high | qa | 독립석 |
| `fde-latency-checker` | 응답 시간 검사관 | QA팀 | high | qa | 독립석 |
| `fde-display-checker` | 표시 형식 검사관 | QA팀 | high | qa | 독립석 |
| `fde-fit-judge` | 맞춤 적합성 심사관 | QA팀 | xhigh | qa | 독립석 |
| `fde-ux-checker` | UX 검사관 | QA팀 | high | qa | 독립석 |
| `fde-ai-tell-checker` | AI티 검사관 | QA팀 | high | qa | 독립석 |

## 마감·회고 (`closing`)

| 에이전트 | 직함 | 팀 | 강도 | 모드 | 표시 |
|---|---|---|---|---|---|
| `fde-retro-analyst` | 회고 분석가 | 회고 | high | retro |  |

## 리허설 (`rehearsal`)

| 에이전트 | 직함 | 팀 | 강도 | 모드 | 표시 |
|---|---|---|---|---|---|
| `fde-mock-persona` | 가짜 인물(리허설) | 리허설 | high | create |  |
| `fde-rehearsal-grader` | 리허설 채점관 | 리허설 | xhigh | grade | 독립석 |

## 교차 검토 짝 (토론 라운드)

| 검토하는 본부 | 검토받는 본부 | 묻는 것 |
|---|---|---|
| 인물 이해 본부 | 솔루션 설계 본부 | 이 기능이 이 사람의 패턴과 맞나, 일반적인 사람용 기능은 아닌가 |
| 솔루션 설계 본부 | 인물 이해 본부 | 이 패턴 분석이 봇 동작으로 바뀔 수 있나, 쓸모없는 분석은 아닌가 |
| 문제 정의 본부 | 전략·범위 본부 | 범위를 줄이다가 핵심 문제를 잘라 내지 않았나 |
| 전략·범위 본부 | 문제 정의 본부 | 이 깊이까지 파는 게 남은 시간 안에서 의미 있나 |
| 리스크·품질 본부 | 솔루션 설계 본부 | 이 설계가 이 인물의 실제 입력에서 깨지지 않나 |
| 인물 이해 본부 | 문제 정의 본부 | 도메인 일반론을 이 사람에게 덮어씌우지 않았나 |
| 문제 정의 본부 | 인물 이해 본부 | 성향 분석이 실제 문제와 연결되나 |
| 데이터 본부 | 솔루션 설계 본부 | 이 설계에 필요한 데이터가 실제로 있고 믿을 만한가 |
| 문제 정의 본부 | 데이터 본부 | 이 데이터가 실제 문제에 답하나, 엉뚱한 데이터를 모으고 있지 않나 |
| 커뮤니케이션 본부 | 전체 | 이 빈틈을 이 인물에게 실제로 물을 수 있는 말로 바꿀 수 있나 |
