"""The organisation as data. The planner reads it, the agent files implement it,
and tests/test_roster.py keeps the two identical.

effort: "high" for regular analysts, "xhigh" for anything that judges,
integrates or arbitrates (user decision: Opus 5.5 everywhere, high = 일반,
xhigh = 핵심).
"""
from __future__ import annotations

from dataclasses import dataclass, field

READ_WRITE = "Read, Write, Grep, Glob"
WEB = "Read, Write, Grep, Glob, WebSearch, WebFetch"
CODE = "Read, Write, Edit, Grep, Glob, Bash"
CHECK = "Read, Write, Grep, Glob, Bash"


@dataclass(frozen=True)
class Agent:
    name: str              # file name and frontmatter name (agents/<name>.md)
    ko: str                # Korean title shown to the user
    division: str
    team: str
    effort: str
    tools: str
    modes: tuple[str, ...]
    quick: bool = False    # part of every quick round
    head: bool = False
    independent: bool = False  # never sees debate records


@dataclass(frozen=True)
class Division:
    key: str
    ko: str
    head: str | None
    switch: str | None
    teams: tuple[str, ...] = field(default_factory=tuple)


DIVISIONS: dict[str, Division] = {d.key: d for d in [
    Division("command", "지휘부", "fde-engagement-lead", None),
    Division("verify", "검증 본부(독립석)", None, None),
    Division("intake", "접수·기록실", None, None),
    Division("persona", "인물 이해 본부", "fde-persona-modeler", "division_persona",
             ("언어 행동팀", "생활 패턴팀", "심리·결정팀", "변화 추적팀")),
    Division("problem", "문제 정의 본부", "fde-problem-lead", "division_problem",
             ("근본 문제팀", "여정팀", "맥락팀", "요구사항팀")),
    Division("solution", "솔루션 설계 본부", "fde-solution-architect", "division_solution",
             ("경험팀", "개인화팀", "엔지니어링팀", "환경·패키징팀")),
    Division("risk", "리스크·품질 본부", "fde-quality-lead", "division_risk", ("실패 분석팀", "검수 설계팀")),
    Division("strategy", "전략·범위 본부", "fde-strategy-lead", "division_strategy", ("범위팀", "차별화팀")),
    Division("comms", "커뮤니케이션 본부", "fde-interview-director", "division_comms",
             ("질문팀", "확인팀", "코칭팀")),
    Division("data", "데이터 본부", "fde-data-lead", "division_data", ("수집팀", "검증팀", "정제·적재팀")),
    Division("techgate", "기술 위원회", "fde-tech-lead", "tech_gate"),
    Division("build-design", "구현-설계 본부", "fde-design-lead", "build"),
    Division("build-dev", "구현-개발 본부", "fde-dev-lead", "build"),
    Division("build-review", "구현-리뷰 본부(독립석)", None, "build"),
    Division("build-ops", "구현-배포·운영 본부", "fde-release-manager", "build"),
    Division("build-qa", "구현-QA 본부(독립석)", "fde-qa-lead", "build"),
    Division("closing", "마감·회고", None, None),
    Division("rehearsal", "리허설", None, None),
]}

