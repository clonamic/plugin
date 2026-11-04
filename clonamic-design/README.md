# clonamic-design

화면 디자인, 디자인 검토, 브라우저 점검, 포스터와 손그림 다이어그램 작업을 맡는 플러그인이다.

## 왜 만들었나

AI에게 화면을 맡기면 어느 서비스에서나 본 듯한 비슷한 결과가 나오고, 실제 브라우저에서 깨져도 모르고 넘어가기 쉽다. 방향을 먼저 정하고, 결과는 실제 화면으로 확인하려고 만들었다.

## 기능

- UI 디자인: 주제에 맞는 분위기, 글꼴, 색, 레이아웃, 움직임을 정해 화면을 만든다. Figma 프레임이나 스크린샷을 보고 구현하기도 한다.
- UI 검토: 시각 위계, 접근성, 반응형, 상호작용 상태, 문구를 실제 화면 기준으로 점검한다.
- 브라우저 점검: 화면 크기별 스크린샷, 사용자 흐름, 콘솔 오류, 키보드 조작을 확인한다.
- 시각물: 포스터, 표지, 코드로 그린 그림을 PNG, PDF, SVG로 만든다.
- 다이어그램: 수정 가능한 손그림 스타일 Excalidraw 파일을 만든다.

## 장점

- 지금 쓰는 에이전트 도구와 브라우저를 그대로 쓰므로 따로 설치할 엔진이 없다.
- 검토 의견에 실제 화면 근거와 측정한 명암비를 붙인다.
- 다이어그램은 만든 뒤 검증기로 겹침과 글자 넘침을 확인한다.

## 사용법

- Claude Code: `/plugin marketplace add clonamic/plugin` 후 `/plugin install clonamic-design@clonamic`
- Codex: `codex plugin marketplace add clonamic/plugin` 후 `codex plugin add clonamic-design@clonamic`
- Grok: `grok plugin install https://github.com/clonamic/plugin#clonamic-design --trust`

설치한 뒤 채팅으로 요청하면 된다.

```text
이 서비스 랜딩 페이지 디자인해 줘
이 화면 접근성까지 검토해 줘
로그인 흐름을 브라우저로 확인해 줘
행사 포스터 만들어 줘
배포 구조를 손그림 느낌으로 그려 줘
```

## 버전 기록

- v2.0.0: 디자인 기능을 역할별 스킬 5개로 재구성
