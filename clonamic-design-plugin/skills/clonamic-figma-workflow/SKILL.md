---
name: clonamic-figma-workflow
description: "Host-native Figma workflow for faithful creation and editing — connection check, document inspection, no vertical text wrap or overlap, and an export-and-verify loop. Use only when a Figma tool is already connected or the user asks how to connect one."
---

# Figma Workflow

## 1. Session setup

- Use the Figma capability already connected to the current host. Never launch Claude, Codex,
  Grok, Hermes, or another executor from this skill. An external executor is eligible only after
  its explicit slash command in the current user request.
- Inspect the available tool contract before acting. If it requires a channel or document key,
  use the exact user- or host-supplied value; never guess it.
- Use the user's named page. Otherwise inspect the current page and reuse it unless isolation is
  required for a new artifact.
- Read document structure before creating anything and reuse existing frames and styles.
- If no Figma capability is connected, state the missing connection. Do not install a server,
  register global configuration, or start a background process as a fallback.

## 2. Faithful reproduction rules (hard requirements from past feedback)

- Reproduce reference images **as-is**: same layout, proportions, hierarchy — no "creative improvements" unless asked.
- **No vertical character stacking**: every text node's width must fit its content (set frame/text width first, then text; after `set_text_content`, check bounds — a 1-character-per-line wrap is a bug, widen the box).
- **No overlapping elements**: after placing nodes, verify x/y/width/height don't collide; prefer `set_auto_layout` for rows/columns/stacks over manual coordinates.
- Load fonts before styling: `load_font_async`, then `set_font_name`/`set_font_size` — never assume a font is available.

## 3. Build procedure

1. Frame first with explicit x/y/size (`create_frame`), name it meaningfully (`rename_node`).
2. Children inside via `insert_child` / auto-layout; group logical clusters (`group_nodes`).
3. Text: create → widen box → set content → set typography → re-check bounds.
4. Colors/effects from the reference's actual values — sample them, don't approximate from memory.

## 4. Export-and-verify loop (mandatory)

After building: `export_node_as_image` on the top frame → **look at the image** → compare against the reference → fix wraps/overlaps/misalignment → re-export. Repeat until clean. Never declare a Figma task done without at least one exported-image inspection.

## 5. Cleanup

Meaningful node names, logical grouping, delete scratch nodes. Report the page + top frame name to the user.

## Offline and source boundary

The reproduction rules and local export checks work offline once the source artifact is available. Live Figma inspection or editing requires an explicitly connected Figma session and is never silently replaced with guessed values. Do not install an MCP server, register global configuration, or fetch a remote Figma file without the user's request and exact connection details.

OpenAI's current Figma agent integration lives in the official `openai/plugins` repository and is governed by Figma's developer terms; it is a runtime reference, not vendored public content in this skill.
