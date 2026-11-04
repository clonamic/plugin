# clonamic-create-agent

에이전트 파이프라인을 그래프로 설계하고 한국어 설계 문서로 내보내는 플러그인이다. 코드는 만들지 않는다.

## 왜 만들었나

에이전트 자동화는 여러 기능이 이어지는 파이프라인이라 설계가 결과를 좌우한다. 글로만 설계하면 흐름이 한눈에 안 보이고, 문서만 보고 같은 결과를 다시 만들기도 어렵다. 흐름을 보면서 고치고, 문서만으로 구현할 수 있는 설계를 남기려고 만들었다.

## 기능

- 설계 편집기: 로컬 웹 화면에서 에이전트와 그 안의 단계를 그래프로 보고 고친다.
- 대화 설계: AI와 대화하면서 그래프를 그리고 입력 칸을 채운다.
- 설계 검토: 검토 챗봇이 설계를 평가하고 근거와 함께 수정안을 낸다.
- 문서 내보내기: 구현 방식에 묶이지 않는 한국어 설계 문서를 만든다.

## 장점

- 구현하는 사람이나 AI가 문서만 보고 시작할 수 있게 입력, 처리, 출력을 적는다.
- 특정 프레임워크 용어를 쓰지 않아 구현 도구를 나중에 골라도 된다.
- 로컬에서 돌아서 별도 서버가 필요 없다.

## 사용법

- Claude Code: `/plugin marketplace add clonamic/plugin` 후 `/plugin install clonamic-create-agent@clonamic`
- Codex: `codex plugin marketplace add clonamic/plugin` 후 `codex plugin add clonamic-create-agent@clonamic`
- Grok: `grok plugin install https://github.com/clonamic/plugin#clonamic-create-agent --trust`

명령 뒤에 프로젝트 이름이나 만들고 싶은 것을 적는다.

```text
/clonamic-create-agent 고객 문의 분류 자동화
```

## 버전 기록

- v0.1.0: 그래프 편집기와 설계 문서 내보내기 추가
- v0.2.0: 세부 단계 설계, 수정 카드, 검토 화면 추가
- v0.4.0: 저장 병합, 초안 내보내기 추가
