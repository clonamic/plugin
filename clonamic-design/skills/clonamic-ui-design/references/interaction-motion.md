# Interaction and motion (Apple-like direct manipulation)

Heuristics for how an interface responds, not a visual theme. They apply only where the user,
the reference, and the project leave behavior open.

## Response

- Acknowledge input on pointer-down, not on release. A press state appears within one frame.
- Every status has feedback: in progress, done, warning, error. Validate inline as the user goes,
  not only on submit.
- Keep the user oriented: where am I, what is here, where can I go, how do I leave.
- Put a control next to the thing it changes. If the mapping needs a caption, the layout is wrong.

## Direct manipulation

- Dragged objects follow the pointer 1:1 and keep the offset where they were grabbed; use pointer
  capture so they never detach.
- Commit to an axis or gesture only after a small movement threshold; until then any gesture can
  still win, and cancel/reverse stays possible.
- Record a short history of positions and timestamps when release velocity matters.
- Past a boundary, add increasing resistance instead of a hard stop.

## Interruptible, continuous motion

- Never block input while an animation runs. A new input retargets the motion from where it is
  on screen now, not from the old destination.
- Carry velocity across a reversal or a hand-off from gesture to animation.
- A surface enters from and returns to its origin (the control that opened it) along the same path.
- Animate X and Y independently when their velocities differ.

## Springs and momentum

- Ordinary state changes: critically damped, no overshoot.
- Overshoot only after a real flick, throw, or velocity-carrying release, and keep it small.
  Menus, modals, page entrances, and automatic reveals never bounce.
- Project the release forward before choosing a snap point, so a fast flick reaches the next stop.

## Timing guide

| Change | Duration | Easing |
|---|---|---|
| press / hover feedback | 0–100 ms | linear or ease-out |
| small state change (toggle, tab) | 150–200 ms | ease-out |
| surface enter (menu, popover) | 200–250 ms | ease-out; exit ~20% faster |
| large surface (sheet, page) | 250–400 ms or a spring | spring / ease-in-out |

## Materials and depth

- Translucency and blur only where they explain layering or keep context visible beneath.
  Do not stack translucent layers until text contrast collapses.
- Shadow strength follows elevation; one light direction for the whole surface.
- A blocking modal may dim the page; a non-blocking panel leaves the page usable.

## Typography for interfaces

- `system-ui` is a sound default for product UI unless identity demands otherwise.
- Size in `rem` so user text-size preferences scale the layout.

## Accessibility alternatives

- `prefers-reduced-motion: reduce` → replace slides, parallax, and springs with short fades or
  instant changes; keep status feedback.
- `prefers-reduced-transparency: reduce` → opaque surfaces, no blur.
- `prefers-contrast: more` → solid surfaces and explicit borders.
- Never make motion, sound, or haptics the only carrier of meaning.

## Performance

- Animate `transform` and `opacity`; avoid animating layout properties.
- Drive pointer-linked updates from `requestAnimationFrame`; list transition properties explicitly
  (no `transition: all`).
- Use the platform (CSS transitions, the Web Animations API, View Transitions) before adding a
  motion library; reuse the one the project already has.

## Review questions

1. Does feedback start at the action and continue through it?
2. Can a moving element be grabbed, reversed, or cancelled without a jump?
3. Does the motion path explain where a surface came from and where it goes?
4. Is every overshoot caused by real momentum?
5. Does reduced motion keep the meaning?