A = Agent
AGENTS: list[Agent] = [
    # 지휘부 (L1)
    A("fde-engagement-lead", "엔게이지먼트 리드", "command", "지휘부", "xhigh", READ_WRITE, ("conclude", "opening"), quick=True, head=True),
    A("fde-arbiter", "중재관", "command", "지휘부", "xhigh", READ_WRITE, ("ruling",)),
    A("fde-freeze-judge", "동결 판단관", "command", "지휘부", "xhigh", READ_WRITE, ("freeze",)),
    A("fde-change-analyst", "변경 영향 분석관", "command", "지휘부", "xhigh", READ_WRITE, ("change",)),
    A("fde-chief-clerk", "서기장", "command", "지휘부", "high", "Read, Write, Edit, Grep, Glob", ("minutes", "final")),
    A("fde-candidate-merger", "후보 통합관", "command", "지휘부", "high", READ_WRITE, ("merge",), quick=True),
    # 검증 본부 (독립석)
    A("fde-blind-verifier", "블라인드 검증관", "verify", "검증", "xhigh", READ_WRITE, ("verify",), quick=True, independent=True),
    A("fde-counter-arguer", "반론관", "verify", "검증", "xhigh", READ_WRITE, ("counter",), quick=True, independent=True),
    A("fde-doc-auditor", "문서 일관성 감사관", "verify", "검증", "high", READ_WRITE, ("audit",), independent=True),
    # 접수·기록실
    A("fde-scribe", "기록관", "intake", "기록팀", "high", READ_WRITE, ("scribe",), quick=True),
    A("fde-utterance-tagger", "발화 태거", "intake", "태깅팀", "high", READ_WRITE, ("tag",), quick=True),
    A("fde-topic-classifier", "주제 분류가", "intake", "태깅팀", "high", READ_WRITE, ("topic",), quick=True),
    # 인물 이해 본부
    A("fde-persona-modeler", "인물 통합 모델러(본부장)", "persona", "본부장", "xhigh", "Read, Write, Edit, Grep, Glob", ("position", "review", "rebuttal"), head=True),
    A("fde-language-pattern", "언어 패턴 분석가", "persona", "언어 행동팀", "high", READ_WRITE, ("analyze", "complement"), quick=True),
    A("fde-emotion-signal", "감정 신호 분석가", "persona", "언어 행동팀", "high", READ_WRITE, ("analyze", "complement")),
    A("fde-routine-time", "루틴·시간 분석가", "persona", "생활 패턴팀", "high", READ_WRITE, ("analyze", "complement")),
    A("fde-tools-environment", "도구·환경 분석가", "persona", "생활 패턴팀", "high", READ_WRITE, ("analyze", "complement")),
    A("fde-motivation-values", "동기·가치 분석가", "persona", "심리·결정팀", "high", READ_WRITE, ("analyze", "complement")),
    A("fde-decision-style", "의사결정 스타일 분석가", "persona", "심리·결정팀", "high", READ_WRITE, ("analyze", "complement"), quick=True),
    A("fde-consistency-tracker", "일관성 추적가", "persona", "변화 추적팀", "xhigh", READ_WRITE, ("analyze", "complement"), quick=True),
    A("fde-leading-answer-detector", "유도 답변 판별가", "persona", "변화 추적팀", "high", READ_WRITE, ("analyze", "complement")),
    # 문제 정의 본부
    A("fde-problem-lead", "문제 정의 리드(본부장)", "problem", "본부장", "xhigh", READ_WRITE, ("position", "review", "rebuttal"), head=True),
    A("fde-problem-archaeologist", "문제 고고학자", "problem", "근본 문제팀", "high", READ_WRITE, ("analyze", "complement"), quick=True),
    A("fde-current-process", "현재 방식 분석가", "problem", "근본 문제팀", "high", READ_WRITE, ("analyze", "complement")),
    A("fde-journey-mapper", "사용 여정 분석가", "problem", "여정팀", "high", READ_WRITE, ("analyze", "complement")),
    A("fde-trigger-exit", "시작·종료 조건 분석가", "problem", "여정팀", "high", READ_WRITE, ("analyze", "complement")),
    A("fde-domain-expert", "도메인 전문가", "problem", "맥락팀", "high", WEB, ("analyze", "complement", "brief")),
    A("fde-stakeholder-mapper", "이해관계자 분석가", "problem", "맥락팀", "high", READ_WRITE, ("analyze", "complement")),
    A("fde-glossary-keeper", "용어 사전 담당", "problem", "맥락팀", "high", "Read, Write, Edit, Grep, Glob", ("analyze", "complement")),
    A("fde-requirements-registrar", "요구사항 관리관", "problem", "요구사항팀", "xhigh", "Read, Write, Edit, Grep, Glob", ("analyze", "complement"), quick=True),
    # 솔루션 설계 본부
    A("fde-solution-architect", "솔루션 아키텍트(본부장)", "solution", "본부장", "xhigh", READ_WRITE, ("position", "review", "rebuttal"), head=True),
    A("fde-conversation-ux", "대화 UX 설계자", "solution", "경험팀", "high", READ_WRITE, ("analyze", "complement")),
    A("fde-bot-character", "봇 캐릭터 설계자", "solution", "경험팀", "high", READ_WRITE, ("analyze", "complement")),
    A("fde-data-memory-designer", "데이터·메모리 설계자", "solution", "개인화팀", "high", READ_WRITE, ("analyze", "complement")),
    A("fde-personalization-strategist", "개인화 전략가", "solution", "개인화팀", "xhigh", "Read, Write, Edit, Grep, Glob", ("analyze", "complement")),
    A("fde-agent-architect", "에이전트 아키텍트", "solution", "엔지니어링팀", "high", READ_WRITE, ("analyze", "complement")),
    A("fde-platform-constraints", "플랫폼 제약 검사관", "solution", "엔지니어링팀", "high", READ_WRITE, ("analyze", "complement", "tech", "brief"), quick=True),
    A("fde-cost-estimator", "구현 비용 추정가", "solution", "엔지니어링팀", "high", READ_WRITE, ("analyze", "complement", "tech")),
    A("fde-environment-analyst", "환경 분석가", "solution", "환경·패키징팀", "high", READ_WRITE, ("analyze", "complement", "brief"), quick=True),
    A("fde-packaging-strategist", "패키징 전략가", "solution", "환경·패키징팀", "xhigh", READ_WRITE, ("analyze", "complement", "brief", "tech")),
    # 리스크·품질 본부
    A("fde-quality-lead", "품질 리드(본부장)", "risk", "본부장", "xhigh", READ_WRITE, ("position", "review", "rebuttal"), head=True),
    A("fde-exception-scenarios", "예외 시나리오 분석가", "risk", "실패 분석팀", "high", READ_WRITE, ("analyze", "complement")),
    A("fde-safety-privacy", "안전·개인정보 검토관", "risk", "실패 분석팀", "high", READ_WRITE, ("analyze", "complement")),
    A("fde-acceptance-designer", "수용 테스트 설계자", "risk", "검수 설계팀", "high", READ_WRITE, ("analyze", "complement"), quick=True),
    A("fde-simulated-user-writer", "가상 사용자 작가", "risk", "검수 설계팀", "high", READ_WRITE, ("analyze", "complement")),
    # 전략·범위 본부
    A("fde-strategy-lead", "전략 리드(본부장)", "strategy", "본부장", "xhigh", READ_WRITE, ("position", "review", "rebuttal"), head=True),
    A("fde-scope-manager", "범위 매니저", "strategy", "범위팀", "xhigh", READ_WRITE, ("analyze", "complement", "brief"), quick=True),
    A("fde-time-budget", "시간 예산 관리자", "strategy", "범위팀", "high", READ_WRITE, ("analyze", "complement")),
    A("fde-hidden-expectations", "숨은 기대 분석가", "strategy", "차별화팀", "high", READ_WRITE, ("analyze", "complement")),
    A("fde-judge-perspective", "심사 관점 분석가", "strategy", "차별화팀", "high", READ_WRITE, ("analyze", "complement", "brief")),
    A("fde-demo-scenario", "데모 시나리오 작가", "strategy", "차별화팀", "high", READ_WRITE, ("analyze", "complement", "final")),
    # 커뮤니케이션 본부
    A("fde-interview-director", "인터뷰 디렉터(본부장)", "comms", "본부장", "xhigh", READ_WRITE, ("position", "review", "rebuttal"), head=True),
    A("fde-question-writer", "질문 작성가", "comms", "질문팀", "high", READ_WRITE, ("write",), quick=True),
    A("fde-question-sequencer", "질문 순서 설계자", "comms", "질문팀", "high", READ_WRITE, ("sequence",)),
    A("fde-readback-writer", "확인 요약 작성가", "comms", "확인팀", "high", READ_WRITE, ("readback",)),
    A("fde-interviewer-coach", "인터뷰어 코치", "comms", "코칭팀", "high", READ_WRITE, ("analyze", "complement"), quick=True),
    # 데이터 본부 (mission: 데이터 수집·검증·정제)
    A("fde-data-lead", "데이터 리드(본부장)", "data", "본부장", "xhigh", CHECK, ("position", "review", "rebuttal", "dataplan", "datareport"), head=True),
    A("fde-data-sourcing-planner", "데이터 수집 계획가", "data", "수집팀", "high", WEB, ("analyze", "complement", "brief")),
    A("fde-data-validator", "데이터 검증관", "data", "검증팀", "high", CHECK, ("validate",)),
    A("fde-data-consistency-checker", "인터뷰 대조 검사관", "data", "검증팀", "high", CHECK, ("consistency",)),
    A("fde-data-cleaner", "데이터 정제 담당", "data", "정제·적재팀", "high", CODE, ("clean",)),
    A("fde-data-loader", "데이터 적재 담당", "data", "정제·적재팀", "high", CODE, ("load",)),
    A("fde-data-provenance-auditor", "데이터 출처 감사관", "data", "정제·적재팀", "xhigh", CHECK, ("audit",), independent=True),
    # 기술 위원회
    A("fde-tech-lead", "테크 리드(위원장·구현 총괄)", "techgate", "위원장", "xhigh", "Read, Write, Edit, Grep, Glob, Bash", ("decide", "plan", "replan"), head=True),
    A("fde-runtime-architect", "런타임 아키텍트", "techgate", "위원", "high", READ_WRITE, ("tech",)),
    A("fde-data-architect", "데이터 아키텍트", "techgate", "위원", "high", READ_WRITE, ("tech",)),
    A("fde-integration-specialist", "통합 담당", "techgate", "위원", "high", WEB, ("tech",)),
    A("fde-tech-devils-advocate", "반대 위원", "techgate", "위원", "xhigh", READ_WRITE, ("challenge",)),
    # 구현 - 설계 본부
    A("fde-design-lead", "설계 본부장", "build-design", "본부장", "xhigh", READ_WRITE, ("design",), head=True),
    A("fde-graph-designer", "그래프 설계자", "build-design", "설계팀", "high", READ_WRITE, ("design",)),
    A("fde-prompt-engineer", "프롬프트 엔지니어", "build-design", "설계팀", "high", CODE, ("design", "implement")),
    A("fde-schema-designer", "데이터 스키마 설계자", "build-design", "설계팀", "high", READ_WRITE, ("design",)),
    A("fde-spec-tracer", "명세 추적관", "build-design", "설계팀", "high", READ_WRITE, ("trace",)),
    A("fde-detail-designer", "디테일 설계자", "build-design", "설계팀", "high", READ_WRITE, ("design",)),
    # 구현 - 개발 본부
    A("fde-dev-lead", "개발 본부장", "build-dev", "본부장", "xhigh", CODE, ("unblock",), head=True),
    A("fde-graph-developer", "그래프·노드 개발자", "build-dev", "개발팀", "high", CODE, ("implement",)),
    A("fde-tool-developer", "도구 통합 개발자", "build-dev", "개발팀", "high", CODE, ("implement",)),
    A("fde-platform-integrator", "플랫폼 연결 담당", "build-dev", "개발팀", "high", CODE, ("implement",)),
    # 구현 - 리뷰 본부 (독립석)
    A("fde-code-reviewer", "코드 리뷰어", "build-review", "리뷰", "xhigh", CHECK, ("codereview",), independent=True),
    A("fde-spec-conformance", "명세 대조관", "build-review", "리뷰", "xhigh", CHECK, ("codereview",), independent=True),
    # 구현 - 배포·운영 본부
    A("fde-release-manager", "릴리스 관리자(본부장)", "build-ops", "본부장", "xhigh", CHECK, ("release", "rollback", "final"), head=True),
    A("fde-deploy-operator", "배포 담당", "build-ops", "배포팀", "high", CHECK, ("deploy",)),
    A("fde-observability", "관측 담당", "build-ops", "운영팀", "high", CHECK, ("observe",)),
    # 구현 - QA 본부 (독립석)
    A("fde-qa-lead", "QA 본부장", "build-qa", "본부장", "xhigh", CHECK, ("verdict",), head=True, independent=True),
    A("fde-scenario-tester", "시나리오 시험관", "build-qa", "QA팀", "high", CHECK, ("qa",), independent=True),
    A("fde-simulated-user-tester", "가상 사용자 시험관", "build-qa", "QA팀", "high", CHECK, ("qa",), independent=True),
    A("fde-latency-checker", "응답 시간 검사관", "build-qa", "QA팀", "high", CHECK, ("qa",), independent=True),
    A("fde-display-checker", "표시 형식 검사관", "build-qa", "QA팀", "high", CHECK, ("qa",), independent=True),
    A("fde-fit-judge", "맞춤 적합성 심사관", "build-qa", "QA팀", "xhigh", CHECK, ("qa",), independent=True),
    A("fde-ux-checker", "UX 검사관", "build-qa", "QA팀", "high", CHECK, ("qa",), independent=True),
    A("fde-ai-tell-checker", "AI티 검사관", "build-qa", "QA팀", "high", CHECK, ("qa",), independent=True),
    # 마감·회고, 리허설
    A("fde-retro-analyst", "회고 분석가", "closing", "회고", "high", READ_WRITE, ("retro",)),
    A("fde-mock-persona", "가짜 인물(리허설)", "rehearsal", "리허설", "high", READ_WRITE, ("create",)),
    A("fde-rehearsal-grader", "리허설 채점관", "rehearsal", "리허설", "xhigh", READ_WRITE, ("grade",), independent=True),
]

