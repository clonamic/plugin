# 플러그인 규칙

Agent Plugins 1.0.0 표준을 따른다. Claude만 규격이 달라서 `.claude-plugin/`을 추가하는데, 이 파일은 손으로 쓰지 않고 스크립트로 만든다(아래 "매니페스트 동기화").

## 계층

| 층 | 무엇인가 | 위치 |
|---|---|---|
| 스킬 | 일 하나. 양식과 그 규칙(무엇인지, 언제, 어떻게 쓰는지) | `plugin-name/skills/<name>/SKILL.md` |
| 플러그인 | 역할 하나를 이루는 스킬 묶음. 필요하면 코드와 MCP를 함께 담는 배포 단위 | `plugin-name/` |
| 서브에이전트 | 독립된 컨텍스트에서 정해진 절차를 맡아 실행하는 일꾼. 스킬의 절차가 부르고, 스킬을 대신하지 않는다 | `plugin-name/agents/<name>.md` |

- 서브에이전트는 Claude, Cursor, Grok이 플러그인에서 읽는다. Codex는 플러그인의 서브에이전트를 읽지 못하므로, 서브에이전트를 쓰는 스킬은 순차 실행 대안을 함께 적는다.
- 플러그인과 따로 쓰는 서브에이전트는 `clonamic/subagents` 저장소에서 관리한다.
- 하네스 규칙을 항상 켜려면 프로젝트나 전역 `AGENTS.md`에서 `clonamic-harness/AGENTS.md`를 가리킨다. Codex, Cursor, Grok은 AGENTS.md를 읽고, Claude Code는 CLAUDE.md에 `@AGENTS.md`를 넣는다.

## 원칙

- **플러그인 하나 = 역할 하나, 스킬 하나 = 일 하나.** 기능이 겹치면 합친다.
- **스킬에는 방향, 지시, 절차, 품질 기준, 예시를 담는다.** Claude Code, Codex, Cursor, Grok Build는 셸, 파일, 브라우저, 서브에이전트를 직접 쓸 수 있다. 호스트가 할 수 있는 일을 자체 엔진으로 다시 만들지 않는다. 스크립트는 결정적이고 작으며, 모델이 손으로 하는 것보다 확실히 나을 때만 둔다(예: 바이트 단위 검증기, 호스트에 없는 형식 변환기).
- **라우터 스킬을 만들지 않는다.** 스킬 선택은 호스트가 `description`을 보고 한다.
- **`skills/` 아래 폴더에는 반드시 SKILL.md가 있다.** 참고 자료만 든 폴더는 해당 스킬의 `references/`에 넣는다.
- **언어**
  - 사용자가 읽는 것(보고서, 명세서 양식, 한국어 글쓰기 지침, 출력 예시): 한국어
  - 내부의 여러 단계 절차, 토큰이 많이 드는 운영 지시, 에이전트 사이의 계약: 영어
  - 출력이 한국어여야 하는 스킬(예: clonamic-korean): 본문을 한국어로 쓴다. 영어 지시는 영어 출력을 끌어내기 쉽다.
- **명시 호출 스킬**은 frontmatter에 `disable-model-invocation: true`, `user-invocable: true`를 넣고, 본문에도 슬래시 명령으로만 실행한다고 적는다.

## 기본 구조

```text
plugin-name/
├── plugin.json                  # 원본 매니페스트. 손으로 고치는 유일한 매니페스트
├── .claude-plugin/plugin.json   # 생성. Claude Code
├── .codex-plugin/plugin.json    # 생성. Codex UI(interface)
├── skills/
│   └── skill-name/
│       ├── SKILL.md             # 필수. frontmatter(name, description) + 절차
│       ├── references/          # 선택. 필요할 때만 읽는 문서
│       ├── scripts/             # 선택. 이 스킬만 쓰는 작은 스크립트
│       └── assets/              # 선택. 결과물에 넣는 템플릿·파일
├── agents/                      # 선택. 서브에이전트(Claude·Grok·Cursor). 없어도 스킬이 동작해야 함
├── mcp.json                     # 선택. MCP 서버
├── tests/                       # 로컬 전용. git에 올리지 않음(.gitignore)
├── LICENSE
└── THIRD_PARTY_NOTICES.md       # 외부 자료를 가져왔을 때만
```

