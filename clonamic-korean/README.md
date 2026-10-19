# clonamic-korean

이력서, 포트폴리오, 자기소개서, 보고서, 게시글, 기술 문서의 한국어를 새로 쓰거나 다듬는 스킬이다. `/clonamic-korean`을 직접 입력했을 때만 실행된다.

```text
/clonamic-korean 이 문단 AI 티 빼줘
/clonamic-korean 깊게 ./docs/portfolio.md
/clonamic-korean 자기소개서 1번 문항 500자로 써줘
```

숫자, 고유명사, 인용, 서법, 문체 높낮이는 그대로 유지하고 어색한 부분만 다듬는다. 정착된 개념어는 그대로 살리고 번역투 서술어와 조사, 단조로운 문장 호흡을 자연스러운 한국어로 고친다. 사용법과 세부 기준은 `skills/clonamic-korean/SKILL.md`에 정리되어 있으며, 원문과 수정본의 대조는 스킬 폴더의 `scripts/check_revision.py`(Python 3.12 이상, 표준 라이브러리만 사용)가 맡는다.