BY_NAME: dict[str, Agent] = {a.name: a for a in AGENTS}

# Cross-review pairs for debate rounds: (reviewing division, reviewed division, question asked)
CROSS_REVIEW: list[tuple[str, str, str]] = [
    ("persona", "solution", "이 기능이 이 사람의 패턴과 맞나, 일반적인 사람용 기능은 아닌가"),
    ("solution", "persona", "이 패턴 분석이 봇 동작으로 바뀔 수 있나, 쓸모없는 분석은 아닌가"),
    ("problem", "strategy", "범위를 줄이다가 핵심 문제를 잘라 내지 않았나"),
    ("strategy", "problem", "이 깊이까지 파는 게 남은 시간 안에서 의미 있나"),
    ("risk", "solution", "이 설계가 이 인물의 실제 입력에서 깨지지 않나"),
    ("persona", "problem", "도메인 일반론을 이 사람에게 덮어씌우지 않았나"),
    ("problem", "persona", "성향 분석이 실제 문제와 연결되나"),
    ("data", "solution", "이 설계에 필요한 데이터가 실제로 있고 믿을 만한가"),
    ("problem", "data", "이 데이터가 실제 문제에 답하나, 엉뚱한 데이터를 모으고 있지 않나"),
    ("comms", "*", "이 빈틈을 이 인물에게 실제로 물을 수 있는 말로 바꿀 수 있나"),
]

