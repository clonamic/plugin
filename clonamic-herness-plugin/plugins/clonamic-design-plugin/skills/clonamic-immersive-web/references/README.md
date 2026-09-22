# Conditional catalog

Open `technology-matrix.md` first. Add `performance.md` or `asset-pipeline.md` only when the implementation actually crosses that boundary.

- Three.js/WebGL/R3F/shaders: renderer, scene, materials, geometry, disposal, GPU budget.
- GSAP/ScrollTrigger/Framer Motion/React Spring: timeline or state ownership and cleanup.
- Babylon.js/PixiJS: engine-specific scene or 2D rendering.
- Spline/Rive/Lottie: runtime asset loading, accessibility fallback, and lifecycle.
- WebGPU/WebXR/model pipelines: explicit platform capability and asset constraints only.

These are condensed offline guidance notes, not bundled runtimes. Never install a package because it is named here.
