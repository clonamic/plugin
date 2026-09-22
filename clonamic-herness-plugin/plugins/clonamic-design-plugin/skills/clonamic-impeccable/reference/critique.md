# Critique

Critique is read-only by default. Inspect the requested surface and return the
full result in chat. Do not create snapshots, journals, ignore files, temp
files, config, or backlog artifacts unless the user explicitly requested a
persistent critique artifact and the host write boundary has already cleared
that exact output.

## Evidence

1. Resolve one concrete target from the request and repository.
2. Review hierarchy, interaction, accessibility, responsive behavior, copy,
   states, performance signals, and fit with the existing design system.
3. When available, run the bundled detector without changing source:
   `node "$IMPECCABLE_ROOT/scripts/detect.mjs" --json <target>`.
4. Use an isolated host-provided browser only when visual evidence materially
   improves the answer. Do not reuse a personal browser session or inject a
   persistent script. Stop every process started for inspection before
   reporting.
5. Distinguish measured evidence, design judgment, false positives, and
   unverified checks.

Independent reviewers are optional. Use them only when the host's team policy
finds that their value exceeds coordination cost; never stop merely to ask for
a reviewer. A sequential local double pass is the fallback.

## Chat result

Lead with the most consequential finding. Then list:

- strengths that should be preserved;
- 3–5 priority defects with severity, exact evidence, user impact, and the
  smallest practical fix;
- accessibility and responsive risks;
- detector findings and false positives;
- unverified items.

Use a score only when every dimension and scoring rule is shown. Do not ask a
follow-up question after a complete read-only critique. If a material design
choice blocks an explicitly requested implementation, route that one decision
through the host's existing intent gate; do not create another approval flow.

## Optional snapshot

Only after an explicitly approved artifact request, write the same chat report
to the exact requested project path. Do not create a default hidden directory
or make later commands depend on that snapshot.
