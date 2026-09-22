# Reference and template contracts

These tools read PPTX OOXML directly with the Python standard library. They never modify a reference file.

## Reference decks

Run both measurements against approved reference decks:

```bash
python3 "$PPT_SKILL_ROOT/scripts/extract_design_dna.py" reference-1.pptx reference-2.pptx --out design_dna.json
python3 "$PPT_SKILL_ROOT/scripts/measure_word_budget.py" reference-1.pptx reference-2.pptx --out word_budget.json
```

`design_dna.json` separates colors and fonts used on actual slides from theme declarations and reports measured geometry rhythm. `word_budget.json` counts text boxes, tables, and linked charts. Its rounded-up median is the ceiling; split a slide above it instead of reducing font size.

## Templates

```bash
python3 "$PPT_SKILL_ROOT/scripts/template_contract.py" template.pptx --out template_contract.json
```

The contract records masters, layouts, semantic placeholder keys, protected master regions, and exemplar geometry. It is extraction-only: the current blank-canvas renderer does not apply a template or claim to preserve its master. Use the contract as measured design input, match placeholders by semantic key or name, and never select a shape by its position in a shape list.

## Engine input

`run_engine.py` accepts repeatable `--reference-pptx` arguments. It writes extracted reference contracts under `reference_contracts/` and records their paths in `deck_ir.json`. Template extraction remains a separate read-only command and is not an engine apply option.

Every validation-passing run also writes `svg/manifest.json` and one bounded SVG per DeckIR slide. Blocked input stops with `qa_report.json`. SVG files are QA previews only. The editable `presentation.pptx` remains the delivery artifact.

Reference extraction adds no Python dependency, environment, container, or browser installation. The existing office renderer remains best-effort, isolated, timeout-bounded, and default-off on macOS unless explicitly enabled.
