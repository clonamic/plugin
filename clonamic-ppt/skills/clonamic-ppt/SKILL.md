---
name: clonamic-ppt
description: Create or revise editable decks, slides, PowerPoint, or PPTX files through structured specifications, deterministic rendering, and QA.
---

# Presentation Engine

Work directly; do not delegate or select another runtime.

1. Read [references/specialist.md](references/specialist.md) and its purpose guidance.
2. Resolve all scripts and references from this skill directory. When reference or template PPTX files are supplied, read [references/reference-contracts.md](references/reference-contracts.md) and extract their contracts before authoring.
3. Resolve `PPT_SKILL_ROOT` to the host-provided directory containing this `SKILL.md`, then run `python "$PPT_SKILL_ROOT/scripts/doctor.py"`. If it reports `ready: false`, stop before creating artifacts and report its exact missing checks and recovery command; never claim the renderer is available. Never scan vendor-specific homes or execute a same-named project script.
4. Create `brief.json`, then `outline.json`, then `slide_specs.json` in the chosen output directory. Apply the measured word ceiling by cutting or splitting content, never by shrinking type.
5. Validate and render with the scripts in `scripts/`. Each validation-passing `run_engine.py` run creates bounded SVG previews for QA while keeping the PPTX editable; blocked input produces only `qa_report.json`.
6. Repair defects, rerun, and return artifact paths with QA findings.

Use only supplied facts and numbers. Do not hand-edit generated coordinates or XML. Images, including ICNS, JXL, HEIF, and HEIC, are unsupported.
Template inspection is extraction-only. The renderer does not apply a template or claim to preserve its master; use the semantic contract as design input for a fresh editable deck.
Use only the standard library for reference extraction. Do not create an environment, install a browser, or add a rendering dependency. On macOS, office rendering remains disabled unless the existing explicit opt-in is set.
