# Astryx CLI + JSON Manifest Contract (vendored snapshot)

Source: https://astryx.atmeta.com/docs/cli ,
https://astryx.atmeta.com/docs/working-with-ai ,
https://astryx.atmeta.com/changelog
Fetched: 2026-07-25
CLI/core version at fetch time: 0.1.8 (Beta). Manifest capability first
appeared at v0.0.15 per changelog.

Treat every command/flag below as a starting point, not ground truth. Resolve
`ASTRYX_BIN` to an already installed project-local CLI and run
`"$ASTRYX_BIN" manifest --json` before relying on exact flags or response
shapes. Never use `npx` or install dependencies during normal use.

## Core commands

- `astryx search <query>` — find components, hooks, docs, templates by
  relevance. Flags: `--type <component|hook|doc|template>`, `--limit <n>`,
  `--detail`, `--json`.
- `astryx component [Name]` — component docs, props, usage, source. Flags:
  `--list`, `--props`, `--source`, `--showcase`, `--blocks`, `--json`.
- `astryx docs [topic]` — tokens, themes, colors, typography, spacing.
  Flags: `--list`, `--json`.
- `astryx template [name] [path]` — inject page/block templates. Flags:
  `--list`, `--skeleton`, `--json`.
- `astryx hook [name]` — hook docs/params. Flags: `--list`, `--params`,
  `--json`.
- `astryx init` — install packages, set up theming, add agent docs. Flag:
  `--features agents`.
- `astryx theme build <file>` — compile a `defineTheme` file into production
  CSS + JS.
- `astryx swizzle` — copy component source for deep customization. Flags:
  `--list`, `--json`.
- `astryx upgrade` — run codemods for version migration. Flags: `--list`,
  `--apply`, `--codemod <name>`, `--from`, `--to`.
- `astryx doctor` — health check; exit 0 (clean) / 1 (failures). Flag:
  `--json`.
- `astryx discover [@scope/name][/ComponentName]` — locate external
  integration packages/components. Flag: `--json`.

## Manifest / self-description

```bash
astryx manifest --json
# or: astryx --json   (embeds manifest under data.manifest)
```

Shape: `{ apiVersion, type: "manifest", data: { name, version, commands[],
globalOptions[], responseTypes } }`. This is the authoritative, current
description of every command, arg, flag, and response type — read it at
integration time rather than trusting this file's command list verbatim.

## Global flags

- `--json` — typed envelope: `{ type, data }`.
- `--detail <level>` — `brief | compact | full`.
- `--lang <locale>` — `en | zh | dense`.
- `--dense` — token-efficient output tuned for AI agents/web tools.
- `--zh` — Simplified Chinese output.

## Response / error shape

Success: `{"type": "component.detail", "data": {"name": "Button", ...}}`

Error: `{"error": "...", "code": "ERR_...", "suggestions": [...]}` — stable
codes observed: `ERR_UNKNOWN_COMPONENT`, `ERR_CORE_NOT_FOUND`,
`ERR_FILE_NOT_FOUND`, `ERR_INVALID_OPTION`, `ERR_PATH_TRAVERSAL`.

## Project config (optional)

`astryx.config.{ts,mjs,js}` next to `package.json`:

```ts
export default {
  integrations: ['@acme/astryx-widgets'],
  issuesUrl: 'https://github.com/your-org/your-repo/issues',
  hooks: { postCodemod: [] },
};
```

Third-party packages contribute via `astryx.integration.{ts,mjs,js}`
(`components`, `templates`, `codemods`, `issuesUrl` fields).

## MCP server

Astryx ships a **hosted, remote** MCP server — no local package/process to
install or start:

```json
{"mcpServers": {"xds": {"type": "url", "url": "https://astryx.atmeta.com/mcp"}}}
```

Compatible with Claude Desktop (`claude_desktop_config.json`), Cursor
(`.cursor/mcp.json`), Windsurf (`.windsurf/mcp.json`), Cline, and other
MCP-compatible tools. Exposes two tools:

- `search(query)` — natural-language discovery across components, docs,
  templates.
- `get(name)` — full documentation for one item (props, usage, examples).

Per the design-workflow rule, do not add this to any project's `.mcp.json`
or global MCP config automatically — surface the snippet and let the user
opt in.
