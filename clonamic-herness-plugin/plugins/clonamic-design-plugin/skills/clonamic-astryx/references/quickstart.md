# Astryx Quickstart (vendored snapshot)

Source: https://github.com/facebook/astryx/blob/main/README.md ,
https://astryx.atmeta.com/docs/getting-started ,
https://astryx.atmeta.com/docs/working-with-ai
Fetched: 2026-07-25
Package version at fetch time: `@astryxdesign/core@0.1.8` (npm registry).
Status at fetch time: **Beta**, MIT license.

This is a point-in-time snapshot for offline reference. Astryx is Beta and
ships breaking changes between minor versions. Resolve `ASTRYX_BIN` to an
already installed project-local CLI and verify with
`"$ASTRYX_BIN" manifest --json` before depending on any detail below. Network
verification and dependency setup are separate, explicit actions.

## Install

Normal use never installs packages. If the user explicitly requests setup,
select and record one approved version, then use that same pinned version for
all Astryx packages:

```bash
npm install --save-exact @astryxdesign/core@<approved-version> @astryxdesign/theme-neutral@<approved-version> @astryxdesign/cli@<approved-version>
```

Optional local CLI alias for reliable invocation from scripts:

```json
"scripts": {
  "astryx": "node node_modules/@astryxdesign/cli/bin/astryx.mjs"
}
```

## Initialize a project

```bash
ASTRYX_BIN=./node_modules/.bin/astryx
test -x "$ASTRYX_BIN"
"$ASTRYX_BIN" init
```

Non-interactive — no prompts — so it is safe for AI agents, CI, and scripts.
Installs packages, sets up theming, and (with `--features agents`) adds
AI-agent context docs.

Generating agent guidance is a separate persistent change. Run it only when
that exact output was requested and approved:

```bash
"$ASTRYX_BIN" init --features agents
```

As of v0.1.8 the documented default is a root `AGENTS.md`. Treat every generated
path as version-dependent: inspect the installed CLI manifest and preview its
planned output before accepting a write.

## Import styles and a theme

```css
@import '@astryxdesign/core/reset.css';
@import '@astryxdesign/core/astryx.css';
@import '@astryxdesign/theme-neutral/theme.css';
```

## First component

Components import from category-specific subpaths to keep bundles small:

```tsx
import {Button} from '@astryxdesign/core/Button';
import {VStack} from '@astryxdesign/core/Layout';
```

## Dev requirements (for contributing to Astryx itself, not consuming it)

Node 22+ (active LTS), pnpm 11.

## Docs / Storybook

- Main docs: https://astryx.atmeta.com
- Storybook: https://facebook.github.io/astryx/storybook/
- Changelog: https://astryx.atmeta.com/changelog
