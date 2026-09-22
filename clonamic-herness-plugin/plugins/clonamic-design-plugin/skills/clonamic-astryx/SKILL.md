---
name: clonamic-astryx
description: Meta Astryx (React design system) integration — component/accessibility foundation for NEW React work with NO established design system. Load only when the design-routing kernel's Astryx rule fires or on explicit Astryx request; never for existing-UI polish, exact reproduction, or non-React work.
---

# clonamic-astryx

Integration guide for Meta's Astryx — an open-source (MIT), Beta, React +
StyleX design system with 150+ accessible components, a CLI, a JSON
manifest, and an MCP server built for AI agents. Official sources:
https://github.com/facebook/astryx and https://astryx.atmeta.com.

## Eligibility gate (mirrors `rules/design/design-workflow.md` verbatim)

> Astryx is eligible only for new React work with no established design
> system; inspect the repository first and otherwise reuse its system. Treat
> Astryx as a component/accessibility foundation, not an aesthetic
> specialist, and verify its current Beta API through official CLI/docs. Do
> not install or migrate to Astryx for existing UI polish, exact
> reproduction, or non-React work.

If the gate does not clearly hold, use the repository's existing system.

## Runtime and setup boundary

Normal use requires an existing project-local CLI:

```bash
test -x ./node_modules/.bin/astryx
./node_modules/.bin/astryx manifest --json
```

If it is missing, report the unavailable runtime. Installation and scaffolding are separate project
mutations. Only after the user explicitly approves setup, select one exact compatible version and
record the pre-change files, then run:

```bash
npm install --save-exact \
  @astryxdesign/core@<approved-version> \
  @astryxdesign/theme-neutral@<approved-version> \
  @astryxdesign/cli@<approved-version>
./node_modules/.bin/astryx init
```

Do not generate or replace root agent guidance as part of ordinary initialization. A separate
explicit request may run `./node_modules/.bin/astryx init --features agents` only after backing up
the affected guidance and declaring its rollback.

Import base styles once in global CSS, then a theme:

```css
@import '@astryxdesign/core/reset.css';
@import '@astryxdesign/core/astryx.css';
@import '@astryxdesign/theme-neutral/theme.css';
```

Components import from category-scoped paths for bundle size:
`import {Button} from '@astryxdesign/core/Button';`

## Manifest / CLI is the source of truth, not this snapshot

The vendored files under `references/` are a dated snapshot (see each file's
header) of a Beta product that changes fast. Before relying on any prop,
command, or theme name:

1. Run `./node_modules/.bin/astryx manifest --json` for the live, machine-readable contract.
2. Run `./node_modules/.bin/astryx component <Name> --props --json` for current authoritative props.
3. Check `./node_modules/.bin/astryx doctor` and astryx.atmeta.com/changelog for breaking changes.

Useful commands: `astryx search <query>`, `astryx component --list`,
`astryx docs tokens`, `astryx template --list`.

## Theming

Adopt a preset (`neutral` default; others include `stone`, `gothic`,
`matcha`, `y2k`, `butter`, plus more — verify live list) via the CLI's theme
scaffold command, edit the generated `defineTheme` file, then build with
`astryx theme build <file>`. CSS-custom-property based; no StyleX compiler
needed unless swizzling component source.

## MCP server (optional — do not auto-add)

Astryx exposes a hosted MCP server (`search`, `get` tools) at
`https://astryx.atmeta.com/mcp`. Do not add it to `.mcp.json` or any config
automatically — surface the connection snippet to the user and let them
opt in:

```json
{"mcpServers": {"xds": {"type": "url", "url": "https://astryx.atmeta.com/mcp"}}}
```

## References

- `references/quickstart.md` — install, init, theming, agent-docs generation
- `references/cli-manifest.md` — CLI command/flag reference, JSON manifest
  contract, MCP tools, error codes
- `references/components.md` — component category index, theme presets
