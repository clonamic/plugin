---
name: clonamic-my-language-export
description: Export the current local style checkpoint only when the user explicitly invokes /clonamic-my-language-export.
disable-model-invocation: true
user-invocable: true
---

# Clonamic My Language Export

Run only on `/clonamic-my-language-export`. The command authorizes one export to the requested
destination; it does not authorize collection or installation.

Use the sibling runtime:

```bash
python3 "$CLONAMIC_MY_LANGUAGE_ROOT/scripts/my_language.py" export --output "<destination>"
```

Resolve `CLONAMIC_MY_LANGUAGE_ROOT` to the installed `clonamic-my-language` skill directory. If
no sample exists, stop with that error. The runtime materializes a current checkpoint and writes a
deterministic Agent Plugins 1.0.0 package containing only the derived profile, an explicit apply
skill, and an explicit reviewer skill.

Never add raw prompts, examples copied from prompts, database contents, timestamps, session data,
environment values, or local paths to the export. Never overwrite a destination.
