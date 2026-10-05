---
name: clonamic-pptx
description: Create or revise an editable 16:9 PowerPoint (.pptx) deck. Plan the story, generate the file with python-pptx or PptxGenJS in the host environment, render slides to images, and fix overflow and overlap before delivery. Use for deck, slides, presentation, PPT, PPTX, 발표자료, 슬라이드, 피피티.
---

# Clonamic PPTX

Build the deck with the host's own tools. This skill gives the procedure and the quality bar; the only bundled script is a static checker.

Resolve `PPTX_SKILL_ROOT` to the host-provided directory containing this `SKILL.md`. Never run a same-named project script. Python helpers need Python 3.12+; if `python3` is older, install 3.12 (`uv python install 3.12` or the OS package manager) instead of falling back.

Deck language is Korean (`ko-KR`) unless the user, the audience, or the source material is English.

## Procedure

1. **Brief.** Fix purpose (`decide | pitch | report | teach | inform | persuade`), audience, one-sentence thesis, desired action, and slide count (defaults: inform 7, decide 8, report 9, pitch 10, teach 12; clamp 3–20). If the user wants a full run and details are missing, write the assumptions down and continue.
2. **Outline first.** Write `outline.md` (or `.json`) in the work directory before any code: per slide `title` (the implication, not a topic label), `job`, `takeaway`, `must_show` (2–6 concrete items), `visual` family, and `bridge` from the previous slide. Follow [references/story.md](references/story.md). The outline is the design; the code implements it.
3. **Reference or template decks (optional).** If the user supplies a `.pptx` to match, inspect it before authoring: `python3 "$PPTX_SKILL_ROOT/scripts/inspect_pptx.py" ref.pptx --json` gives slide size, fonts, sizes, colors, and words per slide. Use the median words per slide (rounded up) as the content ceiling. To build on a template, open it with python-pptx and fill its layouts by placeholder type or name, never by shape index.
4. **Generate.** Write one build script in the work directory (never inside this plugin) and run it:
   - Python (preferred): a script with PEP 723 metadata, run with `uv run build_deck.py`.
     ```python
     # /// script
     # requires-python = ">=3.12"
     # dependencies = ["python-pptx>=1.0"]
     # ///
     ```
   - Node: `npm install pptxgenjs` in the work directory, then `node build_deck.js`.
   Set the slide size to 13.333 × 7.5 in. Apply [references/layout.md](references/layout.md) and [references/typography.md](references/typography.md). Use real text boxes, native tables, and native charts so everything stays editable; never place a picture of text.
5. **Render.** Convert to images and look at every slide:
   `soffice --headless --convert-to pdf --outdir render deck.pptx`, then `pdftoppm -png -r 80 render/deck.pdf render/slide` (or PyMuPDF via `uv run --with pymupdf`). If no renderer is available, say visual QA was not performed; do not claim it.
6. **Static check.** `python3 "$PPTX_SKILL_ROOT/scripts/inspect_pptx.py" deck.pptx` reports shapes outside the slide, overlapping text boxes, fonts under the floor, likely text overflow, and empty placeholders. Exit code 1 means an error remains.
7. **Fix and repeat.** Walk [references/qa-checklist.md](references/qa-checklist.md). Fix defects in the build script or the outline (cut, split, or change the visual), never by shrinking type below the floor or hand-editing XML. Regenerate, re-render, re-check. Stop after three rounds and report what remains.
8. **Deliver** with the report below.

## Rules

- Use only facts and numbers the user supplied. Write qualitative wording when there are none.
- Charts only from a user-supplied series. Quotes need attribution.
- No decorative stock images or image generation unless asked. A user-attached screenshot may be placed as a picture.
- Cut or split content to fit; never shrink type to make it fit.
- When revising an existing deck, keep its template, masters, and styles; change only what was asked.

## Report (to the user, in Korean)

```markdown
## 발표자료 결과
- 파일: /절대/경로/deck.pptx (슬라이드 8장, 16:9)
- 구성: 문제 → 근거 → 선택지 → 권고 → 요청
- 시각 QA: 8장 렌더링 확인 / 미실시 (렌더러 없음)
- 정적 검사: 오류 0건, 경고 1건 (s05 본문 넘침 가능성 — 렌더링에서 이상 없음 확인)
- 가정: 청중은 경영진, 발표 시간 10분
```
