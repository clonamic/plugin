# clonamic-harness

AI 코딩 에이전트의 작업 순서를 잡아 주는 규칙 플러그인이다. 요청 해석, 승인, 실행, 증거 보고 순서를 지키게 한다.

## 왜 만들었나

에이전트에게 일을 맡기면 시키지 않은 일까지 하거나, 끝나지 않은 일을 끝났다고 말하거나, 사소한 일마다 "계속할까요?"라고 묻는 일이 잦다. 승인은 꼭 필요한 곳에서만 받고, 그 안에서는 끝까지 맡길 수 있게 하려고 만들었다.

## 기능

- 요청 해석: 요청을 항목별로 나누고, 시키지 않은 작업을 걸러 낸다.
- 승인: 바꾸기 전에 무엇을 어떻게 왜 바꾸는지 적은 명세서로 승인받는다. 승인은 작업당 최대 두 번이다.
- 팀 구성: 효과가 비용보다 클 때만 독립 검토자 같은 보조 에이전트를 쓴다.
- 마무리: 마지막 변경 뒤에 모든 항목을 다시 확인하고, 결론부터 쓴 보고서를 낸다.

## 장점

- 한 번 승인하면 범위 안에서는 다시 묻지 않고 끝까지 간다.
- 완료 보고에 새로 확인한 증거를 담는다.
- 사용자 환경과 프로젝트 파일을 승인 없이 바꾸지 않는다.

## 사용법

- Claude Code: `/plugin marketplace add clonamic/plugin` 후 `/plugin install clonamic-harness@clonamic`
- Codex: `codex plugin marketplace add clonamic/plugin` 후 `codex plugin add clonamic-harness@clonamic`
- Grok: `grok plugin install https://github.com/clonamic/plugin#clonamic-harness --trust`

규칙을 항상 켜려면 이 폴더의 `AGENTS.md`를 `~/.clonamic/AGENTS.md`로 복사하고 도구에 연결한다.

- Claude Code: `~/.claude/CLAUDE.md`에 `@~/.clonamic/AGENTS.md`를 넣는다.
- Codex: `ln -s ~/.clonamic/AGENTS.md ~/.codex/AGENTS.md`
- Grok: `ln -s ~/.clonamic/AGENTS.md ~/.grok/AGENTS.md`

### 개인 지침 추가

개인 지침은 `AGENTS.md`에 넣지 않고 따로 적는다. 파일이 있으면 읽고, 없으면 건너뛴다.

- Claude Code: `~/.clonamic/claude_add.md`
- 그 밖의 도구: `~/.clonamic/agent_add.md`

내용이 같으면 심볼릭 링크로 연결한다.

```bash
ln -s ~/.clonamic/agent_add.md ~/.clonamic/claude_add.md
```

## 버전 기록

- v2.0.0: 작업 규칙을 플러그인 하나로 통합
- v2.1.0: 승인 횟수를 최대 두 번으로 수정, 독립 검토 에이전트 추가
- v2.2.0: 보고 형식을 결론 우선으로 수정
- v2.3.0: 프로젝트 파일 변경 규칙 강화
- v2.3.1: 커밋 규칙 추가
- v2.4.0: 명세서에 항목별 방법과 이유 추가
- v2.5.0: 명세서에 변경 흐름과 영향 범위 추가, 개인 지침 파일 추가
