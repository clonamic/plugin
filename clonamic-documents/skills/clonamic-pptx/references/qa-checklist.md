# QA checklist

Run after every render. Blockers must be zero before delivery; fix majors unless the user accepts them.

## Blockers

- [ ] The file opens: `inspect_pptx.py` exits 0 and the slide count matches the outline.
- [ ] No shape extends outside the slide (`OUT_OF_BOUNDS`).
- [ ] No two text boxes overlap (`TEXT_OVERLAP`) and no text is clipped or runs past its box in the render.
- [ ] No invented numbers, charts without a supplied series, or unattributed quotes.
- [ ] Slide images are not near-blank; every slide carries its `must_show` items.

## Majors

- [ ] Fonts at or above the floor in [typography.md](typography.md) (`SMALL_FONT`).
- [ ] `LIKELY_OVERFLOW` warnings checked against the render; cut or split where real.
- [ ] No empty placeholders left (`EMPTY_PLACEHOLDER`): they show "Click to add text" in edit mode.
- [ ] A stranger gets the conclusion of each slide in five seconds; the title is the implication.
- [ ] One idea per slide; no slide with two independent conclusions.
- [ ] No card taller than its text with an empty lower half; no large empty canvas under the last block.
- [ ] Same visual never three slides in a row; at most one 2×2 per four slides.
- [ ] The visual matches the case (two choices → comparison, ordered steps → process, named claims → proof grid).
- [ ] Last decide/pitch slide is the ask with owner, timing, success metric as clauses.
- [ ] Footer title is readable (never a lone `…`), page numbers present.
- [ ] No sentence repeated on the same slide; no label chips echoing the cards.

## Polish

- [ ] Shared left edge and top line; equal cards equal size; consistent gutters.
- [ ] Contrast ≥ 4.5:1 for body text.
- [ ] Korean line breaks do not split a word awkwardly; titles at most two lines.
- [ ] Speaker notes present when requested.
- [ ] Everything editable: text in text boxes, native tables and charts.