QUICK_ANALYSTS = [a.name for a in AGENTS if a.quick and "analyze" in a.modes]


def division_agents(key: str, mode: str = "analyze") -> list[Agent]:
    return [a for a in AGENTS if a.division == key and mode in a.modes and not a.head]


def head_of(key: str) -> str | None:
    d = DIVISIONS.get(key)
    return d.head if d else None


def team_mates(name: str) -> list[str]:
    a = BY_NAME[name]
    return [b.name for b in AGENTS if b.division == a.division and b.team == a.team and b.name != name
            and "analyze" in b.modes]


def org_chart_md() -> str:
    """references/org-chart.md, generated (tests keep the file identical to this output)."""
    lines = ["# 조직도 (org-chart)", "",
             f"`src/fde_mode/roster.py`에서 만든 표다(에이전트 {len(AGENTS)}명). 모델은 전원 `claude-opus-5-5`, "
             "추론 강도는 일반 `high`, 판단·통합·중재 `xhigh`. 다시 만들기: `fde roster --md`.", "",
             "- ★ 본부장(본부 입장을 통합하고 토론에서 본부를 대표)",
             "- 빠른 = 매 라운드 빠른 분석에 참여",
             "- 독립석 = 토론 기록을 보지 않음(가드가 읽기를 막는 자리도 있다: 블라인드 검증관·반론관·맞춤 적합성 심사관·AI티 검사관)",
             ""]
    for key, d in DIVISIONS.items():
        members = [a for a in AGENTS if a.division == key]
        if not members:
            continue
        head = f"## {d.ko} (`{key}`)" + (f" — 스위치 `{d.switch}`" if d.switch else "")
        lines += [head, ""]
        if d.teams:
            lines += ["팀: " + " · ".join(d.teams), ""]
        lines += ["| 에이전트 | 직함 | 팀 | 강도 | 모드 | 표시 |", "|---|---|---|---|---|---|"]
        for a in members:
            marks = " ".join(x for x in ("★" if a.head else "", "빠른" if a.quick else "", "독립석" if a.independent else "") if x)
            lines.append(f"| `{a.name}` | {a.ko} | {a.team} | {a.effort} | {', '.join(a.modes)} | {marks} |")
        lines.append("")
    lines += ["## 교차 검토 짝 (토론 라운드)", "", "| 검토하는 본부 | 검토받는 본부 | 묻는 것 |", "|---|---|---|"]
    for a, b, q in CROSS_REVIEW:
        lines.append(f"| {DIVISIONS[a].ko} | {'전체' if b == '*' else DIVISIONS[b].ko} | {q} |")
    lines.append("")
    return "\n".join(lines)
