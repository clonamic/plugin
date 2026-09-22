---
name: clonamic-immersive-web
description: Design or review an explicitly immersive web experience using named 3D or advanced-motion technology such as Three.js, React Three Fiber, Babylon.js, GSAP ScrollTrigger, Rive, Spline, PixiJS, WebGPU, or shaders. Do not select for ordinary CSS transitions, routine page motion, or a document that merely mentions those tools.
license: Complete terms in LICENSE.txt
---

# Clonamic Immersive Web

This is a narrow implementation helper. For a new product UI it can accompany `clonamic-frontend-design`; for an existing UI it can accompany `impeccable`. The Apple foundation still owns unspecified interaction feedback and motion continuity. Do not load unrelated technology references.

## Route once

1. Inspect the repository and use its existing renderer, animation stack, component system, and asset pipeline.
2. Name the one primary technology required by the brief. Read `references/technology-matrix.md`, then only the matching performance or asset section when needed.
3. Keep semantic HTML and ordinary controls outside the canvas when possible. 3D must explain content or interaction, not replace navigation or text.
4. Define a low-power/static fallback, reduced-motion path, loading state, error state, and cleanup/disposal path before adding effects.
5. Measure frame rate, main-thread cost, memory growth, texture/model weight, resize behavior, keyboard access, and pointer/touch behavior in the real target.

## Offline boundary

The guidance catalog is local and works offline. Runtime packages, models, textures, fonts, hosted Spline/Rive files, and CDNs are not bundled. Never install or download them silently. If the project lacks a required dependency, stop at a native/local fallback or request approval with the exact package and reason.

## Guardrails

- One renderer and one animation ownership model per surface.
- Dispose GPU resources and remove listeners on teardown.
- Cap device pixel ratio and asset resolution to the evidence-backed need.
- Pause or degrade work when hidden, offscreen, low-power, or reduced-motion.
- A normal button transition, modal, menu, or page entrance does not justify this skill.

## Provenance

The conditional catalog is derived from FreshTechBro's MIT-licensed `claudedesignskills`; this wrapper keeps discovery thin and prevents all 3D/motion references from entering context at once.
