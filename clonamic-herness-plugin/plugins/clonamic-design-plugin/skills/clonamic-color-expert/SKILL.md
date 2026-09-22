---
name: clonamic-color-expert
description: Analyze or engineer color when the user explicitly asks for color science, OKLCH/OKLab conversion, gamut handling, contrast, WCAG/APCA comparison, color-vision checks, or algorithmic palette construction — and when a palette must be chosen for an INDUSTRY or a BRAND MOOD (업종별 컬러, 브랜드 무드 팔레트), which this skill owns via references/industry-palettes.md. Do not select merely because UI code contains colors or for a simple subjective palette/theme request.
license: Original upstream material in references is CC BY 4.0; see LICENSE.txt.
---

# Clonamic Color Expert

Use this as a narrow, offline helper, not an aesthetic specialist. It may accompany the selected UI specialist when the brief has an explicit color-science criterion; it does not replace the project's tokens or the user's brand direction.

## Procedure

1. Identify the target space, display gamut, background, text size/weight, and required standard.
2. Preserve the project's existing color system unless the request authorizes a migration.
3. Prefer perceptual work in OKLCH/OKLab, but keep source and output formats explicit. Gamut-map before serializing to sRGB or Display-P3.
4. Report computed values and assumptions. Distinguish WCAG 2 contrast from APCA; do not call a draft or non-required metric a legal pass/fail standard.
5. Check critical pairs in normal, hover, disabled, focus, dark, and reduced-transparency states. Include color-vision-independent cues where status matters.

For an industry or brand-mood brief, read `references/industry-palettes.md` — it maps 30 industries
to 7 mood palettes and carries the measured contrast for every role pair. Eight of those pairs fail
WCAG AA, so take the direction from it and ship the repaired value it lists, never the raw source hex
in a failing role; a filled accent button also needs the black-or-white label token stated there.

Read `references/color-science.md` for the compact offline checklist. Open `references/upstream-index.md` or `references/upstream-skill.md` only for a specifically named deeper topic; those files contain attribution and reference routing, not an instruction to load the entire corpus.

## Network boundary

No network access is required. Do not fetch palette sites or silently install a color library. If the repository already has a tested color library, use it; otherwise show transparent formulas or use existing platform functions.

## Attribution

Based on Meodai's `skill.color-expert`, CC BY 4.0, modified and reduced for on-demand Clonamic routing. Third-party reference documents from that repository are intentionally not redistributed.
