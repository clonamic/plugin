# Immersive web: 3D, canvas, advanced motion

Use only when the brief explicitly calls for a 3D scene, shader, particle field, or scroll-driven
timeline. A button transition, modal, or page entrance does not qualify.

## Choose one technology

Prefer what the project already has. If nothing exists:

| Need | Reasonable choice | Use something lighter when |
|---|---|---|
| general 3D scene | Three.js | CSS 3D transforms or an image sequence can show it |
| 3D inside a React app | React Three Fiber | the app is not React |
| large scene, physics, engine tooling | Babylon.js | one hero effect is the whole need |
| many 2D sprites or particles | PixiJS | Canvas 2D holds the frame budget |
| scroll-linked timeline | GSAP ScrollTrigger | CSS scroll-driven animations suffice |
| state-driven React motion | the project's motion library | a CSS transition works |
| designer-authored vector animation | Rive or Lottie | an SVG with CSS animation works |

One owner for render state and one owner for time per surface; never mix two animation systems
on the same element.

## Loading libraries

Install through the project's package manager with a pinned version. For a standalone prototype,
import a pinned version from a CDN as an ES module (for example
`https://cdn.jsdelivr.net/npm/three@<version>/build/three.module.js`). Nothing is bundled with
this plugin.

## Build rules

- Keep text, navigation, and controls in the DOM; the canvas illustrates, it does not replace
  content.
- Define a static fallback (poster image), loading state, error state, and reduced-motion path
  before adding effects.
- Cap device pixel ratio (≤ 2 desktop, ≤ 1.5 mobile) and texture size to what the layout shows.
- Pause rendering when the tab is hidden (`visibilitychange`) or the canvas is offscreen
  (`IntersectionObserver`).
- On teardown dispose geometries, materials, textures, render targets, listeners, and observers.
- Assets: compressed (glTF + Draco/Meshopt, KTX2/WebP textures), loaded by visibility or intent,
  with licenses the project owns.

## Measure, do not assume

In the browser's performance panel or with a small `requestAnimationFrame` sampler: frame time
(target 16.7 ms, 8.3 ms on 120 Hz), main-thread long tasks, memory growth over a minute of use,
total asset weight, behavior on resize, touch input, and keyboard access to surrounding controls.
Report measured numbers, not impressions.
