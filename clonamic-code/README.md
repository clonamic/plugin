# clonamic-code

새 시스템이나 큰 리팩터링을 시작하기 전에 모듈 구조를 설계하는 플러그인이다.

## 왜 만들었나

구조를 정하지 않고 코드부터 쓰면 파일 하나가 여러 일을 떠안고, 나중에 고칠 때 어디까지 영향이 가는지 알기 어렵다. 왜 나눴는지 근거가 남는 설계를 먼저 하려고 만들었다.

## 기능

- 지금 코드와 요구사항을 읽고 모듈을 나눌 근거를 정리한다.
- 모듈마다 맡을 일과 입력, 출력을 적는다.
- 기존 코드는 옮길 순서까지 잡는다.

## 장점

- 나눈 근거가 남아서 나중에 구조를 바꿀 때 판단하기 쉽다.
- 작은 수정이나 단순한 구조 질문에는 끼어들지 않는다.

## 사용법

- Claude Code: `/plugin marketplace add clonamic/plugin` 후 `/plugin install clonamic-code@clonamic`
- Codex: `codex plugin marketplace add clonamic/plugin` 후 `codex plugin add clonamic-code@clonamic`
- Grok: `grok plugin install https://github.com/clonamic/plugin#clonamic-code --trust`

설치한 뒤 채팅으로 요청하면 된다.

```text
결제 모듈을 어떻게 나눌지 설계해 줘
이 서버를 큰 틀에서 리팩터링하려는데 구조부터 잡아 줘
```

## 버전 기록

- v2.0.0: 코드 관련 기능을 역할별로 재구성
- v2.1.0: 모듈 설계만 남기고 변경 규칙은 clonamic-harness로 이동
