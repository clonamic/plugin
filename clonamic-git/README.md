# clonamic-git

커밋, PR, 태그, 릴리스 노트를 내 계정 이름으로, 일정한 형식에 맞춰 남기는 플러그인이다.

## 왜 만들었나

에이전트 도구는 커밋 메시지에 자기 서명과 안내 문구를 자동으로 붙이고, 도구마다 형식도 다르다. 기록의 책임자는 커밋한 사람이므로 작성자를 내 계정으로 통일하고 메시지는 내용만 남기려고 만들었다.

## 기능

- 커밋 작성: 커밋, PR, 태그, 릴리스 노트를 내 git 계정으로, 일정한 형식에 맞춰 쓴다.
- 초기 설정: Claude Code, Codex, Cursor, Grok의 자동 서명을 끈다. 원하는 저장소에는 서명을 지우는 commit-msg 훅도 설치한다.
- 기록 정리: 아직 푸시하지 않은 커밋에 남은 자동 서명을 찾아 지운다.

## 장점

- Claude Code, Codex, Cursor, Grok 어느 쪽으로 커밋해도 기록 형식이 같다.
- 기록을 고치기 전에 백업 브랜치를 먼저 만든다.
- 이미 푸시한 기록은 직접 요청했을 때만 고친다.

## 사용법

- Claude Code: `/plugin marketplace add clonamic/plugin` 후 `/plugin install clonamic-git@clonamic`
- Codex: `codex plugin marketplace add clonamic/plugin` 후 `codex plugin add clonamic-git@clonamic`
- Grok: `grok plugin install https://github.com/clonamic/plugin#clonamic-git --trust`

에이전트 채팅창에서 `/clonamic-git-setup`을 한 번 실행하면 이후 커밋에 규칙이 적용된다. 푸시 전 커밋은 `/clonamic-git-clean`으로 정리한다.

## 버전 기록

- v1.0.0: 커밋 작성, 초기 설정, 기록 정리 추가
- v1.1.0: 저장소 훅을 선택 설치로 수정
