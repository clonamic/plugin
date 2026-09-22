# Layout families (engine-owned)

You pick **block types**. The engine picks the family.

| family | when | required blocks |
|---|---|---|
| proof_grid | 3–4 (up to 6) evidence bullets / short claims | bullets |
| hero_assertion | title + one numeric metric, or 1–2 leftover items | optional metric_card |
| metric_strip | 2–4 numeric metric_card only | metric_card |
| comparison_2col | two options | comparison |
| process_flow | 3–6 ordered steps | process_steps |
| recommendation | ask / next step | recommendation |
| table_focus | lookup grid | table |
| chart_focus | user-supplied series | chart |
| quote_proof | attributed quote | quote |

If a mix does not fit, change blocks. Overflow / VIS003: add a structured block or split the slide.

The engine owns geometry: comparison gets a `vs` badge, process gets numbered discs and arrows, proof gets rails or dots, recommendation gets a band or full-bleed ask. Do not draw those yourself.

Motion is also engine-owned: fade between slides; process / comparison / proof build by click on decide and pitch, sequentially on teach. Report stays still except the fade.
