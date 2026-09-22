---
name: clonamic-apple-design
description: Apply an Apple-first foundation for direct, responsive, spatially coherent UI behavior, motion, materials, and typography. Load for substantial UI creation, redesign, interaction/motion decisions, or UI review even when Apple is not named; combine with at most one aesthetic specialist. Do not load for non-UI work, exact visual copying with no unspecified behavior, or a fully specified one-value UI patch.
license: Complete terms in LICENSE.txt
---

# Clonamic Apple Design

Use this as a foundation lens, not an Apple visual imitation and not an aesthetic
specialist. It may accompany exactly one of `clonamic-frontend-design` or `impeccable`.

## Precedence

Keep accessibility as the hard floor, then follow explicit user direction, exact
reference/Figma, and the repository's established system. Apply this foundation only
to unresolved behavior or design choices. The selected aesthetic specialist handles
brand, palette, and composition after this foundation.

Never override an explicit no-motion request, reduced-motion preference, exact pixels,
existing tokens, or established components merely to look more Apple-like.

## Core pass

For every substantial UI task, check only the relevant items:

- Feedback starts immediately and remains continuous during direct manipulation.
- Dragged content tracks the pointer 1:1 and respects the original grab offset.
- Interactive motion can be interrupted, reversed, and retargeted from its visible state.
- Entry and exit preserve spatial origin and use symmetric, predictable paths.
- Springs explain physical continuity; fixed-duration decorative motion stays restrained.
- Typography, hierarchy, materials, and depth improve legibility rather than imitate a theme.
- Reduced motion keeps status feedback while removing vestibular movement and overshoot.

## Motion ownership

The Apple foundation owns interaction physics. General specialists may prohibit
decorative bounce, but must not remove continuity from a real gesture. Permit a small
overshoot only after a momentum-carrying flick, throw, or drag release. Never add bounce
to a menu, modal, page entrance, automatic reveal, or reduced-motion path.
Do not infer momentum from generic drag, reorder, sheet, carousel, or unspecified-physics wording.
Require explicit flick, throw, momentum, velocity, or velocity-carrying release evidence.

## Conditional reference

Read [principles.md](references/principles.md) only when the task needs detailed motion,
gesture, material, multimodal feedback, typography, accessibility, or foundational
design-principle/process decisions. Skip it for static structure where the core pass is
sufficient.

## Evidence

Exercise the interaction in a real browser when runnable. Check pointer-down feedback,
mid-motion interruption, reversal, keyboard/focus behavior, reduced motion, and frame
smoothness. Exact reference work must still match the reference; Apple applies only to
behavior the reference leaves unspecified.

## Provenance

Adapted from Emil Kowalski's MIT-licensed
[`apple-design`](https://github.com/emilkowalski/skills/tree/main/skills/apple-design)
skill. This `clonamic-` edition removes the upstream response/report harness and keeps the
domain guidance lazy for Clonamic's AoE routing.
