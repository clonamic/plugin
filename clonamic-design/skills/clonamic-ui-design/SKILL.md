---
name: clonamic-ui-design
description: Create or redesign a web or app UI with a deliberate direction — subject-grounded aesthetic, typography, color tokens and themes, layout, Apple-like direct-manipulation motion, design-system choice, optional 3D or advanced motion, and faithful build from a Figma frame or screenshot. Use for new screens, landing pages, redesigns, theming, and reference-matching. Not for auditing an existing UI (clonamic-ui-review) or static posters and art (clonamic-visual-art).
---

# Clonamic UI Design

Design a UI that is specific to its subject, built on tokens, and verified in a real browser.

## Precedence

Accessibility floor > explicit user direction > supplied reference (Figma, screenshot) > the
repository's established design system > the defaults in this skill. Never override a higher
layer to make the result look more distinctive.

## Pick the mode first

- **Reference mode** — the user supplied an exact screenshot or Figma frame. Fidelity wins: skip
  direction work, match layout, proportions, spacing, and type; decide only what the reference
  leaves open (states, motion, responsive behavior). For Figma, read
  [figma.md](references/figma.md).
- **Extend mode** — the repository already has tokens or a component library. Reuse them; make new
  decisions only where the system is silent, in its own idiom.
- **Direction mode** — a new surface with open aesthetic axes. Run the full procedure below.

## Procedure (direction mode)

1. **Pin the subject.** Name the product, the audience, and the page's single job. If the brief is
   vague, choose and state the assumption. Collect real content; placeholder copy produces
   placeholder design.
2. **Inspect the project.** Framework, styling approach, fonts, existing tokens, component library.
   With no system in a new project, read [design-systems.md](references/design-systems.md).
3. **Write a compact plan** (in your reasoning or a short note): 4–6 named color tokens with hex,
   type roles (display, body, utility) and a scale, a layout concept with an ASCII wireframe, one
   signature element, and a motion stance. Read [direction.md](references/direction.md) and
   [color-and-theme.md](references/color-and-theme.md) for how to choose each.
4. **Challenge the plan.** For each choice ask whether you would make it for any similar brief. If
   yes, replace it with one drawn from the subject's own world, and note what changed. Measure every
   planned text/background pair with `python3 ../clonamic-ui-review/scripts/contrast.py FG BG`
   (path relative to this skill's folder).
5. **Build from tokens.** Express the plan as CSS custom properties (or the project's token format)
   and derive every value from them. Semantic HTML first; every interactive element gets default,
   hover, focus-visible, active, disabled, and loading/error states where they apply. For gestures,
   drag, sheets, and transitions, read [interaction-motion.md](references/interaction-motion.md).
   For WebGL, canvas scenes, or scroll-driven timelines, read [immersive.md](references/immersive.md).
6. **Verify in a real browser** with the `clonamic-browser-qa` skill: widths 375, 768, and 1440;
   a keyboard-only pass; reduced-motion emulation; dark mode if supported. Look at the screenshots
   yourself, fix what is off, then remove one decorative element that does not earn its place.
7. **Report** in the format below.

## Quality floor (every mode)

- Body text contrast ≥ 4.5:1, large text and UI component boundaries ≥ 3:1 (WCAG 2.2 AA).
- Visible keyboard focus on every interactive element; logical tab order; no keyboard traps.
- No horizontal scroll, clipping, or overlap from 320px up; touch targets ≥ 24×24px (44px preferred).
- `prefers-reduced-motion` removes movement but keeps state feedback.
- Content is visible without JavaScript timing or a reveal animation completing.
- Korean text: `word-break: keep-all`, body line-height 1.6–1.8, a font with full Hangul coverage.
- Reuse existing components and tokens before adding abstractions or dependencies.

## Report format (user-facing, Korean)

```markdown
## UI 디자인 결과 — 요금제 페이지 (방향 설정 모드)

- 방향: 회계사 사무소용 SaaS. "정돈된 장부" 콘셉트 — 모눈 그리드, 표 중심 비교.
- 토큰: `--ink #14212E` / `--paper #F6F8FA` / `--accent #1F5FBF` (본문 대비 15.3:1, 링크 5.7:1)
- 서체: 제목 IBM Plex Sans KR 600, 본문 Pretendard 400, 숫자 tabular-nums
- 시그니처: 요금 비교표의 행 강조가 커서를 따라 이동 (reduced-motion 시 즉시 전환)
- 검증: 375/768/1440 스크린샷 확인, 키보드 순회 통과, 가로 스크롤 없음
- 남은 결정: 연간 할인율 문구는 실제 값이 필요합니다.
```
