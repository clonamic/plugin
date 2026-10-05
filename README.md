# 플러그인 규칙 : 플러그인 표준 1.0.0 을 따른다.
- claude만 다른 규격을 사용하므로 필요에 따라 추가 폴더로 구조 명시. 

```text
plugin-name/
├── plugin.json                      # 필수. Agent Plugins 1.0.0 매니페스트
├── skills/                          # 스킬 고정 위치. 직계 자식만 탐색
│   └── skill-name/
│       ├── SKILL.md                 # 필수. YAML frontmatter + 지시문
│       ├── scripts/                 # 선택. 실행 코드
│       ├── references/              # 선택. 필요 시 읽는 문서
│       └── assets/                  # 선택. 템플릿·리소스
├── mcp.json                         # 선택. MCP 서버 설정
├── com.example.client/              # 선택. 호스트 확장(역도메인 디렉터리)
├── LICENSE                          # 선택. 라이선스
└── CHANGELOG.md                     # 선택. 변경 기록
```


### 변형
```text
my-plugin/
├── README.md                      # 플러그인 목적, 스킬 관계, 트리, 설치, 실행 계약
├── plugin.json                    # 1.0.0. Codex·Grok이 읽음
├── .python-version                # 3.12
├── pyproject.toml                 # requires-python >=3.12,<3.13
├── requirements.txt
├── .gitignore                     # .venv/
├── scripts/
│   └── bootstrap.py               # .venv 생성 후 requirements 설치
├── .claude-plugin/
│   └── plugin.json                # 클로드 전용. name은 루트와 동일
├── src/plugin_core/
│   ├── __init__.py
│   ├── __main__.py                # 단일 진입점
│   ├── router.py                  # 분기 결정은 여기만
│   ├── contracts.py               # 스킬 간 JSON 계약
│   ├── branches/
│   │   ├── intake.py
│   │   ├── path_a.py
│   │   └── path_b.py
│   └── lib/                       # 공통 유틸. 스킬이 직접 호출하지 않음
├── skills/
│   ├── intake/
│   │   ├── SKILL.md               # 정규화 후 route 호출, a/b로 넘김
│   │   └── examples/sample.json
│   ├── path-a/
│   │   └── SKILL.md               # run --branch a 만
│   └── path-b/
│       └── SKILL.md               # run --branch b 만
└── tests/
    ├── test_router.py
    └── fixtures/
```
### 매니페스트 동기화
손으로 고치는 매니페스트는 각 플러그인의 루트 `plugin.json` 하나다. 나머지는 스크립트가 만든다.

```text
plugin.json                        # 원본. $schema 필수, 표준 키만, 이름은 [a-z0-9-]
.claude-plugin/plugin.json         # 생성. Claude Code
.codex-plugin/plugin.json          # 생성. Codex UI. interface는 여기서 직접 고치고 유지됨
.cursor-plugin/plugin.json         # 생성. agents/가 있는 플러그인만
../.claude-plugin/marketplace.json # 생성. Claude·Cursor·Grok(Codex도 읽음)
../.agents/plugins/marketplace.json# 생성. Codex
```

```bash
python3 scripts/sync_manifests.py          # 루트 plugin.json을 고친 뒤 실행
python3 scripts/sync_manifests.py --check  # 커밋 전 확인. tests/test_manifests.py도 같은 검사
```

- `"skills": "./skills/"`는 루트에 넣지 않는다. 표준 스키마에 없고, `skills/`는 자동 탐색된다.
- 역도메인 폴더(`io.github.*/`)는 어느 호스트도 읽지 않는다. 만들지 않는다.
- 비공개 플러그인은 `UNLISTED`에 넣으면 마켓플레이스에서 빠진다.
