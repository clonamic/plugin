# clonamic-memory

정보와 메모를 내 컴퓨터에 저장하고 필요할 때 꺼내 쓰는 플러그인이다. 요청했을 때만 작동한다.

## 왜 만들었나

에이전트의 자동 기억은 무엇이 저장됐는지 알기 어렵고, 지난 내용이 지금 작업에 끼어들기도 한다. 언제 무엇을 저장하고 꺼낼지 내가 정하려고 만들었다.

## 기능

- 저장과 검색: 내용을 출처와 함께 저장하고 검색어로 찾는다.
- 삭제와 정리: 항목을 지우고 기한이 지난 내용을 정리한다.
- 연결: 항목끼리 관계를 이어 두고 연결된 항목을 함께 찾는다.
- 백업과 복원: 저장소를 파일로 백업하고 되살린다.

## 장점

- 요청 없이 기억을 저장하거나 다른 작업에 끌어오지 않는다.
- 저장한 내용마다 출처가 남아 어디서 온 정보인지 알 수 있다.
- 데이터를 내 컴퓨터에만 저장한다.

## 사용법

- Claude Code: `/plugin marketplace add clonamic/plugin` 후 `/plugin install clonamic-memory@clonamic`
- Codex: `codex plugin marketplace add clonamic/plugin` 후 `codex plugin add clonamic-memory@clonamic`
- Grok: `grok plugin install https://github.com/clonamic/plugin#clonamic-memory --trust`

설치한 뒤 채팅으로 요청하면 된다.

```text
이 결정 기억해 둬
지난번에 저장한 배포 메모 찾아 줘
이 메모 지워 줘
```

## 버전 기록

- v1.0.0: 첫 공개
- v1.1.0: 스킬 안내와 실행 규칙 수정
