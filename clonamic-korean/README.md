# clonamic-korean

이력서, 포트폴리오, 자기소개서, 보고서, 게시글, 기술 문서를 한국어로 새로 쓰거나 다듬는 플러그인이다.

## 왜 만들었나

AI가 쓴 한국어는 번역투가 많고 문장 호흡이 단조롭다. 그렇다고 통째로 다시 쓰게 하면 숫자나 사실이 바뀌거나 내 말투가 사라진다. 사실은 그대로 두고 어색한 부분만 고치려고 만들었다.

## 기능

- 다듬기: 번역투, 상투적인 표현, 단조로운 문장 호흡을 가볍게 또는 깊게 고친다.
- 새로 쓰기: 문서 종류에 맞춰 초안을 쓴다.
- 문체 맞추기: 내가 쓴 글의 말투에 맞춘다.
- 맞춤법과 글자 수: 맞춤법, 띄어쓰기를 고치고 글자 수를 맞춘다.
- 진단: 글은 고치지 않고 문제만 알려 준다.

## 장점

- 숫자, 고유명사, 인용, 높임 수준을 그대로 둔다.
- 빈 곳은 지어내지 않고 확인이 필요하다고 표시한다.
- 고친 뒤 원문과 대조해 빠지거나 바뀐 내용을 확인한다.

## 사용법

- Claude Code: `/plugin marketplace add clonamic/plugin` 후 `/plugin install clonamic-korean@clonamic`
- Codex: `codex plugin marketplace add clonamic/plugin` 후 `codex plugin add clonamic-korean@clonamic`
- Grok: `grok plugin install https://github.com/clonamic/plugin#clonamic-korean --trust`

명령을 직접 입력했을 때만 실행한다.

```text
/clonamic-korean 이 문단 자연스럽게 고쳐 줘
/clonamic-korean 깊게 ./portfolio.md
/clonamic-korean 자기소개서 1번 문항 500자로 써 줘
```

## 버전 기록

- v1.0.0: 첫 공개
- v1.0.1: 다듬기 절차를 명령 하나로 통합
- v2.0.0: 역할별 플러그인 구성에 맞게 수정
- v2.1.0: 맞춤법, 높임말, 번역투 점검과 글자 수 맞추기 추가
- v2.1.1: 문서 표현 수정
- v2.2.0: 굳어진 용어 유지, 문장 흐름 수정
