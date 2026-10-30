---
name: fde-mode
description: Turn FDE-Mode on, off, or into rehearsal for the current project — a forward-deployed-engineer organisation of Opus 5.5 subagents that analyses a pasted persona interview, tells you what to ask next and what you must decide, then designs, builds, deploys and QA's the agent service. Runs ONLY when the user types /fde-mode [on|off|status|auto on|off|rehearsal [start|grade|end]|switch <name> on|off|help].
disable-model-invocation: true
user-invocable: true
argument-hint: "[on|off|status|auto on|off|rehearsal start|grade|end|switch <이름> on|off|help]"
---

# FDE-Mode 켜기

이 스킬은 사용자가 `/fde-mode`를 직접 입력했을 때만 실행한다. 다른 작업 중에 스스로 켜지 않는다.

켜진 뒤에는 이 세션의 메인 대화가 **FDE 디렉터**가 된다. 디렉터는 직접 분석하지 않고, 훅과 `fde next`가 정한 흐름대로 서브에이전트 조직을 움직이고, 사용자에게 물어야 할 결정을 묻는다. 모드는 사용자가 `/fde-mode off`를 하거나 회고가 끝날 때까지 켜져 있다(세션을 다시 열어도 유지).

- 플러그인 위치: `${CLAUDE_PLUGIN_ROOT}`
- 명령: `fde <명령>` (플러그인 `bin/`이 Bash 도구 PATH에 있다). 안 잡히면 `"${CLAUDE_PLUGIN_ROOT}/bin/fde"`로 실행한다.
- 모든 `fde` 명령은 JSON을 출력한다. 사용자에게는 한국어로 짧게 옮긴다.

## 인자: `$ARGUMENTS`

| 인자 | 할 일 |
|---|---|
| (없음) 또는 `on` | 아래 "켜기" 절차 |
| `off` | `fde off` 실행 → "FDE 모드를 껐습니다. 기록은 `.claude/fde-mode/`에 남아 있고 `/fde-mode`로 이어서 켭니다." 대시보드 서버는 다른 프로젝트가 쓸 수 있어 그대로 둔다(끄려면 `fde serve --stop`). |
| `status` | `fde status` → 단계, 라운드, 열린 질문, 대기 결정, 진행 중 실행, 남은 시간을 5줄 이내로 |
| `rehearsal` 또는 `rehearsal start [주제]` | 아래 "리허설" 절차(fde-rehearsal 스킬) |
| `rehearsal grade` | `fde run rehearsal-grade` → 디렉터 루프로 채점 실행 → 결과 요약 |
| `rehearsal end` | 채점 결과를 보여 준 뒤 `fde archive`로 작업 기록을 보관 폴더로 옮겨 실전 준비 상태로 되돌린다(project.toml은 유지) |
| `auto on\|off` | `fde switch autonomy on\|off`. 사용자가 이 인자를 직접 입력했을 때만 실행한다. on → "자율 모드를 켰습니다. 설계 확인·첫 배포 확인·진행 확인을 묻지 않고 추천대로 진행합니다(동결 같은 D1은 계속 묻습니다). 되돌리려면 `/fde-mode auto off`." / off → "협업 모드로 돌아왔습니다. 조각마다 설계·진행을 선택지로 묻습니다." |
| `switch <이름> on\|off` | `fde switch <이름> on\|off` → 바뀐 스위치 목록을 한 줄로 |
| `help` | 이 표와 붙여넣기 규칙을 보여 준다 |

## 켜기

1. `fde on` 을 실행한다(처음이면 `.claude/fde-mode/`와 `project.toml` 템플릿, SQLite를 만든다). 결과의 `binding_found`가 false였거나 방금 템플릿을 만들었다면, 사용자에게 "프로젝트 바인딩(`.claude/fde-mode/project.toml`)이 비어 있어 명령·가드 규칙 없이 동작합니다"라고 알리고 채울지 AskUserQuestion으로 묻는다(D2).
2. 대시보드: `fde serve --detach` → 결과의 `url`을 한 줄로 알린다. `stale`이 true면 `note`를 그대로 알린다.
3. 부팅 점검: `fde boot` → 결과를 표로 보여 준다(항목 · 결과 · 조치). 실패한 D1·D2 항목은 결정 큐에 들어가 있으니 다음 단계에서 묻는다.
4. 지금부터 **fde-director 스킬**을 따른다(훅이 매 턴 상태를 붙여 준다).
5. 사용자에게 사용법을 5줄로 알린다:
   - 인물과의 대화는 그대로 붙여넣는다. 확실하게 하려면 첫 줄을 `>>` 로 시작한다(직접 쳐도, 붙여넣는 글의 첫 줄이어도 된다). 저장되면 "R07로 저장", 못 하면 "저장 못 함"이 나온다. 표지(`>>`·`>>brief`·`>>메모`)를 치고 Shift+Enter로 줄을 바꾼 뒤 붙여 넣고 Enter(Enter만 누르면 표지만 전송된다). 또는 클립보드 맨 윗줄에 표지를 넣어 한 번에 붙여 넣는다. 표지만 보냈다면 10분 안에 바로 다음 메시지로 붙여 넣으면 그 종류로 저장된다.
   - 문제 설명·평가 기준은 첫 줄 `>>brief`, 내 메모는 `>>메모`.
   - 데이터 파일은 프로젝트 바인딩의 `data_raw` 폴더(예: `data/raw/`)에 넣으면 데이터 본부가 자동으로 시작한다.
   - 결정은 이 대화에서 선택지로 묻는다. 대시보드는 읽기용이다.
   - 제작 중에도 설계·진행을 선택지로 묻는다(자율 모드는 `/fde-mode auto on`).
6. `fde next` 를 실행하고 fde-director의 루프대로 처리한다.

## 리허설

리허설은 실전과 같은 흐름을 가짜 인물로 처음부터 끝까지 돌려 시간과 기준을 재는 것이다. 자세한 절차는 fde-rehearsal 스킬을 따른다.

1. `fde on --rehearsal` → `fde serve --detach` → `fde boot`
2. `fde run rehearsal --theme "<주제, 없으면 비움>"` → `fde next` 로 가짜 인물 생성 에이전트를 띄운다.
3. 끝나면 사용자에게 알린다: "인물 역할 지시문을 **열어 보지 말고** 복사해 **이 세션이 아닌 다른 채팅**(새 Claude 대화 등)에 붙여 인물 역할을 맡기세요. 터미널에서 `pbcopy < <프로젝트 절대 경로>/.claude/fde-mode/rehearsal/sealed/roleplay-prompt.md` 를 실행하면 내용이 화면에 안 나옵니다(열어 보면 숨은 요구사항을 알게 돼 리허설이 무의미해집니다). 그 파일은 저도 읽지 않습니다. `rehearsal/public-brief.md`는 `>>brief`로 여기에 붙여 주세요." 디렉터는 봉인 폴더를 절대 읽지 않는다(가드가 막는다).
4. 이후는 실전과 같다. 끝나면 `/fde-mode rehearsal grade` → `/fde-mode rehearsal end`.

## 하지 않는 것

- 이 스킬이 켜졌다고 디렉터가 대화를 직접 분석하지 않는다.
- `make down` 같은 인프라 삭제, `.env` 읽기, 강제 push는 하지 않는다(가드가 막지만 시도도 하지 않는다).
- 봉인된 리허설 파일을 읽거나 내용을 추측해 말하지 않는다.
