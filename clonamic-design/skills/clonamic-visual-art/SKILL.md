---
name: clonamic-visual-art
description: Create an original standalone visual piece — a poster, cover, one-page print, social or event image, or generative/algorithmic artwork (seeded p5.js or Canvas, flow fields, particles, procedural geometry) — exported as PNG, PDF, SVG, or a self-contained HTML sketch. Use when the deliverable is the image or the artwork itself. Not for product UI (clonamic-ui-design), data charts, or diagrams (clonamic-sketch-diagram).
---

# Clonamic Visual Art

Make one deliberate composition or one reproducible generative system, render it, look at it, and
refine it until it holds at full size.

## Procedure

1. **Lock the brief.** Medium (static or generative), exact size (px, or mm plus DPI for print),
   required copy, audience, output formats, and any brand or reference constraints. Supplied
   constraints come before any aesthetic choice.
2. **Write a direction** of 3–5 sentences: the idea, the form language, palette (named hex
   values), type (for static pieces), the one signature device, and what you will leave out. Make
   it original — do not imitate a living artist's signature style or a protected work.
3. **Build** with the route that fits:
   - Static poster/cover/print → [poster.md](references/poster.md).
   - Generative or algorithmic art → [generative.md](references/generative.md).
4. **Render and inspect at full size.** Open the exported file. Check spelling and line breaks,
   that nothing crosses the margins or bleed, no accidental overlap or clipping, and that the
   hierarchy reads from across the room (shrink it to thumbnail size as a test).
5. **Refine, then subtract.** Improve existing elements before adding new ones; remove one element
   that does not serve the idea. Re-render after every change.
6. **Deliver** the files plus the editable source (HTML/SVG/sketch), and report.

## Runtime

Use what the host already provides: a browser (via the `clonamic-browser-qa` skill) to render
HTML/SVG to PNG or PDF; Python via `uv run --with pillow` or `--with reportlab` for raster or PDF
work; p5.js or other libraries from npm or a pinned CDN URL at run time. Nothing is bundled in
this plugin. Fonts: local fonts or a web font loaded at render time; confirm Hangul coverage when
the copy is Korean.

## Report format (user-facing, Korean)

```markdown
## 결과물 — 재즈 페스티벌 포스터 (A2, 300dpi)

- 방향: 금관악기의 반사광을 기하학적 호(arc)로 단순화. 남색 바탕 + 황동색 한 가지 포인트.
- 파일: `poster-a2.pdf`(재단선 3mm 포함), `poster-a2.png`, 편집용 `poster.html`
- 점검: 실제 크기 렌더 확인, 오탈자 없음, 안전 여백 10mm 내 배치, 썸네일 크기에서도 제목 판독 가능
- 참고: 인쇄소가 CMYK를 요구하면 변환 후 황동색이 탁해질 수 있어 교정쇄 확인을 권합니다.
```
