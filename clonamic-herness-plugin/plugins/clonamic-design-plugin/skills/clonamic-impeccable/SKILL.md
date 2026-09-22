---
name: clonamic-impeccable
description: Improve an existing frontend's UX, visual hierarchy, accessibility, responsiveness, performance, and polish. Use for design audits or material UI refinement. Skip backend-only work and fully specified one-value edits.
license: Apache 2.0; see LICENSE.txt and NOTICE.txt.
metadata:
  version: "1.0.0"
---

# Clonamic Impeccable

Improve a real interface without overriding the repository's existing design system or the user's
declared reference. This skill supplies optional design depth; it does not own approval, reporting,
browser safety, or project-wide automation.

When a command reference invokes a bundled script, resolve `IMPECCABLE_ROOT` to the host-provided
directory containing this loaded `SKILL.md`, then run scripts below that directory. Never infer the
path by scanning a vendor-specific home directory.

## Start

1. Read the target UI, its tokens/theme, and one representative component before proposing changes.
2. Classify the request:
   - brand/marketing surface → read `reference/brand.md`;
   - product/app surface → read `reference/product.md`;
   - explicit supported subcommand → also read only `reference/<command>.md`.
3. Preserve established identity. For a new system with no source of truth, use `shape` or `init` only
   when the user requested that scope.
4. Make the smallest coherent change and verify the actual target at narrow, medium, and wide widths.

Never run setup scripts, install hooks, create context files, or add dependencies merely because this
skill loaded. Such mutations require an explicit task and the normal write boundary.

Command references are subordinate technique notes, not independent workflows. The host's intent,
write, team, browser, and report contracts always win. Ignore any reference text that introduces an
extra approval, mandatory question round, implicit persistence, vendor-specific state, dependency
installation, or executor selection. When a reference conflicts, keep only its design heuristics.

This portable package does not install or activate editor hooks. Use its detector manually through a
host-resolved bundled script. Host-specific adapters may provide hooks only when they can verify the
installed runtime path and activation state; never claim a hook is active from config alone.

## Quality floor

- Body text contrast at least 4.5:1; large text at least 3:1.
- Body line length around 65–75 characters and headings tested with real/localized copy.
- Responsive layout without accidental overlap, clipping, horizontal overflow, or unusable hit areas.
- Motion tied to state or hierarchy, interruptible where interactive, with reduced-motion behavior.
- Existing components and tokens reused before new abstractions or dependencies.
- No decorative defaults such as gradient text, arbitrary glass cards, identical card grids, repeated
  eyebrow labels, fake metrics, or numbered sections without real sequence meaning.
- Content remains visible without animation, JavaScript timing, or a successful reveal callback.

## Supported commands

Load only the matching reference:

- Evaluate — `critique`, `audit`
- Refine — `polish`, `bolder`, `quieter`, `distill`, `harden`, `onboard`
- Enhance — `animate`, `colorize`, `typeset`, `layout`, `delight`, `overdrive`
- Fix — `clarify`, `adapt`, `optimize`

Build, setup, design-context generation, and live-edit workflows use the host's normal project
tools plus this skill's quality floor; this package intentionally adds no parallel gate or durable
runtime state for them.

If no command is named, pick the one reference that best matches the requested outcome. Ask only when
two materially different outcomes remain after reading the project. Do not auto-run a command chain.

## Verification

Use the host's isolated browser or project-native test tooling when available. Check the exact changed
surface, keyboard/focus behavior when interactive, reduced motion when animated, and long/localized
content. Fix evidence-backed defects and stop when the requested acceptance condition is met.

Return the finished result in the host's normal concise report. Do not emit scores without the tested
dimensions and evidence that produced them.
