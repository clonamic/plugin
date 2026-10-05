---
name: clonamic-ui-review
description: Audit an existing web UI for visual hierarchy, accessibility (WCAG contrast, keyboard, semantics, forms), responsiveness, interaction states, performance, copy, and generic template anti-patterns, with real-browser evidence and measured contrast; optionally apply the smallest fixes or a requested refinement (quieter, bolder, simpler, hardened). Use for UI review, design critique, accessibility audit, or polish of an existing interface. Not for creating a new UI (clonamic-ui-design).
---

# Clonamic UI Review

Judge a real interface with evidence, rank what matters, and fix only what was asked.

## Inputs

- Target: URL, route, component, or files. Resolve one concrete target before starting.
- Mode: **review only** (default — change nothing) or **fix** (the user asked for changes).
- Acceptance bar: WCAG 2.2 AA unless the user or project states another.

## Procedure

1. **Read the code.** The target files, the tokens/theme, and one representative shared component.
   Walk [checklist.md](references/checklist.md) and record findings as `file:line`.
2. **Render it** with the `clonamic-browser-qa` skill: screenshots at 375, 768, and 1440 wide; a
   keyboard-only pass; reduced-motion and dark-mode emulation where supported; 200% zoom; console
   errors. Open every screenshot and look at it.
3. **Measure contrast.** Read computed text and background colors from the browser (for text over
   images or translucent layers, sample the rendered pixels) and run
   `python3 scripts/contrast.py FG BG` for each distinct pair (path relative to this skill's folder).
   Exit code 1 means below target; `--fix fg` proposes the smallest lightness change; `--json` for
   batches.
4. **Judge the design.** Hierarchy (blur or shrink the screenshot — does the main action still
   lead?), spacing rhythm, type scale, color restraint, consistency across screens, and
   [anti-patterns.md](references/anti-patterns.md).
5. **Rank findings** P0–P3. Each one gets: evidence (measured, observed, or judgment — say which),
   user impact, and the smallest practical fix.
   - P0 blocks a task or excludes a group of users (keyboard trap, invisible primary action).
   - P1 fails the acceptance bar or seriously hinders use.
   - P2 noticeable friction or inconsistency with a workaround.
   - P3 polish.
6. **Fix mode only.** Apply fixes in priority order with the smallest coherent change, reusing
   existing tokens and components. Re-run the same evidence for each fix; stop when the acceptance
   bar or the user's request is met.
7. **Report** in the format below. Show a score only if every dimension and its rule are shown.

## Refinement requests

When the user asks for a direction rather than a defect list, apply one move and keep the rest:

- **Quieter** — fewer accents, lower saturation and weight, less motion, more space.
- **Bolder** — larger type contrast, one committed color field, a stronger focal point.
- **Simpler** — remove redundant elements and copy, merge sections, cut one level of nesting.
- **Harden** — long and localized text, empty, loading, error, offline, slow network, huge data.
- **Adapt** — breakpoints, touch targets, safe areas, orientation, input modes.
- **Clarify** — labels, error messages, empty states, onboarding hints.
- **Animate** — motion that explains state changes only; see the `clonamic-ui-design` skill's
  `references/interaction-motion.md`.

## Report format (user-facing, Korean)

```markdown
## UI 리뷰 결과 — /pricing (리뷰 전용, 기준 WCAG 2.2 AA)

가장 큰 문제: 375px에서 요금 비교표가 가로로 넘쳐 결제 버튼이 화면 밖으로 밀립니다.

| 등급 | 문제 | 근거 | 영향 | 최소 수정 |
|---|---|---|---|---|
| P0 | 모바일에서 결제 버튼 접근 불가 | 375px 스크린샷, 표 너비 612px (관찰) | 모바일 사용자 결제 불가 | 표를 카드형으로 전환 또는 가로 스크롤 영역 분리 |
| P1 | 보조 텍스트 대비 부족 | `#9AA0A6` on `#FFFFFF` = 2.64:1 (측정) | 저시력 사용자 판독 어려움 | `--text-muted`를 `#72777D`(4.52:1)로 |
| P2 | 포커스 링 없음 | `button.css:14` `outline: none` (코드) | 키보드 사용자가 위치를 잃음 | `:focus-visible` 링 추가 |

- 유지할 점: 요금제 이름과 가격의 위계가 명확하고, 숫자에 tabular-nums가 적용되어 있습니다.
- 확인하지 못한 항목: 실제 스크린리더 낭독(접근성 트리만 확인), 저사양 기기 성능.
```
