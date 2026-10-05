# Direction: aesthetic, type, layout, copy

## Where distinctive choices come from

Look at the subject's own world before reaching for a style: the materials, tools, documents,
signage, and vocabulary its people already use. A bakery has flour, paper bags, and handwritten
price cards; an observability tool has terminals, timelines, and alert colors. Pick one or two of
those cues and let them drive palette, type, and one structural device. A style chosen without
the subject is a template.

The first screen states the thesis. Lead with whatever is most characteristic — a sentence, a
product shot, a live demo, an interactive moment. "Big headline + three stats + gradient blob" is
the fallback, not the default.

## Surface register

| | Product surface (app, dashboard, settings) | Brand surface (landing, campaign, portfolio) |
|---|---|---|
| Goal | the tool disappears into the task | a memorable point of view |
| Type | one well-tuned sans is often enough; fixed rem scale, ratio 1.125–1.2 | display + body pairing; fluid display size allowed; ratio 1.25–1.333 |
| Color | restrained: neutrals + one accent for action, selection, state | one committed color field is allowed |
| Density | dense tables and panels are fine | generous space around few elements |
| Motion | 150–250 ms, state changes only, no load choreography | one orchestrated moment may lead |
| Risk | familiarity is a feature; invent nothing for standard tasks | take one justified risk |

## Typography

- Assign roles: display (used sparingly), body, utility (captions, data, code). Two families
  usually suffice; three only when a utility face does real work.
- Pair by structural contrast (e.g. a geometric sans with a humanist serif), not two similar faces.
- Body measure 60–75 characters for Latin, about 35–45 full-width characters for Korean.
- Tight tracking only on large display sizes; never squeeze body text. Avoid negative tracking on
  Hangul.
- Numbers that are compared (prices, tables, timers) use `font-variant-numeric: tabular-nums`.
- Headings use `text-wrap: balance`; paragraphs may use `text-wrap: pretty`.
- Korean-capable families: Pretendard, Noto Sans KR, IBM Plex Sans KR, Noto Serif KR, Gowun
  Batang. Always end stacks with a generic family.

## Layout

- Use one spacing scale (multiples of 4 or 8) and one grid; break the grid only on purpose.
- Structure carries meaning. Numbered markers mean a real sequence; eyebrows label real categories;
  dividers separate real groups. Remove devices that only decorate.
- Vary rhythm between sections (dense, airy, full-bleed) instead of repeating one card block.
- Prefer CSS grid/flex and container queries over JavaScript measurement.
- Watch selector specificity: section-level and component-level rules that both set spacing tend
  to cancel each other. Keep spacing ownership in one layer.

## Defaults to avoid when the axis is free

These looks are legitimate when the brief asks for them, but they show up regardless of subject
when nothing was decided:

- warm off-white page, high-contrast serif headline, rust/terracotta accent;
- near-black page with one neon green or orange accent and glow;
- newspaper pastiche: hairline rules, square corners, dense columns;
- purple-to-blue gradient hero, gradient text, glass cards on a blurred blob;
- three identical icon-on-top feature cards; a pill "eyebrow" above every heading;
- invented metrics ("10x faster", "99.9%") and logo walls without real logos.

## Restraint

Spend boldness in one place: the signature element. Keep everything around it quiet. Before
shipping, remove one decoration that does not serve the subject.

## Copy is design material

- Name things by what the user controls, not how the system works ("알림 설정", not "웹훅 구성").
- Buttons say exactly what happens, and the name stays the same through the flow: a "게시" button
  produces a "게시됨" toast.
- Errors state what happened and how to fix it, without apology or vagueness. Empty states invite
  the next action.
- Keep one register (합니다체 or 해요체) across the surface; sentence case for Latin labels.
- One element, one job: a label labels, an example demonstrates, a hint hints.
