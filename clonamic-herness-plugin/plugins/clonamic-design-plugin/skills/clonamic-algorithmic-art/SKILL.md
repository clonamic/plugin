---
name: clonamic-algorithmic-art
description: Create original generative or algorithmic art using seeded randomness, particles, flow fields, procedural geometry, or p5.js. Select for code-as-art deliverables; do not select for charts, product UI decoration, static posters, or copying a named artist's style.
license: Complete terms in LICENSE.txt; bundled p5.js terms in assets/P5-LICENSE.txt.
---

# Clonamic Algorithmic Art

Build an original, reproducible sketch. The default runtime is bundled `assets/p5.min.js`; `assets/p5.js` is its corresponding readable source and the dependency-free Canvas template is a fallback. Never reference a CDN, remote font, or remote texture.

## Workflow

1. Lock canvas size, animation/static output, interaction, performance target, and required file types.
2. Define one concise computational idea: state, update rule, forces/noise, palette mapping, and stopping/reset behavior.
3. Seed every random source and expose only parameters that materially change the system. The same seed and parameters must reproduce the same frame sequence.
4. Copy `assets/p5.min.js` beside the output and load it with a relative path. Keep the license/source link when redistributing it. Use the native Canvas 2D template when a library is unnecessary; never install or fall back to a CDN silently.
5. Add pause, reset, seed, and export controls only when useful. Keep controls semantic and keyboard reachable.
6. Test at the target size and a lower-power setting. Bound particle count, pixel density, history buffers, and allocation inside animation loops.

Read `references/generator-template.js` for p5 structure only; replace its algorithm. `references/offline-checklist.md` owns the packaging and originality gate.

## Output gate

- Original system, not imitation of a living artist or supplied protected work.
- No unseeded randomness, hidden network request, or unbounded growth.
- Reduced-motion/static alternative when embedded in an interface.
- Keep every runtime dependency local and preserve its license when redistributing it.

## Provenance

Adapted and shortened from Anthropic's Apache-2.0 `algorithmic-art` skill. The Clonamic edition replaces its CDN-first template with pinned local p5.js runtime/source files and a dependency-free Canvas 2D fallback.
