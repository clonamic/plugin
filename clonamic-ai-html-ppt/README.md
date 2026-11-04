# clonamic-ai-html-ppt

슬라이드와 문서를 만드는 로컬 편집기다. Figma처럼 자유롭게 배치하고, 평소 쓰던 AI에게 같은 화면을 맡겨 함께 고친다.

## 왜 만들었나

PPT를 만들 때마다 유료 프로그램을 쓰고 싶지 않았고, 정해진 틀에 갇히는 것도 불편했다. 디자인 도구에 AI를 연결해 봐도 고칠 때마다 결과를 덮어쓰고 토큰도 많이 들었다. 그래서 사람과 AI가 요소 하나 단위로 같은 문서를 고치는 편집기를 만들었다.

## 기능

- 편집: 도형, 이미지, 표, 텍스트, 오토 레이아웃, 효과를 캔버스에서 다룬다.
- AI 수정: 페이지 전체를 채팅으로 요청하거나, 요소를 골라 한 줄로 요청한다.
- 페이지 규격: 16:9, 4:3, A4 등을 고르고 가로와 세로를 바꾼다.
- 발표: 전체 화면 발표와 발표자 보기를 쓴다.
- 내보내기: 현재 페이지, 고른 페이지, 전체를 PDF로 저장한다.

## 장점

- 별도 AI 서비스나 API 키 없이 Claude Code, Codex, Cursor, Grok을 그대로 쓴다.
- AI는 바꿀 요소만 고치므로 방금 손으로 고친 내용을 덮어쓰지 않는다.
- AI에게 맡긴 요청은 알림의 `되돌리기` 한 번으로 통째로 되돌린다.
- 화면에서 본 그대로 PDF가 나오고, PDF의 글자도 선택하고 검색할 수 있다.
- 내 컴퓨터에서만 돌고, 탭을 모두 닫으면 스스로 꺼진다.

## 사용법

- Claude Code: `/plugin marketplace add clonamic/plugin` 후 `/plugin install clonamic-ai-html-ppt@clonamic`
- Codex: `codex plugin marketplace add clonamic/plugin` 후 `codex plugin add clonamic-ai-html-ppt@clonamic`
- Grok: `grok plugin install https://github.com/clonamic/plugin#clonamic-ai-html-ppt --trust`

명령 뒤에 만들고 싶은 것을 적으면 편집기가 열리고 그 말이 첫 요청이 된다.

```text
/clonamic-ai-html-ppt 신제품 발표 10장
/clonamic-ai-html-ppt A4 세로 보고서
```

## 버전 기록

- v0.1.0: 첫 공개
