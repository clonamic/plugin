---
name: clonamic-vercel-web-design-guidelines
description: Audit UI code against Vercel's named Web Interface Guidelines using the bundled offline snapshot. Select only when the user explicitly requests that published checklist; for general accessibility, UX critique, or polish use `impeccable`.
metadata:
  author: vercel
  version: "1.0.0"
  argument-hint: <file-or-pattern>
---

# Web Interface Guidelines

Review files for compliance with Web Interface Guidelines.

## Offline-first procedure

1. Read `references/command.md`, the pinned local snapshot.
2. Read the specified files or patterns.
3. Check every applicable rule without changing the interface unless the user asked for fixes.
4. Output findings in the snapshot's terse `file:line` format.

## Optional current-source check

Only when the user explicitly asks for the latest online version, retrieve:

```
https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md
```

Compare it to the local snapshot and state the retrieved commit/date. If the network is unavailable, continue with the local snapshot and label it pinned; never skip the audit silently.

## Usage

When a user provides a file or pattern argument, read those files, apply the local rules, and use the specified output format.

If no files specified, ask the user which files to review.

## Provenance

`references/command.md` is a pinned snapshot of Vercel Labs' MIT-licensed `web-interface-guidelines`. The repository source lock records the commit and digest.
