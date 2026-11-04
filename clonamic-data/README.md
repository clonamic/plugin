# clonamic-data

데이터셋을 만들고, 정리하고, Hugging Face에 올리는 플러그인이다. 파인튜닝 데이터도 다룬다.

## 왜 만들었나

큰 데이터는 받다가 디스크가 차거나, 다 만든 뒤에야 형식 오류를 발견하는 일이 잦다. 시작 전에 점검하고 올리기 전에 검증하는 순서를 지키려고 만들었다.

## 기능

- 작업 규모에 맞춰 저장 공간을 미리 확인한다.
- 큰 데이터는 전부 받지 않고 스트리밍으로 처리한다.
- JSONL 형식을 검증한다.
- Hugging Face에 올린다. 저장소는 비공개가 기본이다.

## 장점

- 긴 작업이 중간에 실패할 위험이 줄어든다.
- 작업 규모에 맞춰 점검량을 조절한다.

## 사용법

- Claude Code: `/plugin marketplace add clonamic/plugin` 후 `/plugin install clonamic-data@clonamic`
- Codex: `codex plugin marketplace add clonamic/plugin` 후 `codex plugin add clonamic-data@clonamic`
- Grok: `grok plugin install https://github.com/clonamic/plugin#clonamic-data --trust`

설치한 뒤 채팅으로 요청하면 된다.

```text
이 CSV를 파인튜닝용 JSONL로 바꾸고 검증해 줘
정리한 데이터셋을 Hugging Face에 비공개로 올려 줘
```

## 버전 기록

- v2.0.0: 데이터 기능을 역할별로 재구성
