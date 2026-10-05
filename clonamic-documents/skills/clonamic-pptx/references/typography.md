# Typography and color

## Type scale (pt)

| role | size | floor |
|---|---|---|
| hero title | 28–32 | 24 |
| slide title | 22–24 | 20 |
| subtitle / lead | 14–16 | 14 |
| body / card text | 14–16 | 12 |
| small body (dense tables) | 12–13 | 11 |
| metric value | 28–40 | 24 |
| metric label | 12 | 11 |
| footer / source | 8–9 | 8 |

Below the floor is a defect: cut or split instead. Line spacing 1.1–1.25 for body; titles one or two lines at most.

## Fonts

Pick one heading and one body family that exist on the machine that renders and on the audience's machines. For Korean decks:

- Windows audience: `Malgun Gothic` (맑은 고딕).
- macOS audience: `Apple SD Gothic Neo`.
- Mixed or unknown: `Noto Sans KR` / `Pretendard` only if installed for the renderer; otherwise `Malgun Gothic`, which PowerPoint maps on macOS.

Set the East Asian font explicitly (python-pptx: the run's `a:ea` typeface; PptxGenJS: `fontFace`). Latin-only decks: `Calibri`, `Arial`, or the template's theme fonts. Never mix more than two families.

## Color

Use a neutral canvas, one accent, one dark accent; at most one extra semantic color (positive/negative) when the data needs it.

| token | clarity-neutral | boardroom-pine | ink-ask |
|---|---|---|---|
| canvas | FFFFFF | F4F1EA | EFEAE1 |
| surface (cards) | F7F8FA | FFFCF6 | F7F3EB |
| text primary | 111827 | 171412 | 171412 |
| text secondary | 59636E | 5C564C | 5A5348 |
| border | EEF1F4 | D8D2C4 | C9C0B0 |
| accent | 2F6FED | 1F4E3D | 7C6542 |
| accent dark | 174EA6 | 16382C | 171412 |

Suggested pairing: decide / report → clarity-neutral; pitch → boardroom-pine; persuade / ask-heavy → ink-ask. A user template or brand always wins over these tokens.

Contrast: body text on its background at least 4.5:1; never light gray body text on white.

## Visuals

- Prefer metric cards, comparison, process, or a compact table over a decorative picture.
- Charts only from user-supplied numbers; label axes and units; one conclusion line per chart.
- No image search or generation unless asked.
