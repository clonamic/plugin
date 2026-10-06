---
name: clonamic-task-log
description: Turn your own git work on a chosen day in the current project into a portfolio-ready Korean work log (local files plus Notion) — runs ONLY when the user types /clonamic-task-log [날짜]. Date forms - 오늘, 어제, 그제, YYYY-MM-DD, MM-DD, ranges with ~. Other first words - 설정, 포트폴리오 정리, 노션 동기화.
disable-model-invocation: true
user-invocable: true
---

# 작업 기록

이 스킬은 사용자가 `/clonamic-task-log`를 직접 입력했을 때만 실행한다. 커밋, 작업 보고, 다른 스킬 실행 중에 스스로 켜지 않는다.

지금 열린 프로젝트에서 사용자가 그날 직접 한 git 작업을 날짜별 작업 기록으로 정리한다. 기록은 사용자 혼자 보는 비공개 자료이고 목적은 포트폴리오다. 기록은 커밋 통계가 아니라 그날 무엇을 왜 어떻게 해서 무엇이 달라졌는지를 쓴다. 파일 이름, 경로, 비밀 정보는 어디에도 남기지 않는다.

## 0. 공통 규칙

- **스크립트.** 이 `SKILL.md`가 있는 폴더를 `SKILL_DIR`로 두고 `python3 "$SKILL_DIR/scripts/tasklog.py" --agent-dir <에이전트 폴더> <명령>`으로 실행한다. 모든 명령은 JSON 하나를 출력한다. Python 3.12 이상, 표준 라이브러리만 쓴다. `python3 --version`이 3.12보다 낮으면 `uv python install 3.12`(또는 OS 패키지 관리자)로 설치해 그 인터프리터로 실행한다. 낮은 버전으로 우회하지 않는다.
- **에이전트 폴더.** 지금 실행 중인 호스트의 폴더를 쓴다. Claude Code `.claude`, Codex `.codex`, Cursor `.cursor`, Grok `.grok`.
- **저장 위치.** 이 플러그인이 저장하는 것은 모두 `<프로젝트>/<에이전트 폴더>/log-part/` 안에 있고, CLI(`save`, `write`, `notion-set`)만 쓴다. 에이전트 폴더에 파일을 직접 쓰지 않는다. 홈 폴더나 다른 프로젝트에는 아무것도 저장하지 않는다. state.json에 프로젝트 신원(원격 주소 해시, 루트 경로)이 있고, 다른 프로젝트에서 복사한 log-part는 거부한다. 같은 프로젝트를 옮겼으면 사용자 확인 뒤 `rebind`를 실행한다.
- **비공개 정보.** 기록, 보고서, Notion 어디에도 파일 이름, 경로, 함수·변수 이름, 커밋 해시, 브랜치·티켓 번호, URL, 메일, 호스트, IP, 환경 변수, 키를 쓰지 않는다. 기능 말로 쓴다.
- **읽기 경계.** `.env`, 자격 증명·키 파일, `.git` 내부, 의존성, 캐시, 모델·체크포인트 폴더는 읽지 않는다. git은 읽기 명령만 쓰고 프로젝트 파일, `.gitignore`, git 설정을 고치지 않는다.

## 1. 인자 읽기

명령은 `/clonamic-task-log [날짜]`다. 첫 인자가 일한 날짜이고, 없으면 오늘(프로필 시간대, 기본 Asia/Seoul)이다.

| 입력 | 뜻 |
|---|---|
| (없음), `오늘` | 오늘 |
| `어제`, `그제` | 하루 전, 이틀 전 |
| `2026-10-01` | 그 날짜 |
| `10-01` | 올해 10월 1일 |
| `09-28~10-02`, `2026-09-28~2026-10-02` | 그 기간(양 끝 포함) |
| `설정` | 프로필·Notion 위치 고치기([setup](references/setup.md) 4절) |
| `포트폴리오 정리` | 기록 전체를 포트폴리오 요약으로 묶기(6절) |
| `노션 동기화` | 로컬에만 쓰인 최근 기록을 Notion에 올리기(5절만) |

