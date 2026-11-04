# clonamic-executor

지금 쓰는 에이전트에서 다른 에이전트 CLI(Claude, Grok, Hermes)에 질문을 한 번 보내고 답을 받아 오는 플러그인이다.

## 왜 만들었나

판단이 갈릴 때 다른 도구의 의견을 듣고 싶어도, 터미널을 옮겨 다니며 내용을 복사하기는 번거롭다. 그렇다고 에이전트끼리 마음대로 일을 넘기면 어디서 무엇을 바꿨는지 추적하기 어렵다. 그래서 읽기 전용 질문 한 번으로 범위를 좁혔다.

## 기능

- 지정한 CLI에 요청 하나를 보낸다.
- 결과를 JSON으로 돌려받는다.

## 장점

- 다른 CLI를 읽기 전용으로 실행해 파일을 바꾸지 않는다.
- 응답 시간과 출력 크기를 제한하고, 비밀 값은 가린다.
- 요청을 다시 다른 에이전트에게 넘기는 연쇄 호출을 막는다.

## 사용법

- Claude Code: `/plugin marketplace add clonamic/plugin` 후 `/plugin install clonamic-executor@clonamic`
- Codex: `codex plugin marketplace add clonamic/plugin` 후 `codex plugin add clonamic-executor@clonamic`
- Grok: `grok plugin install https://github.com/clonamic/plugin#clonamic-executor --trust`

설치한 뒤 CLI 이름을 넣어 요청하면 된다.

```text
이 설계를 grok한테 한번 물어봐 줘
```

## 버전 기록

- v2.0.0: 다른 CLI 호출 기능을 플러그인 하나로 통합
