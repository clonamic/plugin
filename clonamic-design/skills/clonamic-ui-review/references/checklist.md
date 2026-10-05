# UI review checklist

Each item: what to look for → how to confirm. Check only what applies to the target. Record
code findings as `file:line`, rendered findings with the viewport and screenshot.

## Semantics and assistive tech

- Actions are `<button>`, navigation is `<a href>`; no clickable `div`/`span` → grep `onClick` on
  non-interactive elements; tab to it.
- Every control has an accessible name (visible label, `aria-label` for icon-only buttons) →
  inspect the browser's accessibility tree.
- Images: meaningful `alt`, or `alt=""` for decoration; decorative icons `aria-hidden="true"`.
- One `h1`, no skipped heading levels; landmarks (`header`, `nav`, `main`, `footer`); a skip link
  on content-heavy pages.
- Live updates (toasts, inline validation, async results) announced via `aria-live="polite"`.
- Native elements before ARIA; ARIA roles match behavior (a `role="tab"` really behaves as a tab).

## Keyboard and focus

- Everything reachable and operable by keyboard in a logical order; no traps; Escape closes
  overlays and returns focus to the trigger.
- Focus is always visible (≥ 3:1 against adjacent colors) and not hidden behind sticky headers →
  `outline: none` without a `:focus-visible` replacement is a defect.
- `:focus-visible` rather than `:focus` for rings; `:focus-within` for compound controls.
- `autofocus` only where one primary input clearly owns the page, and not on mobile.

## Forms

- Each input has a label tied to it (`for`/`id` or wrapping); the label is clickable.
- Correct `type`, `inputmode`, `autocomplete`, and `name`; spellcheck off for codes, emails, ids.
- Paste is never blocked. Required fields marked in text, not color alone.
- Errors appear inline beside the field, say how to fix, and focus moves to the first error on
  submit. The submit button stays enabled until the request starts, then shows progress.
- Unsaved changes warn before navigation. Previously entered data is not requested twice.

## Contrast and color

- Body text ≥ 4.5:1, large text ≥ 3:1, component boundaries and focus indicators ≥ 3:1 →
  `scripts/contrast.py`.
- Check hover, disabled (exempt but should stay legible), selected, dark mode, text on images.
- Status is never conveyed by color alone.

## Layout and responsiveness

- No horizontal scroll, overlap, or clipping from 320px up; content reflows at 400% zoom.
- Touch targets ≥ 24×24px with spacing (44px preferred for primary actions).
- Long, short, and empty content handled: truncation or wrapping, `min-width: 0` on flex children,
  empty states instead of broken layout.
- Full-bleed layouts respect `env(safe-area-inset-*)`; modals and drawers use
  `overscroll-behavior: contain`.
- Pinch zoom is not disabled (`user-scalable=no`, `maximum-scale=1` are defects).

## Typography and copy

- Body measure about 60–75 Latin characters; body size ≥ 16px on mobile; line-height ≥ 1.5
  (1.6–1.8 for Korean).
- No justified body text, all-caps paragraphs, or wide tracking on body text.
- Tabular numbers in tables and comparisons; balanced heading wraps.
- Proper characters: `…`, curly quotes, non-breaking space between number and unit.
- Labels name the outcome ("변경사항 저장", not "확인"); one term per concept; errors give the next
  step; consistent register.

## Motion

- `prefers-reduced-motion` honored; no essential information carried only by motion.
- Only `transform`/`opacity` animated for continuous motion; no `transition: all`.
- Interactive animations can be interrupted; `transform-origin` points to the trigger.
- Nothing flashes more than three times per second.

## Media and performance

- Images have `width`/`height` (or `aspect-ratio`) to prevent layout shift; below-the-fold images
  `loading="lazy"`; the hero image prioritized.
- Fonts preloaded only when critical, with `font-display: swap`; few weights.
- Long lists (> ~100 rows) virtualized or `content-visibility: auto`.
- No layout reads inside render or animation loops; DOM reads and writes batched.
- Measure in the browser: Largest Contentful Paint, Cumulative Layout Shift, Interaction to Next
  Paint, long tasks. Report numbers with the device/throttling used.

## State, navigation, i18n

- Filters, tabs, pagination, and open panels reflected in the URL so they can be shared and
  restored; links open in new tabs with modifier keys.
- Destructive actions offer undo or confirmation.
- Dates, numbers, and currency formatted with `Intl` APIs; layout survives 30–40% longer
  translations; product names marked `translate="no"`.
- Dark theme sets `color-scheme` and a matching `theme-color`; native selects stay readable.
- Server/client rendering does not produce hydration mismatches for dates or random values.