- 그 날짜(기간)에 **작성한** 내 커밋을 모은다. 마지막 실행 위치와 관계없다.
- 기록 파일은 `<YYYY-MM-DD>.md`(기간은 `<YYYY-MM-DD>~<YYYY-MM-DD>.md`), Notion 제목은 `YYYY-MM-DD`(기간은 `MMDD~MMDD`)다.
- 같은 날짜를 다시 실행하면 같은 기록과 같은 페이지를 갱신한다. 근거와 본문이 같으면 `unchanged`다. 사용자가 직접 요청한 지난 날짜에는 추가 플래그가 필요 없다.
- 해석이 모호하면 가장 좁은 범위로 정하고 보고서에 적는다.

## 2. 준비

1. `preflight`를 실행한다. `ok`가 false면 실패한 항목의 `fix`를 그대로 보여 주고 멈춘다. `.gitignore`나 `.git/info/exclude`를 대신 고치지 않는다. 필요한 것은 git 설치, 원격이 있는 저장소, git 사용자 신원, git에서 무시되는 에이전트 폴더, Python 3.12 이상이다.
2. Notion MCP 도구(검색, 조회, 페이지 생성, 페이지 수정)가 내 도구 목록에 있는지 직접 확인한다. 없으면 멈추지 않고 로컬 기록까지 한 뒤 Notion은 보고서에 `승인 시 진행`으로 남긴다.
3. `first_run`이 true면 [setup](references/setup.md)대로 한 메시지로 묻고, 답으로 profile.md·notion.md·notion-template.md를 `tasklog.py save --name <파일> < 내용`으로 저장하고 Notion 페이지를 만든다. 답을 기다리는 동안 다음 단계로 가지 않는다.
4. **한국어 검사 도구.** 아래 명령으로 clonamic-korean이 있는지 확인한다.

```bash
python3 "$SKILL_DIR/scripts/tasklog.py" --agent-dir <에이전트 폴더> korean
```

   `found`가 true면 `path`가 가리키는 스킬 폴더를 작성자에게 넘길 참고 문서 위치로 기억한다. false면 지금 호스트에 맞는 명령으로 사용자 수준(홈 폴더 아래)에 설치한다. 프로젝트 안에는 설치하지 않는다. 공식 저장소는 https://github.com/clonamic/plugin 이다.

   | 호스트 | 설치 명령 |
   |---|---|
   | Claude Code | `claude plugin marketplace add clonamic/plugin` 다음 `claude plugin install clonamic-korean@clonamic` |
   | Codex | `codex plugin marketplace add clonamic/plugin` 다음 `codex plugin add clonamic-korean@clonamic` |
   | Cursor | `git clone --depth 1 https://github.com/clonamic/plugin /tmp/clonamic-plugin && cp -R /tmp/clonamic-plugin/clonamic-korean ~/.cursor/plugins/local/clonamic-korean` |
   | Grok | `grok plugin install https://github.com/clonamic/plugin#clonamic-korean --trust` 다음 `grok plugin enable clonamic-korean` |

   설치 뒤 `korean`을 한 번 더 실행해 확인한다. 설치가 실패하면 이유를 한 줄로 말하고, 작성자 에이전트에 들어 있는 최소 문체 규칙만으로 계속한다. 멈추지 않는다.

## 3. 수집

```bash
python3 "$SKILL_DIR/scripts/tasklog.py" --agent-dir <에이전트 폴더> prepare --on "<인자 그대로>"
```

`--on`에는 사용자가 쓴 날짜 인자를 그대로 준다(없으면 생략). 스크립트가 날짜 해석, 내 커밋 수집, 거르기, 중요도, 진행 정도 추정, 익명화를 하고 작업 항목마다 `digest`(기능, 변경 종류, 정리된 힌트)를 담은 JSON을 낸다. 거르는 것은 병합·봇·되돌림 쌍·빈 커밋·생성 파일만 바꾼 커밋 같은 이유가 분명한 것뿐이다.

