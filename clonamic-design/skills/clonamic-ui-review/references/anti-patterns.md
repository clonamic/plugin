# Anti-patterns

Signs that a UI was assembled from defaults rather than designed. Each is a finding only when it
does not serve the subject; note the exception when it does.

## Template tells

| Pattern | Why it reads as generic | Acceptable when |
|---|---|---|
| gradient text on headlines | decoration standing in for type hierarchy | brand guide mandates it |
| purple/blue gradient hero, glow on dark | appears regardless of subject | the subject is literally light or space |
| glass cards on blurred color blobs | depth without meaning, contrast collapses | layering over live content |
| three identical icon-over-heading cards | content forced into a fixed grid | items are truly parallel and equal |
| pill eyebrow above every heading | labels that categorize nothing | eyebrows encode real categories |
| numbered sections 01 / 02 / 03 | implies a sequence that is not there | real ordered steps |
| colored side border on rounded cards | a stock accent device | a status rail with real meaning |
| invented metrics, fake logos, stock testimonials | unearned credibility | real, sourced numbers |
| one font for display, body, and data | flat hierarchy | product UI with a deliberate single family |
| bounce/elastic easing on menus or entrances | playful noise; see interaction-motion | after a real flick with momentum |
| oversized hero text with crushed tracking | volume instead of hierarchy | a poster-like brand moment |

## Layout and visual defects

- Cards nested in cards; borders, shadows, and backgrounds all applied to the same box.
- Uniform spacing everywhere, so groups do not read as groups.
- Grey text on colored backgrounds (use a tint of the background hue instead).
- Body text touching the viewport edge on mobile; cramped padding inside controls.
- Positioned children clipped by an `overflow: hidden` ancestor (menus, tooltips).
- Broken or placeholder images; icons from mixed sets or sizes.
- Several competing primary buttons on one screen.

## Copy tells

- Buzzwords ("seamless", "revolutionary", "next-level") and slogan cadence instead of facts.
- Heavy em-dash use and triads that sound like an ad.
- Vague buttons ("확인", "Submit", "Continue") where a specific verb fits.
- Errors that apologize but do not say what happened or what to do.

## Product-surface specifics

- Display fonts in labels, buttons, or tables.
- Restyled standard controls (custom scrollbars, unusual checkboxes) with no task benefit.
- Modal as the first answer when inline or progressive disclosure would do.
- Inconsistent component vocabulary between screens — if two save buttons differ, one is wrong.
- Saturated accent on inactive states.
