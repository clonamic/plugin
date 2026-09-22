# Technology matrix

Condensed from the pinned MIT `claudedesignskills` catalog.

| Need | Prefer when already present | Avoid when |
|---|---|---|
| General WebGL scene | Three.js | semantic DOM/CSS can express it |
| React-owned 3D | React Three Fiber | project is not React or mixes imperative ownership |
| Engine features/large scene | Babylon.js | a small visual effect is enough |
| 2D GPU particles/sprites | PixiJS | Canvas 2D meets the measured budget |
| Sequenced scroll timeline | GSAP ScrollTrigger | native scroll/CSS is sufficient |
| State-driven React motion | existing Motion/Framer Motion or React Spring | ordinary CSS transition works |
| Authored vector runtime | existing Rive/Lottie asset pipeline | a local SVG is sufficient |
| No-code hosted scene | existing local/exported Spline integration | offline or data ownership forbids hosting |
| WebXR | existing A-Frame/Three/Babylon XR stack | device support and fallback are undefined |

Use exactly one ownership model for render state and one for time/timelines. A named tool in a prompt is evidence to inspect, not permission to install it.
