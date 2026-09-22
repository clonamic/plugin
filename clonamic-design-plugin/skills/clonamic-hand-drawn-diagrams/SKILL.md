---
name: clonamic-hand-drawn-diagrams
description: Create an editable hand-drawn Excalidraw diagram, sketch flow, explainer, wireframe, or page mockup when the user explicitly wants that visual language. Do not select when Mermaid, a normal vector diagram, or prose is sufficient, or for product UI implementation.
license: Complete terms in LICENSE.txt
---

# Clonamic Hand-Drawn Diagrams

Create local, editable `.excalidraw` JSON first. SVG or PNG is a derived preview. The default path is fully offline; hosted scene URLs and browser-extension setup are optional only when the user explicitly asks.

## Workflow

1. Choose the smallest diagram type that communicates the idea and define the reading order.
2. Use a restrained hand-drawn vocabulary: boxes, arrows, labels, and at most one emphasis color unless the brief asks for a page-like mockup.
3. Route arrows around nodes; do not cross labels or hide connection meaning. Keep labels horizontal and short.
4. Resolve `HAND_DRAWN_SKILL_ROOT` to the host-provided directory containing this `SKILL.md`. Save valid Excalidraw JSON locally and run `python3 "$HAND_DRAWN_SKILL_ROOT/scripts/validate_excalidraw.py" <file>` when compatible with the output schema. Never scan vendor homes or execute a project-relative helper.
5. Produce SVG/PNG only with tools already installed. If rendering is unavailable offline, return the editable `.excalidraw` file and explain the missing preview; do not install Playwright, Chrome tooling, or a server silently.
6. Inspect legibility, arrow ownership, bounds, clipping, and accidental overlap before completion.

Open `references/fundamental-shapes.md`, `references/arrow-routing.md`, or `references/quality-checklist.md` only when that aspect is needed. `references/json-schema.md` is for file-format questions.

## Isolation

Never modify global browser settings, profiles, extensions, or MCP configuration. Never start a background server unless the user explicitly requests the hosted/editor workflow and approves that exact process.

## Provenance

Adapted and reduced from Muthukumaran Navaneethakrishnan's MIT-licensed `hand-drawn-diagrams`. Network-hosted URLs and automatic tool installation were removed from the default workflow.
