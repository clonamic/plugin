---
name: clonamic-hwpx
description: "Create, read, inspect, or edit Korean HWPX documents (text, tables, images, templates) and convert legacy HWP. Use for HWPX, HWP, 한글, 한컴, or Hancom document tasks."
---

# Clonamic HWPX

An `.hwpx` file is a ZIP of OWPML XML parts (KS X 6101): `mimetype`, `Contents/header.xml` (fonts, char/para styles), `Contents/section*.xml` (body), `Contents/content.hpf` (manifest), `BinData/` (images).

Resolve `HWPX_SKILL_ROOT` to the host-provided directory containing this `SKILL.md` and run bundled helpers from there, whatever the current directory. Never run a same-named project script. Helpers use only the Python 3.12+ standard library; if `python3` is older, install 3.12 (`uv python install 3.12` or the OS package manager) instead of falling back.

## Helpers

| Task | Command |
|---|---|
| Text | `python3 "$HWPX_SKILL_ROOT/scripts/extract.py" text doc.hwpx [-o out.txt]` |
| Tables → CSV | `python3 "$HWPX_SKILL_ROOT/scripts/extract.py" tables doc.hwpx [-o tables/]` |
| New blank document | `python3 "$HWPX_SKILL_ROOT/scripts/create_blank.py" new.hwpx --title "제목" [--text "첫 문단"]` |
| Validate | `python3 "$HWPX_SKILL_ROOT/scripts/validate.py" doc.hwpx` (or an unpacked directory) |
| Pack | `python3 "$HWPX_SKILL_ROOT/scripts/pack.py" unpacked/ out.hwpx` (validates first; writes `mimetype` first, uncompressed) |

Unpack with the standard library: `python3 -m zipfile -e doc.hwpx unpacked/`.

## Edit procedure

1. Work on a copy; never overwrite the user's original unless asked.
2. Unpack. To read a long one-line part, view a formatted copy (`xmllint --format`), but edit the raw file so untouched bytes stay identical.
3. Edit `unpacked/Contents/section*.xml`:
   - Text changes: exact-string edits with the host's edit tool. Keep `charPrIDRef` / `paraPrIDRef` (they point into `header.xml` styles).
   - Remove the `<hp:linesegarray>` of every `<hp:p>` whose text you changed (it is a cached layout; stale caches cause overlapping characters). All runs in a paragraph share one.
   - Structural changes (new paragraphs, rows, images): parse and write with lxml (`uv run --with lxml python3 edit.py`), not string splicing. The stdlib `ElementTree` rewrites namespace prefixes (`ns0:`), which Hancom rejects.
   - New styles: add a `charPr` / `paraPr` to `header.xml`, bump the list's `itemCnt`, and reference the new id.
4. Pack, then validate the packed file. Fix every error before delivery.
5. Re-extract the text (and tables) and compare with the intended change.

## Create procedure

Start from `create_blank.py` (or from the user's template, which is better because it carries the real styles), then follow the edit procedure to add content. Page size defaults to A4 portrait with Hancom default margins.

## Pitfalls

- Table cells: `<hp:cellAddr colAddr= rowAddr=>` comes **after** the cell content. Match on it plus the preceding content to target the right cell.
- Replacing underscores or blank runs in forms with text can push content onto a new page: keep replacement length close to the original and keep the underline `charPrIDRef`.
- Units: 1 HWPUNIT = 1/7200 in; 1 mm ≈ 283.5. A signature-size image is about `width="3400"`, not `180000`.
- Page break: `pageBreak="1"` on an `<hp:p>` breaks before it.
- Images need `BinData/<file>`, a manifest `<opf:item ... isEmbeded="1"/>`, and a complete `<hp:pic>` with all 15 children in order; missing `hp:imgClip`, `hp:imgDim`, or `hp:effects` crashes Hancom. See [references/image-insertion.md](references/image-insertion.md).
- Paragraph, table, header/footer, numbering, and style structures: [references/xml-reference.md](references/xml-reference.md).

## Legacy .hwp

`.hwp` (binary) must be converted to `.hwpx` before editing. Do not use LibreOffice for HWP→HWPX: it has no reliable HWPX export and can silently corrupt newer files. Use `@ssabrojs/hwpxjs` from a scratch work directory, installed with an exact version only after the user approves the install: `npm install --save-exact @ssabrojs/hwpxjs@<approved-version>`, then `./node_modules/.bin/hwpxjs convert:hwp in.hwp out.hwpx`. Never run it through plain `npx`. When reading with its JS API, pass a bounded slice (`fileBuffer.buffer.slice(fileBuffer.byteOffset, fileBuffer.byteOffset + fileBuffer.byteLength)`), never the pooled `fileBuffer.buffer`. If conversion is unavailable, ask the user to save as HWPX from Hancom Office.

## Rendering

This skill does not claim a portable HWPX→PDF or image renderer. Use a renderer only if the host has one that was checked on a disposable copy of this document; otherwise report visual QA as not performed and rely on validation and re-extraction.

## Report (to the user, in Korean)

```markdown
## HWPX 결과
- 파일: /절대/경로/결과.hwpx (원본은 그대로 둠)
- 변경: 2쪽 표 3행 금액 수정, 서명 이미지 1개 삽입
- 검증: validate.py 오류 0건, 텍스트 재추출로 변경 확인
- 시각 확인: 미실시 (렌더러 없음)
```