## 코드를 쓰는 플러그인

Python은 **3.12 이상**(`requires-python = ">=3.12"`)을 쓴다.
사용자 PC의 `python3`가 3.12 이상이면 그대로 쓰고, 아니면 SKILL.md가 설치를 안내한다(`uv python install 3.12` 또는 OS 패키지 관리자). 더 낮은 버전으로 조용히 넘어가지 않는다.

**스크립트가 한 스킬에서만 쓰이면** 스킬 안에 둔다. 대부분은 이것으로 충분하다.

```text
skills/skill-name/scripts/tool.py   # 표준 라이브러리만. python3 tool.py <명령>
```

**여러 스킬이 같은 코드를 쓸 때만** 플러그인 루트에 패키지를 둔다.

```text
my-plugin/
├── plugin.json
├── README.md                    # 목적, 스킬 관계, 실행 계약
├── pyproject.toml               # requires-python >=3.12. 외부 의존성이 있을 때만
├── src/my_plugin/
│   ├── __main__.py              # 진입점 하나. python3 -m my_plugin <명령>
│   ├── commands/                # 명령 하나 = 스킬 하나
│   └── core/                    # 공통 로직과 스킬 사이 계약
├── skills/
│   └── skill-name/SKILL.md      # 명령 한 줄로 호출. 분기 판단은 description과 본문이 맡는다
└── tests/                       # 로컬 전용. git에 올리지 않음(.gitignore)
```

- 외부 패키지가 꼭 필요하면 스크립트 머리에 PEP 723 메타데이터(`# /// script`, `requires-python`, `dependencies`)를 적고 `uv run`으로 실행한다.
- `.venv`를 플러그인 폴더에 만들지 않는다. Claude와 Codex는 플러그인을 버전별 캐시 폴더에 설치하고, 업데이트하면 그 폴더를 통째로 바꾼다.
- `requirements.txt`, `.python-version`, `bootstrap.py`는 두지 않는다. 버전과 의존성 정보는 한 곳에만 둔다.
- 플러그인 루트의 `src/`를 참조하는 스킬은 플러그인 단위로 설치해야 동작한다. 스킬 폴더만 따로 복사하면 동작하지 않는다.

## 매니페스트 동기화

손으로 고치는 매니페스트는 각 플러그인의 루트 `plugin.json` 하나다. 나머지는 스크립트가 만든다.

```text
plugin.json                          # 원본. $schema 필수, 표준 키만, 이름은 [a-z0-9-]
.claude-plugin/plugin.json           # 생성. Claude Code
.codex-plugin/plugin.json            # 생성. Codex UI. interface는 이 파일에서 직접 고치면 유지됨
.cursor-plugin/plugin.json           # 생성. agents/가 있는 플러그인만
../.claude-plugin/marketplace.json   # 생성. Claude·Cursor·Grok(Codex도 읽음)
../.agents/plugins/marketplace.json  # 생성. Codex
```

```bash
python3 scripts/sync_manifests.py          # 루트 plugin.json을 고친 뒤 실행
python3 scripts/sync_manifests.py --check  # 커밋 전 확인. tests/test_manifests.py도 같은 검사를 한다
```

- `"skills": "./skills/"`는 루트에 넣지 않는다. 표준 스키마에 없는 키이고, `skills/`는 자동으로 탐색된다.
- 역도메인 폴더(`io.github.*/`)는 어느 호스트도 읽지 않는다. 만들지 않는다.
- 비공개 플러그인은 `UNLISTED`에 넣으면 마켓플레이스 목록에서 빠진다.
