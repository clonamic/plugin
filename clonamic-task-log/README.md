# clonamic-task-log

그날 내가 한 git 작업을 포트폴리오에 옮길 수 있는 한국어 작업 기록으로 정리하는 플러그인이다.

## 왜 만들었나

작업 기록은 미루면 기억이 흐려지고, 커밋 목록만으로는 어떤 문제를 왜 그렇게 풀었는지 남지 않는다. 포트폴리오를 쓸 때 다시 뒤지지 않도록 그날그날 읽을 수 있는 기록으로 남기려고 만들었다.

## 기능

- 작업 기록: 그날의 문제, 접근, 결과를 프로젝트 밖의 사람도 알아보게 쓴다.
- 저장: 로컬 파일로 남기고 Notion 페이지에도 올린다.
- 진행 현황: 중요도를 매기고 기능별 진행률을 추정해 보여 준다.
- 포트폴리오 정리: 쌓인 기록을 포트폴리오용으로 다시 묶는다.

## 장점

- 파일 이름, 경로, 커밋 해시, 비밀 값은 저장 전에 걸러 낸다.
- 내가 한 커밋만 대상으로 삼는다.
- 명령을 직접 입력했을 때만 실행한다.

## 사용법

- Claude Code: `/plugin marketplace add clonamic/plugin` 후 `/plugin install clonamic-task-log@clonamic`
- Codex: `codex plugin marketplace add clonamic/plugin` 후 `codex plugin add clonamic-task-log@clonamic`
- Grok: `grok plugin install https://github.com/clonamic/plugin#clonamic-task-log --trust`

날짜를 생략하면 오늘 기록을 쓴다.

```text
/clonamic-task-log
/clonamic-task-log 어제
/clonamic-task-log 10-01~10-03
/clonamic-task-log 포트폴리오 정리
/clonamic-task-log 설정
```

## 버전 기록

- v1.0.0: 첫 공개
- v1.0.1: 설정 파일 저장 방식 수정
- v1.0.2: 작업 항목 합계 계산 추가
- v1.1.0: 날짜 지정 추가, 기록 내용 수정
- v1.1.1: 기록 길이 축소, 삭제 명령 추가
- v1.1.2: 쓰기 권한 사전 점검 추가
- v1.1.3: 작업 메모 품질 기준 추가
- v1.2.0: 기록을 이야기 형식으로 수정
- v1.2.1: 제목 길이와 결정 문구 수정
- v1.4.0: 여러 저장소 묶음 지원, 완료 정리 추가
- v1.4.1: 문서 표현 수정
- v1.4.2: Grok 신뢰 설정을 사용자가 직접 하도록 수정