- `empty`가 true면 기록하지 않고 "그 날짜에 새로 기록할 내 커밋 없음"으로 보고한다.
- `evidence.complete`가 false면 기록은 쓰되 보고서에 일부만 수집했다고 적고 Notion 동기화는 `승인 시 진행`으로 남긴다.

## 4. 기록 쓰기

이 스킬을 실행한 세션이 리더다. 리더가 내용을 알고, 작성자가 문장을 쓴다.

1. **리더가 실제 변경을 읽는다.** 작업 항목마다 `git show`, 바뀐 코드, 시험, 문서를 읽기 경계 안에서 읽고 작업 메모(WORK NOTES)를 쓴다. 항목별로 다음을 담는다.
   - 문제: 왜 필요했는지.
   - 한 일: 무엇을 어떻게 했는지, 고른 기술.
   - 결과: 지금 동작이 어떻게 다른지. 측정한 숫자는 있을 때만.
   - (있으면) 판단: 고른 이유와 접은 대안. 문제 해결: 증상, 원인, 해결, 확인.

   작업 메모는 기능 말로만 쓴다. 파일 이름, 경로, 식별자, 비밀을 쓰지 않는다. `digest`만으로 이해되지 않는 일을 추측해서 채우지 않는다. 읽어도 모르면 그 항목은 `그 밖에`로 넘긴다.

2. **작성자에게 맡긴다.** 작성자에게 주는 것은 `prepare` JSON, 작업 메모, [entry](references/entry.md) 경로, 사용자가 이번 대화에서 알려 준 사실, 2절에서 찾은 clonamic-korean 스킬 폴더(있으면)다. 프로젝트 경로, diff, state.json, `.run.json`은 넘기지 않는다. 작성자 정의는 플러그인의 `agents/clonamic-task-logger.md`다.

   | 호스트 | 작성자 |
   |---|---|
   | Claude Code | 플러그인 에이전트 `clonamic-task-log:clonamic-task-logger`(Sonnet) |
   | Codex | 일반 서브에이전트에 `agents/clonamic-task-logger.md` 본문을 지시문으로 주고 모델은 쓸 수 있는 가장 최신 `*-luna`(현재 `gpt-6-luna`) |
   | Cursor, Grok | 플러그인 에이전트, 또는 일반 서브에이전트에 같은 본문. Sonnet 급 모델을 쓸 수 있으면 그 모델 |
   | 서브에이전트를 쓸 수 없음 | 리더가 같은 본문을 따라 차례로 직접 쓰고, 보고서에 "작성자 서브에이전트 없이 리더가 작성" 한 줄을 남긴다 |

3. **리더가 검토한다.** 초안을 [entry](references/entry.md)와 대조한다. 헤딩과 순서, 항목마다 문제·한 일·결과, 통계 문장(커밋·파일·줄 수)이나 얼버무림이 없는지, 숫자가 입력에서 온 것인지, 내용이 작업 메모와 맞는지 본다.
4. **게이트.** 초안을 OS 임시 폴더의 파일(예: `mktemp`로 만든 경로)에 저장하고 `gate --entry <파일>`을 실행한다. 종료 코드 2면 `blocked` 목록을 작성자에게 돌려 그 줄만 고치게 한다(서브에이전트가 없으면 리더가 고친다). 게이트 판정을 눈대중으로 뒤집지 않는다. 세 번 고쳐도 막히면 멈추고 남은 항목을 보고한다.
5. **한국어 검사.** 게이트를 통과한 초안에 `korean --entry <파일>`을 실행한다. 종료 코드 2면 `report`를 작성자에게 돌려 고치고 게이트부터 다시 한다. 1(경고)은 보고서에 한 줄 적고 진행한다. `found`가 false면 이 단계는 건너뛴다.
6. **저장.** `write --entry <파일>`로 저장한다. 날짜 키가 이번 실행(`.run.json`)과 같은지 확인하고, 해당 블록만 바꾸고(블록 밖에 사용자가 쓴 글은 그대로), state.json과 index.md를 갱신한다. 같은 근거와 같은 본문이면 `unchanged`다.

