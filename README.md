# 플러그인 규칙 : 플러그인 표준 1.0.0 을 따른다.

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
