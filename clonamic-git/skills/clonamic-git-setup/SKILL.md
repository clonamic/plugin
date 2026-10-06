---
name: clonamic-git-setup
description: "One-time setup so agent hosts stop adding AI attribution to git: switch off each host's own commit/PR attribution (Claude Code, Codex, Cursor, Grok Build) and install a project-local commit-msg hook that strips AI trailers on every commit. Runs only on the explicit /clonamic-git-setup command or a request such as 'AI 커밋 흔적 안 남게 설정해줘'."
disable-model-invocation: true
user-invocable: true
---

# clonamic-git-setup — stop attribution at the source

Runs only on the explicit `/clonamic-git-setup` command or a direct user request.

Default layers: the **host switch** stops the agent from writing attribution, `clonamic-commit` filters every message, PR body, tag, and release note, and `scan_history.py` checks unpushed commits before a push.

**Never touch the user's project.** A repo hook lives in `.git/hooks`, which is outside the agent folder, so it is opt-in only: install it only when the user explicitly asks for a hook in that specific repository. Never install it as part of setup, never suggest it repeatedly, and never write anything else into a project (no `.gitignore`, `.git/config`, or tracked files).

Resolve `CLONAMIC_GIT_ROOT` to the plugin directory two levels above this `SKILL.md`. Scripts need Python 3.12+ (standard library only); if `python3` is older, install 3.12 (`uv python install 3.12` or the OS package manager) instead of falling back.

## 1. Repo hook — only on explicit request for this repository

1. `python3 "$CLONAMIC_GIT_ROOT/scripts/install_hook.py" --status`
2. `python3 "$CLONAMIC_GIT_ROOT/scripts/install_hook.py"` — writes `commit-msg` and a self-contained `clonamic-strip-ai-trailers` filter into the repo's own hooks dir (inside `.git`, untracked, survives plugin updates). It prints how to remove it (`--uninstall`, or delete both files).
   - Exit 1 "refused: … core.hooksPath" → the repo uses a shared or tracked hooks dir (husky, lefthook, a global path). Tell the user and offer to add the printed one-line call to that hook manager's `commit-msg` instead; editing a tracked hook file is a repo change the user must approve.
   - Exit 1 "refused to replace the existing … commit-msg" → a foreign hook exists. Offer to add the printed `CHAIN_LINE` to it; never overwrite it.
3. Optional repo-specific extra patterns (regex, case-insensitive, one per entry): `git config --add clonamic.aiPattern '<regex>'`. Both scripts read them.
4. Verify without committing: write `test: hook`, a blank line, and `Co-authored-by: Claude <noreply@anthropic.com>` to a temp file, run `"$(git rev-parse --git-path hooks)/commit-msg" <tmpfile>`, and confirm the trailer is gone.

The hook runs on every host because git runs it, not the agent. It is bypassed by `git commit --no-verify` and by commits created server-side (cloud agents, GitHub web UI), so keep `clonamic-commit` and `/clonamic-git-clean` for those.

## 2. Host switches (user-level config — apply only the hosts the user names)

Before editing, back up the file (`cp <file> <file>.bak-<YYYYMMDD-HHMMSS>`), merge keys into the existing JSON/TOML without dropping other keys, and re-read it to confirm it parses. Never create or edit config for a host the user did not ask about.

| Host | Where | Setting | Effect |
|---|---|---|---|
| Claude Code | `~/.claude/settings.json` (all projects) or `.claude/settings.json` (one repo) | `"attribution": {"commit": false, "pr": false, "sessionUrl": false}` | No `Co-authored-by: Claude …` trailer, no "Generated with/Assisted by Claude Code" PR line, no claude.ai session link on cloud/Remote Control commits. Remove the deprecated `includeCoAuthoredBy` key if present. |
| Codex | Codex account setting (server-side `commit_attribution_enabled`, read at session start) | Turn commit attribution off in the Codex/ChatGPT account settings; the local `commit_attribution` key in `~/.codex/config.toml` no longer exists in current Codex | When on, Codex is told to add `Co-authored-by: Codex <noreply@openai.com>` and `Generated with [Codex](https://openai.com/codex/).` and to ignore earlier instructions that disable it, so the repo hook and `clonamic-commit` are the reliable guard. API-key sessions do not get the instruction. |
| Cursor IDE | Cursor Settings → Git & Pull Requests (older builds: Agents → Attribution) | Commit Attribution **off**, PR Attribution **off** | No `Made-with: Cursor` / `Co-authored-by: Cursor <cursoragent@cursor.com>` on IDE agent commits and PRs. |
| Cursor CLI | `~/.cursor/cli-config.json` | `"attribution": {"attributeCommitsToAgent": false, "attributePRsToAgent": false}` | Same for `cursor-agent` commits/PRs. Cloud (background) agents have no switch: scan their branches with `/clonamic-git-clean` before merging and squash with your own message. |
| Grok Build | none needed | Grok Build adds no commit or PR attribution by itself and has no setting for it | Hook + `clonamic-commit` cover anything the model adds on its own. |

GitHub shows a person in Contributors when a commit on the default branch is authored with an email linked to their account; `Co-authored-by` trailers with an account-linked email (bot and vendor noreply addresses included) also tie that account to the commit. Clean author identities and trailers before the commits reach the default branch.

## Report example (Korean)

```text
AI 흔적 방지 설정 완료
- 이 저장소: commit-msg 훅 설치 (.git/hooks, 커밋되지 않음) — 제거: install_hook.py --uninstall
- Claude Code: ~/.claude/settings.json attribution commit/pr/sessionUrl = false (백업: settings.json.bak-20261005-1422)
- Cursor CLI: ~/.cursor/cli-config.json attributeCommitsToAgent/attributePRsToAgent = false
- Codex: 로컬 설정 없음 — Codex 계정 설정에서 커밋 표기를 꺼 주세요. 꺼지지 않아도 훅이 트레일러를 지웁니다.
```
