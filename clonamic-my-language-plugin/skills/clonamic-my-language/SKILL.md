---
name: clonamic-my-language
description: Capture and use the text after /clonamic-my-language for this response only. Never invoke automatically or collect any other role.
disable-model-invocation: true
user-invocable: true
---

# Clonamic My Language

Run only when the user explicitly enters `/clonamic-my-language`. The slash token itself is the
authorization to store this command's user payload in the plugin-local database; it authorizes no
other write.

## Invocation

1. Remove only the slash command token and its single separating space. Preserve every remaining
   UTF-8 byte, including newlines and emoji.
2. Pipe that payload through stdin to `scripts/my_language.py capture`. Never place it in argv,
   logs, a temporary file, or another prompt source.
3. Use the returned `profile` only while answering the captured payload. Preserve facts, quoted
   text, numbers, identifiers, and code before matching style.
4. Run exactly one review pass against
   [review-contract.json](references/review-contract.json). This main command owns that pass. When
   the host exposes the package's `clonamic-my-language-review` native child agent, give it the
   active command, derived profile, contract, and draft. Otherwise execute the same contract
   sequentially here. Never invoke the sibling reviewer skill as an independently routed skill.
   Do not persist the draft or review.
5. Discard the profile from working context after this response.

```bash
python3 "$CLONAMIC_MY_LANGUAGE_ROOT/scripts/my_language.py" capture
```

Resolve `CLONAMIC_MY_LANGUAGE_ROOT` to this skill directory. The runtime accepts payload bytes
only on stdin and defaults to the private local data path documented in
[runtime-contract.json](references/runtime-contract.json).

## Boundaries

- Accept `source_role=user` and `explicit_command=/clonamic-my-language` only.
- Never capture ordinary chat, system/developer instructions, assistant output, tool output,
  files, clipboard contents, or earlier conversation history.
- Never start a watcher, cron job, hook, server, network request, or background analysis.
- Never run the review path outside an active `/clonamic-my-language` invocation.
- Treat low-confidence profile fields as weak hints, not facts about the user.
- Model observable language habits only; never infer personality, identity, health, intent, or
  other psychological traits.
