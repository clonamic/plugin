# Third-party notices

The Clonamic Korean plugin is MIT-licensed. It adapts MIT-licensed material from two sources.
The copyright lines and the full MIT text are in `LICENSE` at the plugin root and in
`skills/clonamic-korean/LICENSE`, so the notice travels with the skill folder when it is installed
on its own.

- **epoko77-ai — humanize-korean (MIT, Copyright (c) 2026 epoko77-ai).** The Korean AI-tell
  catalog, the rewriting recipes, the preservation rules, and the modality/quote/number patterns
  in `skills/clonamic-korean/scripts/check_revision.py` are condensed and rewritten from that
  project's taxonomy, playbook, and gate scripts.
- **artemnovitckii/content-skills (MIT, Copyright (c) 2026 Artem Novitckii,
  https://github.com/artemnovitckii/content-skills).** Rewritten in Korean and adapted to Korean
  documents:
  - `dumbify` → `skills/clonamic-korean/references/plain-korean.md`
  - `storytelling` → `skills/clonamic-korean/references/story.md`
  - `viral-hooks` → `skills/clonamic-korean/references/openings.md`
  - `voice-dna` → `skills/clonamic-korean/references/voice.md`
  - `anti-ai-writing` → folded into `references/ai-tells.md` and `references/rewriting.md`
    (specificity, hollow vs. earned contrast, metaphor test, formatting tells)

Not included: the `unslop` CLI (MIT, Copyright (c) 2026 Mohamed Abdallah) that the former
`clonamic-unslop` skill wrapped. No code or text from it is distributed here.
