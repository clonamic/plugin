# Clonamic My Language Plugin

An explicit-only, local style-profile plugin. It records only the UTF-8 bytes supplied after
`/clonamic-my-language`, derives observable writing signals, and can export a raw-free portable
profile plugin.

## Commands

```bash
# The host removes the slash command token and pipes only its payload to stdin.
printf '%s' '이 문장 그대로 분석해줘.' | python3 skills/clonamic-my-language/scripts/my_language.py capture

python3 skills/clonamic-my-language/scripts/my_language.py export --output ./profile-plugin
python3 skills/clonamic-my-language/scripts/my_language.py inspect
```

The default database is `${CLONAMIC_DATA_HOME}/my-language/style.sqlite3`, or
`~/.clonamic/my-language/style.sqlite3` when the variable is absent. The database is created
lazily and is never part of this package.

The explicit main command always performs one review pass. Hosts with native child agents may use
the guarded package agent; other hosts apply the same contract sequentially.

No command watches files, runs in the background, contacts a server, or captures system,
developer, assistant, or tool content. Exported packages contain only a derived profile and two
explicit-only skills; they contain no prompt text, database, private path, or session data.
