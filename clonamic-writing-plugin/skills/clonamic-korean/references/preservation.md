# Preservation

This skill changes Korean prose only. It is not applicable when the primary surface is ordinary chat, a work report, source code, a spreadsheet, slides, or email.

Keep these spans exact unless the user explicitly supplied a replacement:

- numbers, dates, money, ratios, units, versions, and identifiers
- person, organization, product, place, law, paper, and project names
- direct quotations, citations, URLs, DOI values, and link targets
- negation, uncertainty, permission, obligation, comparison, and causal direction
- code fences, commands, paths, API names, placeholders, formulas, logs, and machine-generated lines
- table and CSV cell values
- bibliography, BibTeX, footnotes, link fragments, and query strings
- legal registry numbers, ISBN/ISSN, ISIN, tickers, coordinates, time zones, and postal codes
- masked personal data, one-time codes, fullwidth digits, circled markers, Hanja in names, and `[sic]`
- Mermaid, diff, conflict-marker, cron, UUID, SHA, regex, SPDX, ARN, and semantic-version syntax
- legal, medical, and financial duties, conditions, disclaimers, and claim strength

Do not add facts, actors, reasons, examples, customers, metrics, quotations, or lived experience. If a clear rewrite needs missing information, flag the gap instead of filling it.

Do not convert units, temperatures, time zones, relative dates, number formatting, or quoted spelling. A link label may be suggested, but its URL, DOI, query, and fragment are immutable. Never complete masked data or resolve conflict markers.

## Consistency checks

- Unsourced rankings, study results, comparisons, or quotations require a source request or weaker wording; labeled dashboard and slide metrics do not.
- A candidate that invents an example, customer, review, feeling, or stronger claim is invalid.
- Lost citations or links invalidate the candidate.
- Reuse the glossary, first definition, or majority term; do not invent acronym expansions or translations.
- Generic link labels may be clarified without changing their targets.
- Contradictions between headings, prose, tables, diagrams, or counts must be reported, not silently repaired with a new fact.

Before returning an edit, compare the original and revision for every protected span. A lost or changed protected span invalidates the revision.
