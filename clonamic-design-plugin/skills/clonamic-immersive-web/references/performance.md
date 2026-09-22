# Performance gate

- Establish a static/DOM baseline before adding GPU work.
- Measure target devices; do not claim a frame-rate improvement from code inspection alone.
- Bound device pixel ratio, lights, draw calls, shader variants, particles, post-processing passes, and retained histories.
- Compress geometry/textures in the existing pipeline and load by visibility or user intent.
- Reuse buffers/materials and dispose textures, render targets, geometries, listeners, observers, and animation handles.
- Pause or reduce rendering when hidden, offscreen, low-power, or reduced-motion.
- Keep keyboard focus, labels, error/loading states, and content outside the canvas when possible.
