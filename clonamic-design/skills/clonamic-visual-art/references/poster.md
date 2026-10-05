# Static pieces: posters, covers, prints, social images

## Set up the canvas

| Output | Size to build | Notes |
|---|---|---|
| screen / social | exact px (e.g. 1080×1350, 1200×630, 1920×1080) | render at device scale 2 for crispness |
| print | trim size in mm + 3 mm bleed each side | 300 dpi raster, or vector PDF; keep text ≥ 5 mm inside trim |
| cover / thumbnail | the largest required size | check legibility at the smallest size it will appear |

## Build route

- **HTML/CSS or SVG (default).** One fixed-size page (`width`/`height` in px or mm via `@page`),
  CSS grid for structure, fonts loaded and awaited (`document.fonts.ready`) before rendering.
  Render with a browser: `page.screenshot({ path, omitBackground })` for PNG, `page.pdf({ width,
  height, printBackground: true })` for PDF.
- **Python.** Pillow for raster compositing; ReportLab or a browser for vector PDF. Run with
  `uv run --with pillow script.py` so nothing is installed into the project.
- Keep the source (HTML/SVG/script) next to the export so the piece stays editable.

## Composition

- One grid and one spacing rhythm; align to it, break it once on purpose.
- Hierarchy by scale, weight, and position before color. One focal point.
- Negative space is an element; do not fill it with decoration.
- Text is minimal and exact: title, essential facts (date, place, call to action), credits.
- Palette of 2–4 colors with one accent; check text contrast if the piece is informational.
- Avoid stock moves: generic gradient blobs, centered-everything, drop shadows on text, repeated
  cards or badges.

## Before export

- Spelling, numbers, dates, and line breaks verified against the brief.
- Nothing crosses the safe margin; bleed filled for print; no stray hairlines at the trim.
- Third-party images or marks used only if the user supplied or licensed them; record their source
  in the report.
- Print in CMYK? Note that vivid RGB accents may dull and suggest a proof.