## 5. Notion 동기화

[notion](references/notion.md)의 순서를 따른다. 핵심만 적으면 다음과 같다.

- 작업로그 위치는 실행마다 한 번만 확정한다(state.json의 ID를 조회, 없으면 제목 검색).
- 날짜 페이지 후보가 0개면 만들고, 1개면 갱신하고, 2개 이상이면 멈추고 보고한다.
- 제목은 `YYYY-MM-DD`(기간은 `MMDD~MMDD`), 첫 블록은 대표 성과 한 줄이고 본문은 로컬 기록과 같다. 본문이 같으면 쓰지 않는다.
- 생성 응답이 끊기면 다시 만들지 않고 검색·조회로 찾는다.
- 쓴 뒤 다시 조회해 제목, 첫 블록, 절 제목을 확인하고 `notion-set`으로 ID를 적는다. 그다음 진행 현황 페이지(기능 · 진행률 · 최근 변화 · 남은 일)를 갱신한다.
- 메타데이터와 HTML 주석은 Notion에 넣지 않는다. Notion MCP가 없거나 실패하면 로컬 기록은 그대로 두고 `승인 시 진행`으로 남긴다.

## 6. 포트폴리오 정리

1. `portfolio`로 전체 기록의 묶음 데이터를 받는다.
2. [portfolio](references/portfolio.md)의 구조(역할 한 줄, 대표 성과 3~5, 기능별 기여, 사용 기술, 문제 해결 사례 2~3)로 쓴다. 4절처럼 작성자에게 맡기면 묶음 데이터와 portfolio 문서 경로를 넘긴다. 기록에 있는 사실과 숫자만 쓰고 새 사실을 더하지 않는다.
3. `write-portfolio --entry <파일>`로 게이트를 거쳐 `log-part/portfolio.md`에 저장하고, Notion 작업로그 아래 `포트폴리오 요약` 페이지를 같은 0/1/2+ 규칙으로 만들거나 갱신한 뒤 `notion-set --kind portfolio`로 적는다.

## 7. 보고

채팅에 한 번 보고한다. 파일로 만들지 않는다. 맨 위가 결론이고 나머지는 목록이다.

```text
## 핵심 요약
- 기록 완료 — 2026-10-05, 작업 항목 3개
- 미검증·실패: 없음

## 결과
- 로컬 기록 — log-part/2026-10-05.md 작성
- Notion — 작업로그 / 2026-10-05 갱신, 제목·첫 블록·절 확인
- 진행 정도 — 결제 모듈 약 55%

## 범위 밖 — 있을 때만
- 승인 시 진행1: Notion 동기화 — Notion MCP 도구가 없어 로컬에만 기록함
```

- 해당 없는 절과 줄은 뺀다. 기록 본문을 보고서에 다시 붙이지 않는다. 사용자가 보여 달라고 하면 그때 보여 준다.
- 보고서 안의 경로는 log-part 안의 기록 파일만 쓴다.

## 저장 구조

```text
<프로젝트>/<에이전트 폴더>/log-part/
├── profile.md            파트, 담당 기능·마일스톤, 신원, 시간대
├── notion.md             Notion 위치와 페이지 구조
├── notion-template.md    Notion 페이지 템플릿 사본
├── 2026-10-05.md         날짜 기록
├── index.md              타임라인과 기능별 진행
├── portfolio.md          포트폴리오 요약(요청했을 때)
└── state.json            프로젝트 신원, 커서, Notion ID, 실행 지문
```
