# clonamic-documents

한글(HWPX) 문서와 PowerPoint 발표 자료를 만들고 고치는 플러그인이다.

## 왜 만들었나

한국에서는 한글 문서를 자주 주고받는데, AI 도구로 다루기가 까다롭다. 발표 자료도 파일만 만들고 끝내면 글자가 넘치거나 겹친 채로 나오기 쉽다. 바로 쓸 수 있는 파일로 만들려고 두 형식을 묶었다.

## 기능

- HWPX: 문서를 만들고, 읽고, 글, 표, 이미지를 고친다. 예전 HWP 파일도 변환한다.
- PPTX: 16:9 발표 자료를 만들거나 고친다. 내용 흐름을 먼저 잡고 슬라이드를 만든다.

## 장점

- HWPX는 고친 뒤 구조 검증기로 파일 구조를 확인한다.
- PPTX는 슬라이드를 이미지로 그려 보고 넘침과 겹침을 고친 뒤 넘겨준다.
- PPTX 슬라이드 요소는 PowerPoint에서 직접 고칠 수 있다.

## 사용법

- Claude Code: `/plugin marketplace add clonamic/plugin` 후 `/plugin install clonamic-documents@clonamic`
- Codex: `codex plugin marketplace add clonamic/plugin` 후 `codex plugin add clonamic-documents@clonamic`
- Grok: `grok plugin install https://github.com/clonamic/plugin#clonamic-documents --trust`

설치한 뒤 채팅으로 요청하면 된다.

```text
이 양식 HWPX에 표 내용을 채워 줘
회사 소개 발표 자료 10장 만들어 줘
```

## 버전 기록

- v2.0.0: 문서 기능을 역할별로 재구성
