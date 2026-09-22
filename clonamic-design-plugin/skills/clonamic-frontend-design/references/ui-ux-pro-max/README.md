# UI UX Pro Max offline reference

Pinned MIT-licensed data and Python standard-library search utilities from `nextlevelbuilder/ui-ux-pro-max-skill`.

Use only when the user explicitly asks for UI UX Pro Max, a catalog-backed design-system recommendation, or comparison across its stored styles/stacks. Do not preload the CSV catalog for ordinary new UI work.

Run from this directory:

```bash
python3 "$FRONTEND_DESIGN_ROOT/references/ui-ux-pro-max/scripts/search.py" "<query>" --domain style
python3 "$FRONTEND_DESIGN_ROOT/references/ui-ux-pro-max/scripts/design_system.py" "<product description>"
```

This Clonamic copy is stdout/JSON only: persistence, page output, and output-directory options are disabled so a catalog lookup cannot overwrite project files. Results are evidence for a design plan, not a second aesthetic specialist; `clonamic-frontend-design` still owns the final direction.

URLs, Google Fonts imports, CDN snippets, and package commands inside CSV results are metadata only. In offline work, use repository-local or system fonts/assets and never execute or fetch a catalog string.
