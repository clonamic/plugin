# Color and themes

## Work in a perceptual space

- Edit in OKLCH (`oklch(L C H)`): equal lightness steps look equal, and hue stays put when you
  change lightness. Convert to the output space at the end.
- Always know the space of a value. An RGB triplet without a space is ambiguous; hue angles from
  HSL and OKLCH are not interchangeable.
- Wide gamut: author Display-P3 accents inside `@media (color-gamut: p3)` with an sRGB fallback.
  Gamut-map by lowering chroma, not by clipping channels (clipping shifts hue).

## Token roles

Define roles, not swatches. A typical set: `bg`, `surface`, `surface-2`, `text`, `text-muted`,
`border`, `accent`, `on-accent`, `focus`, and `success / warning / danger / info` with their
`on-` partners. Components reference roles only. Three layers keep this manageable:
primitive ramps → semantic roles → component overrides.

## Building a palette

1. Pick the accent hue from the subject (see direction.md), then a neutral hue slightly tinted
   toward it (chroma 0.005–0.02).
2. Build each ramp by stepping lightness (e.g. L 0.98 → 0.20 in 10–12 steps); taper chroma near
   both ends, where sRGB cannot hold it.
3. Assign roles from the ramps and measure every text pair with
   `../../clonamic-ui-review/scripts/contrast.py` (relative to this file's folder). Use `--fix fg`
   to get the smallest lightness change that passes.
4. Status colors must differ in more than hue: pair them with an icon, label, or shape.

## Contrast

- WCAG 2.x ratio (the legal/compliance baseline): 4.5:1 body text, 3:1 large text (≥ 24px, or
  ≥ 18.66px bold), 3:1 for UI component boundaries and focus indicators. AAA is 7:1 / 4.5:1.
- APCA is a different, perceptual model (reported as Lc, polarity-aware). Treat it as advisory
  unless the project requires it: roughly Lc 75+ for body text, 60+ for larger content text,
  45+ for large headlines. Compute it with a maintained implementation installed at run time; do
  not mix its numbers with WCAG ratios.
- Measure rendered pairs: hover, focus, disabled, selected, dark mode, and text over images or
  translucent layers (composite first; the script accepts `#rrggbbaa`).

## Dark mode

- Not an inversion. Use dark grey surfaces (L ≈ 0.15–0.22) and raise elevation by lightening.
- Lower accent chroma slightly and check it against the dark surface separately.
- Set `color-scheme: dark` so native controls and scrollbars follow, and match
  `<meta name="theme-color">` to the page background.

## Color-vision checks

Emulate protanopia, deuteranopia, tritanopia, and achromatopsia in the browser's rendering
emulation (DevTools → Rendering → vision deficiencies) and confirm every status remains readable.

## Themes for artifacts (slides, documents, landing pages)

A theme = name + color roles + 2–3 font stacks + a radius/shadow stance + one motif. To theme an
artifact:

1. Propose 2–3 themes that fit the content and audience (name, 4–6 swatches, fonts, one-line mood).
2. Wait for the user's choice, or adjust one to their feedback.
3. Apply it everywhere from tokens; re-check contrast in the final format.

Font stacks: CSS keeps the full stack. Single-font formats (PDF, PPTX, DOCX) use the first family
installed on the machine; express weight as 400/700 rather than inventing "Bold" family names.

### Starter themes by mood

Own starting points, measured with `contrast.py` (text and muted on `bg`, accent as link text on
`bg`, label on accent). Adjust hue to the subject; re-measure after any change.

| Mood | Fits | bg | text | muted | accent | on-accent | Fonts (display / body) |
|---|---|---|---|---|---|---|---|
| Calm trust | finance, legal, health | `#F6F8FA` | `#14212E` 15.3 | `#4A5A6A` 6.7 | `#1F5FBF` 5.7 | `#FFFFFF` 6.1 | IBM Plex Sans KR / Pretendard |
| Warm craft | food, hospitality, handmade | `#FBF6EF` | `#2B1D14` 15.2 | `#6B5546` 6.5 | `#B4471F` 5.1 | `#FFFFFF` 5.4 | Gowun Batang / Pretendard |
| Quiet luxury | fashion, hotels, premium | `#F2EFEA` | `#1A1817` 15.4 | `#5C5650` 6.3 | `#7A5C2E` 5.4 | `#FFFFFF` 6.2 | Noto Serif KR / Pretendard |
| Fresh natural | wellness, outdoor, farming | `#F3F5EE` | `#1E2A1F` 13.6 | `#4F5E4F` 6.3 | `#2F6B3A` 5.8 | `#FFFFFF` 6.4 | Pretendard 700 / Pretendard |
| Night tech | developer tools, AI, data | `#0E1016` | `#E8EAF2` 15.8 | `#A3A9BA` 8.1 | `#8B7CFF` 5.8 | `#0E1016` 5.8 | JetBrains Mono / Pretendard |
| Playful bright | kids, social, consumer apps | `#FFFDF7` | `#1D1A2E` 16.7 | `#55506B` 7.5 | `#C42B60` 5.4 | `#FFFFFF` 5.4 | Jua / Pretendard |
| Industrial steel | B2B, manufacturing, logistics | `#EEF1F4` | `#1F262E` 13.5 | `#4D5966` 6.3 | `#0B6E99` 5.0 | `#FFFFFF` 5.7 | IBM Plex Sans KR / IBM Plex Sans KR |

These are directions, not a migration: the project's existing palette always wins.
