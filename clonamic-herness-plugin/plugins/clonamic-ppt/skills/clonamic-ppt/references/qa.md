# QA

After `run_engine.py`, open `qa_report.json`.

- `blocker` must be 0.
- `major` should be 0 before delivery.
- `VIS003` / `VIS001` = the slide is too empty. Switch to proof_grid / comparison / process / metrics.
- `QA009` = a card is taller than its text (now fires from ~1.05in, not only giant stretch). Add `주장 — 이유` body or change the block type. Do not ignore it.
- `OUT018` = outline visual does not match the slide's case (two choices used as quote, three named items used as hero). Change the visual.
- `SPC024` = specs block type does not implement the outline visual.
- `SPC025` = `quote_proof` has no extras. Implement `must_show` as 2–3 bullets under the quote. Do not stretch the quote card.
- `QA013` = empty canvas under the last planted block. The engine should plant a conclusion band; if it still fires, the takeaway is missing or identical to the title.
- `QA014` = footer title became `…`. Shorten the deck title or rerun on this engine. Never ship a lone ellipsis.
- `VIS002` = nearly blank render. Rebuild that slide.
- `VIS000` = PNG render skipped on this machine; still fix IR majors.
- Repair only `slide_specs.json`, then rerun the engine.
