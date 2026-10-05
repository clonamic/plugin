# Generative and algorithmic art

## Define the system first

Write it down before coding: the state (particles, cells, curves), the update rule (forces, noise
field, growth, subdivision), how values map to color and stroke, and when it stops or resets. The
artwork is the system; every parameter should change the result in a visible way.

## Rules

- **Seeded.** Every random source comes from one seed; the same seed and parameters reproduce the
  same frames. Show the seed in the UI or file name.
- **Bounded.** Cap particle counts, trail buffers, pixel density, and allocations per frame; no
  unbounded arrays.
- **Controllable.** Expose only the parameters that matter. Default keys: `space` pause,
  `r` new seed, `s` save PNG. Controls stay keyboard reachable.
- **Embeddable.** When placed in an interface, honor `prefers-reduced-motion` with a still frame.
- **Original.** Build a system of your own; do not recreate a living artist's recognizable work.

## Runtime

Load p5.js at run time: from the project's npm dependencies, or a pinned CDN build in a
standalone HTML file, e.g.
`<script src="https://cdn.jsdelivr.net/npm/p5@<version>/lib/p5.min.js"></script>`. When the user
needs offline output, download that pinned file next to the HTML with the user's consent. Plain
Canvas 2D needs no library at all.

## p5.js skeleton (instance mode)

```js
const params = { seed: Number(new URLSearchParams(location.search).get('seed')) || 1, count: 1800, scale: 0.0025 };

new p5((p) => {
  let points = [];
  const reset = () => {
    p.randomSeed(params.seed);
    p.noiseSeed(params.seed);
    points = Array.from({ length: params.count }, () => p.createVector(p.random(p.width), p.random(p.height)));
    p.background('#0F1115');
  };
  p.setup = () => { p.createCanvas(1200, 1200); p.pixelDensity(Math.min(2, window.devicePixelRatio)); reset(); };
  p.draw = () => {
    p.stroke(232, 225, 210, 18);
    for (const pt of points) {
      const angle = p.noise(pt.x * params.scale, pt.y * params.scale) * p.TAU * 2;
      const next = p5.Vector.fromAngle(angle).add(pt);
      p.line(pt.x, pt.y, next.x, next.y);
      pt.set(next);
      if (pt.x < 0 || pt.x > p.width || pt.y < 0 || pt.y > p.height) pt.set(p.random(p.width), p.random(p.height));
    }
    if (p.frameCount > 600) p.noLoop();
  };
  p.keyPressed = () => {
    if (p.key === ' ') p.isLooping() ? p.noLoop() : p.loop();
    if (p.key === 'r') { params.seed = Math.floor(p.random(1e9)); reset(); p.loop(); }
    if (p.key === 's') p.saveCanvas(`flow-${params.seed}`, 'png');
  };
});
```

Replace the update rule with your own system; keep the seed, bounds, and controls.

## Canvas 2D without a library

Use a small seeded PRNG so results are reproducible:

```js
function rng(seed) {
  return () => {
    seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
```

## Check before delivery

Run it for the full duration at the target size and once with `pixelDensity(1)`: frame time
stays steady, memory does not climb, the same seed gives the same image, and the saved PNG
matches the screen. Deliver the HTML, the chosen seeds, and stills.
