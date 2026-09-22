# Apple interaction principles for the web

Load only the sections relevant to the current UI. These are implementation heuristics,
not a visual theme. Explicit requirements, exact references, repository truth, and
accessibility remain authoritative.

## Response and direct manipulation

- Show press feedback on pointer-down; do not wait for click release.
- During drag, sheet, slider, or carousel movement, update continuously with 1:1 tracking.
- Preserve the grab offset and use pointer capture so the object does not jump or detach.
- Track a short position/time history when release velocity affects the result.
- Use a small intent threshold before committing a direction; retain cancel and reversal.
- Detect plausible gestures in parallel from the first move and cancel the losers once
  intent is clear; only pay a double-tap disambiguation delay where double-tap exists.

## Interruptibility and continuity

- Keep motion interruptible. Never disable input merely because a transition is running.
- Retarget from the current on-screen value, not the stale logical destination.
- Preserve velocity across a reversal or gesture-to-animation handoff.
- Enter and exit along the same path and anchor a surface to its initiating control.
- Use independent axes when X and Y have meaningfully different velocities.
- Let intermediate motion hint at the outcome (grow toward the trigger, lean toward the
  target) instead of interpolating blindly to the end state.

## Springs and momentum

- Prefer critically damped motion with no overshoot for ordinary state changes.
- Use momentum-only bounce: a restrained overshoot is eligible only after a real flick,
  throw, or drag release whose velocity should remain visible.
- Never bounce menu/modal entrances, automatic reveals, or decorative transitions.
- Project a release toward where the gesture is going before selecting a snap point.
- Use progressive resistance beyond a drag boundary instead of a hard frozen stop.

## Performance

- Prefer transform and opacity on the compositor path.
- Use requestAnimationFrame for pointer-driven work and avoid unnecessary input latency.
- Inspect fast or complex motion frame-by-frame when it feels discontinuous.
- Do not add a motion dependency for a simple transition the platform already handles.

## Materials and depth

- Use translucency only to explain hierarchy or preserve context beneath a floating layer.
- Avoid stacking translucent surfaces where contrast collapses.
- Match material weight and shadow to surface scale and background complexity.
- A modal may dim the background; a parallel non-blocking panel should preserve flow.
- Prefer a spatially anchored materialization over an arbitrary fade when origin matters.

## Multimodal feedback

- Trigger sound and haptics on the exact causal event and match their character to the
  action's physicality.
- Fire the visual, audio, and haptic response on the same frame; latency between them
  breaks the illusion of a single event.
- Reserve sound and haptics for meaningful moments; overusing either trains people to
  ignore all of it.

## Typography and structure

- Start with `system-ui` unless the product identity requires another typeface.
- Tighten tracking and leading carefully as display size grows; keep body text legible.
- Scale layout with text using relative units and preserve user text-size preferences.

## Design foundations

Apple frames every choice above as serving eight principles: purpose (build with
intention, decide what not to build), agency (keep people in control, forgive mistakes
over gating them with confirmations), responsibility (privacy and safety, especially
around AI misuse), familiarity (honor known metaphors and platform consistency),
flexibility (adapt to context, device, and range of ability), simplicity (concise and
clear, not merely minimal — fewer unnecessary decisions, not hidden necessary context),
craft (every spacing, timing, and alignment value is a deliberate, defensible choice),
and delight (the result of the other seven, not decoration layered on top).

- Feedback comes in four kinds — status, completion, warning, error — validate inline,
  not only on submit.
- Every screen should answer: where am I, where can I go, what's here, how do I get out.
- Place a control near what it affects; if a label is needed to explain the mapping, the
  mapping itself is weak.
- Prefer direct, specific labels over vague umbrella terms so behavior stays predictable.

## Process

- Prototype interactively; a working demo surfaces problems a static design hides, and
  sets the quality bar the final build has to meet.
- Design interaction and visuals together — motion is not a layer added after the pixels.
- Test with real people in real context, and review motion in slow motion to catch what
  full speed hides.

## Accessibility alternatives

- Under `prefers-reduced-motion`, replace slides, parallax, and springs with short fades or
  static state changes while retaining status feedback.
- Under reduced transparency, increase surface opacity and remove blur.
- Under increased contrast, use near-solid surfaces and explicit contrasting boundaries.
- Maintain visible focus, keyboard equivalence, readable contrast, and adequate hit areas.
- Never make motion, sound, or haptics the only carrier of meaning.

## Review questions

1. Does feedback begin at the user's action and continue through it?
2. Can a moving control be grabbed, reversed, or cancelled without a jump?
3. Does the path explain where the surface came from and where it returns?
4. Is any bounce caused by real gesture momentum rather than decoration?
5. Does reduced-motion preserve meaning without the physical movement?
6. Did the implementation preserve the reference and repository design system?
