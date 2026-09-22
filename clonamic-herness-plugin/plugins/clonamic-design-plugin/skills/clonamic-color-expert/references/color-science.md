# Offline color checklist

Source attribution: adapted from Meodai's `skill.color-expert` (CC BY 4.0), pinned in the repository source lock. This is a modified Clonamic summary.

- State the encoded space and transfer function; RGB triplets without a space are ambiguous.
- Use OKLCH/OKLab for perceptual editing, then gamut-map to the output space.
- Contrast is pair-specific. Test rendered foreground/background states, not palette swatches in isolation.
- WCAG 2.x contrast and APCA are different models; name the one calculated and the required acceptance policy.
- Color is never the only status cue. Preserve text, shape, icon, or position signals.
- Test dark mode, disabled and focus states, transparency over actual backgrounds, and common color-vision deficiencies.
- Do not mix hue-angle conventions from different spaces as if they were interchangeable.
- Prefer a small role-based token set over a large unowned swatch catalog.

For a deeper named topic, use `upstream-index.md` to locate the relevant source title. The third-party corpus it indexes is not bundled; do not invent its contents when offline.
